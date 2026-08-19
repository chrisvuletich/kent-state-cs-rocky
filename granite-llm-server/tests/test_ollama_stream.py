from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

import requests
from urllib3.exceptions import ReadTimeoutError

from app import ollama_client
from app.ollama_client import OllamaCallError, call_ollama_chat_stream


def encode_event(event):
    return json.dumps(
        event,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"


class FakeStreamingResponse:
    def __init__(self, chunks=(), status_code=200):
        self.chunks = list(chunks)
        self.status_code = status_code
        self.close_calls = 0

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.close_calls += 1


def successful_body(*, include_thinking=False):
    first_message = {"role": "assistant", "content": "Olá "}
    if include_thinking:
        first_message["thinking"] = "private reasoning"
    return b"".join((
        encode_event({
            "model": "gemma4:latest",
            "message": first_message,
            "done": False,
        }),
        encode_event({
            "model": "gemma4:latest",
            "message": {"role": "assistant", "content": "🪨"},
            "done": False,
        }),
        encode_event({
            "model": "gemma4:latest",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 4,
            "eval_count": 2,
        }),
    ))


class OllamaStreamingClientTests(unittest.TestCase):
    def test_readiness_requires_vision_capability_when_image_input_is_enabled(self):
        tags = Mock()
        tags.json.return_value = {
            "models": [{"name": "gemma4:latest"}],
        }
        details = Mock()
        details.json.return_value = {
            "capabilities": ["completion", "vision"],
        }
        with (
            patch.object(
                ollama_client.requests,
                "get",
                return_value=tags,
            ) as get,
            patch.object(
                ollama_client.requests,
                "post",
                return_value=details,
            ) as post,
        ):
            self.assertTrue(ollama_client.check_ollama_readiness(
                "gemma4:latest",
                require_vision=True,
            ))

        post.assert_called_once_with(
            ollama_client.OLLAMA_BASE_URL + "/api/show",
            json={"model": "gemma4:latest"},
            timeout=ollama_client.OLLAMA_READY_TIMEOUT_SECONDS,
        )
        get.assert_not_called()

        details.json.return_value = {"capabilities": ["completion"]}
        with (
            patch.object(ollama_client.requests, "get", return_value=tags),
            patch.object(ollama_client.requests, "post", return_value=details),
        ):
            self.assertFalse(ollama_client.check_ollama_readiness(
                "gemma4:latest",
                require_vision=True,
            ))

    def test_streams_split_utf8_chunks_and_collects_final_telemetry(self):
        body = successful_body(include_thinking=True)
        emoji_index = body.index("🪨".encode("utf-8"))
        response = FakeStreamingResponse([
            body[:emoji_index + 1],
            body[emoji_index + 1:],
        ])

        with patch.object(ollama_client.requests, "post", return_value=response) as post:
            stream = call_ollama_chat_stream(
                "gemma4:latest",
                [{"role": "user", "content": "Hello"}],
                {"num_predict": 20},
                "medium",
            )
            deltas = list(stream)

        self.assertEqual(deltas, ["Olá ", "🪨"])
        self.assertTrue(stream.thinking_present)
        self.assertEqual(stream.telemetry, {
            "model_input_bytes": len(post.call_args.kwargs["data"]),
            "model_output_bytes": len(body),
            "provider": {
                "actual_model": "gemma4:latest",
                "stop_reason": "stop",
                "prompt_eval_count": 4,
                "eval_count": 2,
            },
        })
        self.assertEqual(response.close_calls, 1)

        request_payload = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(request_payload, {
            "model": "gemma4:latest",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
            "options": {"num_predict": 20},
            "think": "medium",
        })
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertEqual(
            post.call_args.kwargs["headers"],
            {"Content-Type": "application/json"},
        )

    def test_stream_accepts_crlf_and_a_final_line_without_newline(self):
        lines = successful_body().splitlines()
        body = b"\r\n".join(lines)
        response = FakeStreamingResponse([body])

        with patch.object(ollama_client.requests, "post", return_value=response):
            stream = call_ollama_chat_stream(
                "gemma4:latest",
                [{"role": "user", "content": "Hello"}],
            )

        self.assertEqual(list(stream), ["Olá ", "🪨"])
        self.assertEqual(stream.telemetry["model_output_bytes"], len(body))

    def test_stream_is_single_use(self):
        response = FakeStreamingResponse([successful_body()])
        with patch.object(ollama_client.requests, "post", return_value=response):
            stream = call_ollama_chat_stream(
                "gemma4:latest",
                [{"role": "user", "content": "Hello"}],
            )

        self.assertEqual(list(stream), ["Olá ", "🪨"])
        with self.assertRaisesRegex(RuntimeError, "only be consumed once"):
            list(stream)

    def test_pre_stream_http_failure_is_sanitized_and_closed(self):
        response = FakeStreamingResponse(status_code=504)
        with (
            patch.object(ollama_client.requests, "post", return_value=response),
            self.assertRaises(OllamaCallError) as raised,
        ):
            call_ollama_chat_stream(
                "gemma4:latest",
                [{"role": "user", "content": "Hello"}],
            )

        self.assertEqual(raised.exception.kind, "timeout")
        self.assertEqual(raised.exception.telemetry["model_output_bytes"], 0)
        self.assertEqual(response.close_calls, 1)

    def test_midstream_timeout_is_sanitized_and_closed(self):
        wrapped_timeout = requests.ConnectionError(
            ReadTimeoutError(None, "/api/chat", "private provider details")
        )
        response = FakeStreamingResponse([
            encode_event({
                "message": {"role": "assistant", "content": "Partial"},
                "done": False,
            }),
            wrapped_timeout,
        ])
        with patch.object(ollama_client.requests, "post", return_value=response):
            stream = call_ollama_chat_stream(
                "gemma4:latest",
                [{"role": "user", "content": "Hello"}],
            )

        iterator = iter(stream)
        self.assertEqual(next(iterator), "Partial")
        with self.assertRaises(OllamaCallError) as raised:
            next(iterator)

        self.assertEqual(raised.exception.kind, "timeout")
        self.assertNotIn("private provider details", str(raised.exception))
        self.assertEqual(response.close_calls, 1)

    def test_malformed_or_incomplete_provider_streams_fail_closed(self):
        invalid_bodies = (
            b"not-json\n",
            encode_event(["not", "an", "object"]),
            encode_event({"error": "private provider failure"}),
            encode_event({
                "message": {"role": "assistant", "content": "No done"},
                "done": False,
            }),
            encode_event({
                "message": {"role": "assistant", "content": ""},
                "done": True,
            }),
            encode_event({
                "message": {"role": "assistant", "content": 12},
                "done": False,
            }),
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                response = FakeStreamingResponse([body])
                with patch.object(
                    ollama_client.requests,
                    "post",
                    return_value=response,
                ):
                    stream = call_ollama_chat_stream(
                        "gemma4:latest",
                        [{"role": "user", "content": "Hello"}],
                    )

                with self.assertRaises(OllamaCallError) as raised:
                    list(stream)
                self.assertEqual(raised.exception.kind, "invalid_response")
                self.assertEqual(response.close_calls, 1)

    def test_stream_line_and_total_body_limits_fail_closed(self):
        for setting, limit in (
            ("_MAX_STREAM_LINE_BYTES", 8),
            ("_MAX_STREAM_BODY_BYTES", 8),
        ):
            with self.subTest(setting=setting):
                response = FakeStreamingResponse([b"123456789"])
                with (
                    patch.object(ollama_client, setting, limit),
                    patch.object(
                        ollama_client.requests,
                        "post",
                        return_value=response,
                    ),
                ):
                    stream = call_ollama_chat_stream(
                        "gemma4:latest",
                        [{"role": "user", "content": "Hello"}],
                    )
                    with self.assertRaises(OllamaCallError) as raised:
                        list(stream)

                self.assertEqual(raised.exception.kind, "invalid_response")
                self.assertEqual(response.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
