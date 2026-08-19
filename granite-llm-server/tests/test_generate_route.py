import base64
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

import requests

import app.main as granite_main
from app.main import app as flask_app
from app.ollama_client import OllamaCallError
from app.stream_contract import validate_stream


# Run from the granite-llm-server directory:
# python -m unittest tests.test_generate_route -v


def encode_json(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def make_ollama_response(payload):
    return Mock(content=encode_json(payload), status_code=200)


def granite_payload(text="Hello"):
    return {"model": "gemma4:latest", "input": [{
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }]}


TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)


def granite_image_payload(*, stream=False):
    image_bytes = base64.b64decode(TINY_PNG_BASE64)
    payload = {
        "model": "gemma4:latest",
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Describe it."},
                {
                    "type": "input_image",
                    "mime_type": "image/png",
                    "image_base64": TINY_PNG_BASE64,
                    "detail": "auto",
                    "byte_length": len(image_bytes),
                    "width": 1,
                    "height": 1,
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                },
            ],
        }],
    }
    if stream:
        payload["stream"] = True
    return payload


def decode_ndjson(response):
    return [
        json.loads(line)
        for line in response.get_data(as_text=True).splitlines()
        if line
    ]


class FakeOllamaStream:
    def __init__(
        self,
        deltas=(),
        *,
        thinking_present=False,
        telemetry=None,
        failure=None,
    ):
        self.deltas = list(deltas)
        self.thinking_present = thinking_present
        self.telemetry = telemetry or {
            "model_input_bytes": 100,
            "model_output_bytes": 80,
            "provider": {"actual_model": "gemma4:latest"},
        }
        self.failure = failure
        self.close_calls = 0

    def __iter__(self):
        for delta in self.deltas:
            yield delta
        if self.failure is not None:
            raise self.failure

    def close(self):
        self.close_calls += 1


class TestGenerateRoute(unittest.TestCase):

    def setUp(self):
        flask_app.config["TESTING"] = True
        self.client = flask_app.test_client()

    @patch("app.ollama_client.requests.post")
    def test_generate_requires_configured_internal_token(self, mock_post):
        with patch.object(granite_main, "GRANITE_AUTH_TOKEN", "synthetic-granite-token"):
            rejected = self.client.post("/generate", json=granite_payload())
            mock_post.return_value = make_ollama_response({
                "message": {"content": "Authenticated"}
            })
            accepted = self.client.post(
                "/generate",
                json=granite_payload(),
                headers={"X-Rocky-Granite-Token": "synthetic-granite-token"},
            )

        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        mock_post.assert_called_once()

    def test_generate_returns_retryable_busy_response(self):
        gate = Mock()
        gate.acquire.return_value = False
        with patch.object(granite_main, "INFERENCE_GATE", gate):
            response = self.client.post("/generate", json=granite_payload())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"]["type"], "model_busy")
        self.assertEqual(response.headers["Retry-After"], "2")

    def test_streaming_requires_the_rollout_flag(self):
        payload = granite_payload()
        payload["stream"] = True
        with (
            patch.object(granite_main, "ENABLE_STREAMING", False),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
        ):
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], {
            "type": "bad_request",
            "message": "Streaming is not enabled.",
        })
        call_stream.assert_not_called()

    def test_image_input_requires_its_rollout_flag(self):
        with (
            patch.object(granite_main, "ENABLE_IMAGE_INPUT", False),
            patch.object(granite_main, "call_ollama_chat") as call_ollama,
        ):
            response = self.client.post("/generate", json=granite_image_payload())

        self.assertEqual(response.status_code, 400)
        self.assertIn("not enabled", response.get_json()["error"]["message"])
        call_ollama.assert_not_called()

    def test_image_input_reaches_ollama_for_json_generation(self):
        result = {
            "content": "One pixel.",
            "thinking_present": False,
            "telemetry": {},
        }
        with (
            patch.object(granite_main, "ENABLE_IMAGE_INPUT", True),
            patch.object(
                granite_main,
                "call_ollama_chat",
                return_value=result,
            ) as call_ollama,
        ):
            response = self.client.post("/generate", json=granite_image_payload())

        self.assertEqual(response.status_code, 200)
        call_ollama.assert_called_once_with(
            "gemma4:latest",
            [{
                "role": "user",
                "content": "Describe it.",
                "images": [TINY_PNG_BASE64],
            }],
            {},
            None,
        )

    def test_image_input_reaches_ollama_for_streaming_generation(self):
        upstream = FakeOllamaStream(["One pixel."])
        with (
            patch.object(granite_main, "ENABLE_IMAGE_INPUT", True),
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                return_value=upstream,
            ) as call_stream,
        ):
            response = self.client.post(
                "/generate",
                json=granite_image_payload(stream=True),
                buffered=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(decode_ndjson(response)[-1]["type"], "completed")
        self.assertEqual(
            call_stream.call_args.args[1][0]["images"],
            [TINY_PNG_BASE64],
        )

    def test_generate_rejects_non_boolean_stream_before_inference(self):
        payload = granite_payload()
        payload["stream"] = "true"
        with patch.object(granite_main, "call_ollama_chat_stream") as call_stream:
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("stream", response.get_json()["error"]["message"])
        call_stream.assert_not_called()

    def test_generate_streams_normalized_ndjson_and_holds_capacity_until_done(self):
        payload = granite_payload()
        payload.update({
            "stream": True,
            "max_output_tokens": 40,
        })
        upstream = FakeOllamaStream(["Hello ", "Rocky!"])
        gate = Mock()
        gate.acquire.return_value = True

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_GATE", gate),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                return_value=upstream,
            ) as call_stream,
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=True,
            )

        events = decode_ndjson(response)
        validate_stream(events)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/x-ndjson")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertEqual([event["type"] for event in events], [
            "started",
            "delta",
            "delta",
            "completed",
        ])
        self.assertEqual(events[1]["text"] + events[2]["text"], "Hello Rocky!")
        self.assertEqual(events[-1]["telemetry"], upstream.telemetry)
        self.assertEqual(events[-1]["metadata"], {
            "source": "ollama",
            "reasoning_requested": False,
            "reasoning_applied": False,
        })
        call_stream.assert_called_once_with(
            "gemma4:latest",
            [{"role": "user", "content": "Hello"}],
            {"num_predict": 40},
            None,
        )
        gate.acquire.assert_called_once()
        gate.release.assert_called_once()
        begin.assert_called_once()
        end.assert_called_once()
        self.assertEqual(upstream.close_calls, 1)

    def test_generate_stream_turns_midstream_timeout_into_terminal_error(self):
        payload = granite_payload()
        payload["stream"] = True
        private_telemetry = {
            "model_input_bytes": 10,
            "model_output_bytes": 20,
            "provider": {},
        }
        upstream = FakeOllamaStream(
            ["Partial"],
            failure=OllamaCallError("timeout", private_telemetry),
        )

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                return_value=upstream,
            ),
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=True,
            )

        events = decode_ndjson(response)
        validate_stream(events)
        self.assertEqual([event["type"] for event in events], [
            "started",
            "delta",
            "error",
        ])
        self.assertEqual(events[-1]["error"], {
            "type": "model_timeout",
            "message": "Model request timed out.",
        })
        self.assertNotIn("telemetry", events[-1])
        self.assertEqual(upstream.close_calls, 1)

    def test_generate_stream_returns_json_for_pre_stream_timeout(self):
        payload = granite_payload()
        payload["stream"] = True
        telemetry = {
            "model_input_bytes": 10,
            "model_output_bytes": 0,
            "provider": {},
        }
        gate = Mock()
        gate.acquire.return_value = True

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_GATE", gate),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                side_effect=OllamaCallError("timeout", telemetry),
            ),
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.get_json()["error"]["type"], "model_timeout")
        self.assertEqual(response.get_json()["telemetry"], telemetry)
        begin.assert_called_once()
        end.assert_called_once()
        gate.release.assert_called_once()

    def test_generate_stream_enforces_requested_reasoning_at_termination(self):
        payload = granite_payload()
        payload.update({
            "stream": True,
            "reasoning": {"effort": "medium", "summary": "detailed"},
        })
        upstream = FakeOllamaStream(["Answer"], thinking_present=False)

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                return_value=upstream,
            ),
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=True,
            )

        events = decode_ndjson(response)
        validate_stream(events)
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("no reasoning output", events[-1]["error"]["message"])

    def test_closing_stream_early_closes_ollama_and_releases_capacity(self):
        payload = granite_payload()
        payload["stream"] = True
        upstream = FakeOllamaStream(["unused"])
        gate = Mock()
        gate.acquire.return_value = True

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_GATE", gate),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                return_value=upstream,
            ),
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=False,
            )
            self.assertEqual(upstream.close_calls, 0)
            gate.release.assert_not_called()
            end.assert_not_called()
            response.close()

        begin.assert_called_once()
        end.assert_called_once()
        gate.release.assert_called_once()
        self.assertEqual(upstream.close_calls, 1)

    def test_stream_cleanup_releases_capacity_even_if_upstream_close_fails(self):
        upstream = Mock()
        upstream.close.side_effect = RuntimeError("close failed")
        gate = Mock()
        body = granite_main.GraniteStreamBody(
            "gemma4:latest",
            upstream,
            None,
            gate,
        )

        with (
            patch.object(granite_main, "end_inference") as end,
            self.assertRaisesRegex(RuntimeError, "close failed"),
        ):
            body.close()

        end.assert_called_once()
        gate.release.assert_called_once()
        body.close()
        upstream.close.assert_called_once()
        gate.release.assert_called_once()

    def test_ready_checks_ollama_and_configured_model(self):
        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "ENABLE_IMAGE_INPUT", True),
            patch.object(granite_main, "check_ollama_readiness", return_value=True) as check,
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["dependencies"]["ollama"])
        self.assertEqual(response.get_json()["capabilities"], {
            "supports_streaming": True,
            "supports_image_input": True,
            "image_limits": {
                "max_images": granite_main.MAX_IMAGES_PER_REQUEST,
                "max_image_bytes": granite_main.MAX_IMAGE_BYTES,
                "max_total_bytes": granite_main.MAX_IMAGE_TOTAL_BYTES,
                "max_pixels": granite_main.MAX_IMAGE_PIXELS,
                "max_total_pixels": granite_main.MAX_IMAGE_TOTAL_PIXELS,
            },
        })
        check.assert_called_once_with(
            response.get_json()["model"],
            require_vision=True,
        )

    def test_ready_requires_the_configured_internal_token(self):
        with (
            patch.object(
                granite_main,
                "GRANITE_AUTH_TOKEN",
                "synthetic-granite-token",
            ),
            patch.object(
                granite_main,
                "check_ollama_readiness",
                return_value=True,
            ) as check,
        ):
            rejected = self.client.get("/ready")
            accepted = self.client.get(
                "/ready",
                headers={
                    "X-Rocky-Granite-Token": "synthetic-granite-token",
                },
            )

        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        check.assert_called_once()

    @patch("app.ollama_client.requests.post")
    def test_generate_sends_exact_payload_to_ollama_with_reasoning(
        self,
        mock_post
    ):
        mock_response = make_ollama_response({
            "model": "gemma4:latest",
            "done_reason": "stop",
            "prompt_eval_count": 12,
            "eval_count": 8,
            "total_duration": 4_200_000_000,
            "load_duration": 100_000_000,
            "prompt_eval_duration": 300_000_000,
            "eval_duration": 3_700_000_000,
            "prompt": "must not be telemetry",
            "response": "must not be telemetry",
            "user_id": "must not be telemetry",
            "message": {
                "content": "Olá 🪨",
                "thinking": "Fake private reasoning"
            }
        })
        mock_post.return_value = mock_response

        granite_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Explain résumé 🪨."
                        }
                    ]
                }
            ],
            "max_output_tokens": 500,
            "temperature": 0.7,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.8,
            "reasoning": {
                "effort": "medium",
                "summary": "detailed"
            }
        }

        expected_ollama_payload = {
            "model": "gemma4:latest",
            "messages": [
                {
                    "role": "user",
                    "content": "Explain résumé 🪨."
                }
            ],
            "stream": False,
            "options": {
                "num_predict": 500,
                "temperature": 0.7,
                "top_p": 0.9,
                "frequency_penalty": 0.5,
                "presence_penalty": 0.8
            },
            "think": "medium"
        }

        response = self.client.post(
            "/generate",
            json=granite_payload
        )

        self.assertEqual(response.status_code, 200)

        response_data = response.get_json()

        self.assertEqual(
            response_data["model"],
            "gemma4:latest"
        )
        self.assertEqual(
            response_data["output_text"],
            "Olá 🪨"
        )

        metadata = response_data["metadata"]

        self.assertEqual(metadata["source"], "ollama")
        self.assertTrue(metadata["reasoning_requested"])
        self.assertTrue(metadata["reasoning_applied"])
        self.assertEqual(
            metadata["reasoning_effort"],
            "medium"
        )
        self.assertEqual(
            metadata["reasoning_summary_requested"],
            "detailed"
        )

        # Raw model thinking must not be returned to the API client.
        self.assertNotIn(
            "Fake private reasoning",
            response.get_data(as_text=True)
        )

        telemetry = response_data["telemetry"]
        self.assertEqual(
            telemetry["model_output_bytes"],
            len(mock_response.content),
        )
        self.assertEqual(
            telemetry["provider"],
            {
                "actual_model": "gemma4:latest",
                "stop_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 8,
                "total_duration": 4_200_000_000,
                "load_duration": 100_000_000,
                "prompt_eval_duration": 300_000_000,
                "eval_duration": 3_700_000_000,
            },
        )

        mock_post.assert_called_once()

        _, keyword_arguments = mock_post.call_args
        actual_request_body = keyword_arguments["data"]
        actual_ollama_payload = json.loads(actual_request_body)

        self.assertEqual(
            actual_ollama_payload,
            expected_ollama_payload
        )
        self.assertEqual(
            telemetry["model_input_bytes"],
            len(actual_request_body),
        )
        self.assertGreater(
            len(actual_request_body),
            len(actual_request_body.decode("utf-8")),
        )
        self.assertEqual(
            keyword_arguments["headers"],
            {"Content-Type": "application/json"},
        )

        # "think" belongs at the top level, not in options.
        self.assertNotIn(
            "think",
            actual_ollama_payload["options"]
        )

        # Rocky's summary setting is not an Ollama request field.
        self.assertNotIn(
            "summary",
            actual_ollama_payload
        )

    @patch("app.ollama_client.requests.post")
    def test_generate_omits_options_and_think_when_not_provided(
        self,
        mock_post
    ):
        mock_response = make_ollama_response({
            "message": {
                "content": "Fake Ollama response"
            }
        })
        mock_post.return_value = mock_response

        granite_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hello"
                        }
                    ]
                }
            ]
        }

        expected_ollama_payload = {
            "model": "gemma4:latest",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ],
            "stream": False
        }

        response = self.client.post(
            "/generate",
            json=granite_payload
        )

        self.assertEqual(response.status_code, 200)

        response_data = response.get_json()

        self.assertFalse(
            response_data["metadata"]["reasoning_requested"]
        )
        self.assertFalse(
            response_data["metadata"]["reasoning_applied"]
        )

        mock_post.assert_called_once()

        _, keyword_arguments = mock_post.call_args
        actual_ollama_payload = json.loads(keyword_arguments["data"])

        self.assertEqual(
            actual_ollama_payload,
            expected_ollama_payload
        )
        self.assertNotIn("options", actual_ollama_payload)
        self.assertNotIn("think", actual_ollama_payload)

    @patch("app.ollama_client.requests.post")
    def test_generate_returns_400_and_does_not_call_ollama_when_option_validation_fails(
        self,
        mock_post
    ):
        invalid_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hello"
                        }
                    ]
                }
            ],
            "max_output_tokens": 0
        }

        response = self.client.post(
            "/generate",
            json=invalid_payload
        )

        self.assertEqual(response.status_code, 400)

        response_data = response.get_json()

        self.assertEqual(
            response_data["error"]["type"],
            "bad_request"
        )
        self.assertIn(
            "max_output_tokens",
            response_data["error"]["message"]
        )

        mock_post.assert_not_called()

    @patch("app.ollama_client.requests.post")
    def test_generate_returns_400_and_does_not_call_ollama_for_invalid_reasoning(
        self,
        mock_post
    ):
        invalid_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hello"
                        }
                    ]
                }
            ],
            "reasoning": {
                "effort": "extreme",
                "summary": "detailed"
            }
        }

        response = self.client.post(
            "/generate",
            json=invalid_payload
        )

        self.assertEqual(response.status_code, 400)

        response_data = response.get_json()

        self.assertEqual(
            response_data["error"]["type"],
            "bad_request"
        )
        self.assertIn(
            "reasoning.effort",
            response_data["error"]["message"]
        )

        mock_post.assert_not_called()

    @patch("app.ollama_client.requests.post")
    def test_generate_returns_502_when_reasoning_requested_but_not_returned(
        self,
        mock_post
    ):
        mock_response = make_ollama_response({
            "message": {
                "content": "Answer without a thinking field"
            }
        })
        mock_post.return_value = mock_response

        granite_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Solve this problem."
                        }
                    ]
                }
            ],
            "reasoning": {
                "effort": "medium",
                "summary": "detailed"
            }
        }

        response = self.client.post(
            "/generate",
            json=granite_payload
        )

        self.assertEqual(response.status_code, 502)

        response_data = response.get_json()

        self.assertEqual(
            response_data["error"]["type"],
            "model_error"
        )
        self.assertIn(
            "returned no reasoning output",
            response_data["error"]["message"]
        )
        self.assertEqual(
            response_data["telemetry"]["model_output_bytes"],
            len(mock_response.content),
        )

        # The request reached Ollama, but Ollama did not fulfill
        # the reasoning portion of the contract.
        mock_post.assert_called_once()

    @patch("app.ollama_client.requests.post")
    def test_generate_returns_sanitized_timeout_with_byte_counts(self, mock_post):
        mock_post.side_effect = requests.Timeout("private timeout details")

        response = self.client.post("/generate", json=granite_payload())

        data = response.get_json()
        self.assertEqual((response.status_code, data["error"]["type"]),
                         (504, "model_timeout"))
        self.assertGreater(data["telemetry"]["model_input_bytes"], 0)
        self.assertEqual(data["telemetry"]["model_output_bytes"], 0)
        self.assertNotIn("private timeout details", response.get_data(as_text=True))

    @patch("app.ollama_client.requests.post")
    def test_generate_rejects_non_string_or_empty_model_output(self, mock_post):
        for output in (None, "   "):
            with self.subTest(output=output):
                mock_post.return_value = make_ollama_response({
                    "message": {"content": output},
                })
                response = self.client.post("/generate", json=granite_payload())
                self.assertEqual(
                    (response.status_code, response.get_json()["error"]["type"]),
                    (502, "model_error"),
                )


if __name__ == "__main__":
    unittest.main()
