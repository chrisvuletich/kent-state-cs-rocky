from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from urllib3.exceptions import ReadTimeoutError


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "granite_stream_client.py"

spec = importlib.util.spec_from_file_location("granite_stream_client_tests", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load Granite stream client.")
client = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(API_ROCKY_DIR))
try:
    spec.loader.exec_module(client)
finally:
    sys.path.remove(str(API_ROCKY_DIR))


def encode_event(event):
    return json.dumps(event, separators=(",", ":")).encode("utf-8") + b"\n"


class FakeResponse:
    def __init__(
        self,
        chunks=(),
        *,
        status_code=200,
        content_type="application/x-ndjson",
    ):
        self.chunks = list(chunks)
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.close_calls = 0

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.close_calls += 1


def successful_body():
    return b"".join((
        encode_event({"type": "started", "model": "gemma4:latest"}),
        encode_event({"type": "delta", "text": "Hello "}),
        encode_event({"type": "delta", "text": "Rocky!"}),
        encode_event({
            "type": "completed",
            "telemetry": {
                "model_input_bytes": 100,
                "model_output_bytes": 50,
                "provider": {"eval_count": 2},
                "queue": {
                    "status": "not_queued",
                    "initial_position": 0,
                    "depth_on_arrival": 0,
                    "wait_ms": 0,
                    "capacity": 12,
                    "queued_bytes_on_arrival": 0,
                },
            },
            "metadata": {"source": "ollama"},
        }),
    ))


class GraniteStreamClientTests(unittest.TestCase):
    def open(self, response):
        with patch.object(client.requests, "post", return_value=response) as post:
            stream = client.open_granite_stream(
                "http://granite.test/generate",
                {"model": "gemma4:latest", "input": []},
                {"X-Rocky-Granite-Token": "secret"},
                170,
                "gemma4:latest",
            )
        return stream, post

    def test_successful_stream_is_incremental_strict_and_single_use(self):
        body = successful_body()
        split = body.index(b"Rocky") + 2
        response = FakeResponse([body[:split], body[split:]])

        stream, post = self.open(response)

        events = list(stream)
        self.assertEqual([event["type"] for event in events], [
            "delta",
            "delta",
            "completed",
        ])
        self.assertEqual(stream.model, "gemma4:latest")
        self.assertEqual(stream.received_bytes, len(body))
        self.assertEqual(response.close_calls, 1)
        self.assertTrue(post.call_args.kwargs["stream"])
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        with self.assertRaisesRegex(RuntimeError, "only be consumed once"):
            list(stream)

    def test_blank_queue_heartbeats_are_surfaced_before_started(self):
        body = b"\n\r\n\n" + successful_body()
        response = FakeResponse([body[:2], body[2:]])

        stream, _post = self.open(response)

        items = list(stream)
        self.assertEqual(len(items), 6)
        self.assertTrue(all(
            item is client.GRANITE_STREAM_HEARTBEAT
            for item in items[:3]
        ))
        events = items[3:]
        self.assertEqual([event["type"] for event in events], [
            "delta",
            "delta",
            "completed",
        ])
        self.assertEqual(stream.received_bytes, len(body))
        self.assertEqual(response.close_calls, 1)

    def test_active_heartbeat_is_surfaced_after_started(self):
        body = b"".join((
            encode_event({"type": "started", "model": "gemma4:latest"}),
            b"\n",
            encode_event({"type": "delta", "text": "Answer"}),
            encode_event({
                "type": "completed",
                "telemetry": {},
                "metadata": {},
            }),
        ))
        response = FakeResponse([body])

        stream, _post = self.open(response)
        items = list(stream)

        self.assertIs(items[0], client.GRANITE_STREAM_HEARTBEAT)
        self.assertEqual([item["type"] for item in items[1:]], [
            "delta",
            "completed",
        ])

    def test_open_is_lazy_and_can_close_before_the_first_event(self):
        response = FakeResponse([successful_body()])

        stream, _post = self.open(response)

        self.assertFalse(hasattr(response, "chunk_size"))
        self.assertEqual(stream.received_bytes, 0)
        stream.close()
        self.assertEqual(response.close_calls, 1)

    def test_terminal_queue_error_before_started_is_a_valid_stream(self):
        terminal_event = {
            "type": "error",
            "error": {
                "type": "model_busy",
                "message": "The model is busy. Try again shortly.",
            },
            "telemetry": {
                "queue": {
                    "status": "timed_out",
                    "initial_position": 1,
                    "depth_on_arrival": 0,
                    "wait_ms": 1000,
                    "capacity": 12,
                    "queued_bytes_on_arrival": 0,
                },
            },
        }
        body = b"\n\n" + encode_event(terminal_event)
        response = FakeResponse([body])

        stream, _post = self.open(response)

        items = list(stream)
        self.assertEqual(items[-1], terminal_event)
        self.assertTrue(all(
            item is client.GRANITE_STREAM_HEARTBEAT
            for item in items[:-1]
        ))
        self.assertEqual(stream.model, "gemma4:latest")
        self.assertEqual(response.close_calls, 1)

    def test_terminal_queue_error_rejects_trailing_events(self):
        body = b"".join((
            encode_event({
                "type": "error",
                "error": {
                    "type": "model_busy",
                    "message": "The model is busy. Try again shortly.",
                },
            }),
            encode_event({"type": "delta", "text": "too late"}),
        ))
        response = FakeResponse([body])
        stream, _post = self.open(response)

        with self.assertRaises(client.GraniteStreamError) as raised:
            list(stream)

        self.assertEqual(raised.exception.kind, "bad_response")
        self.assertEqual(response.close_calls, 1)

    def test_terminal_event_rejects_non_object_telemetry(self):
        for event in (
            {
                "type": "error",
                "error": {"type": "model_error", "message": "Failed."},
                "telemetry": [],
            },
            {"type": "cancelled", "telemetry": []},
        ):
            with self.subTest(event=event):
                response = FakeResponse([encode_event(event)])
                stream, _post = self.open(response)
                with self.assertRaises(client.GraniteStreamError) as raised:
                    list(stream)
                self.assertEqual(raised.exception.kind, "bad_response")
                self.assertEqual(response.close_calls, 1)

    def test_open_maps_bounded_granite_json_errors_and_closes(self):
        cases = (
            (400, "bad_request", "bad_request"),
            (503, "model_busy", "busy"),
            (503, "service_unavailable", "network"),
            (503, None, "network"),
            (504, "model_timeout", "timeout"),
            (502, "model_error", "network"),
        )
        for status, granite_type, expected_kind in cases:
            with self.subTest(status=status):
                body = json.dumps({
                    "error": {
                        "type": granite_type,
                        "message": "Safe message",
                    },
                    "telemetry": {"provider": {}},
                }).encode("utf-8")
                response = FakeResponse([body], status_code=status)
                with (
                    patch.object(client.requests, "post", return_value=response),
                    self.assertRaises(client.GraniteStreamError) as raised,
                ):
                    client.open_granite_stream(
                        "http://granite.test/generate",
                        {},
                        {},
                        170,
                        "gemma4:latest",
                    )

                self.assertEqual(raised.exception.kind, expected_kind)
                self.assertEqual(response.close_calls, 1)
                self.assertEqual(
                    raised.exception.message,
                    "Safe message" if expected_kind == "bad_request" else None,
                )

    def test_open_rejects_wrong_media_type_first_event_or_model(self):
        wrong_media_type = FakeResponse(
            [successful_body()],
            content_type="application/json",
        )
        with (
            patch.object(client.requests, "post", return_value=wrong_media_type),
            self.assertRaises(client.GraniteStreamError) as raised,
        ):
            client.open_granite_stream(
                "http://granite.test/generate",
                {},
                {},
                170,
                "gemma4:latest",
            )
        self.assertEqual(raised.exception.kind, "bad_response")
        self.assertEqual(wrong_media_type.close_calls, 1)

        invalid_event_streams = (
            FakeResponse([encode_event({"type": "delta", "text": "early"})]),
            FakeResponse([
                encode_event({"type": "started", "model": "other-model"})
            ]),
        )
        for response in invalid_event_streams:
            with self.subTest(response=response):
                stream, _post = self.open(response)
                with self.assertRaises(client.GraniteStreamError) as raised:
                    list(stream)
            self.assertEqual(raised.exception.kind, "bad_response")
            self.assertEqual(response.close_calls, 1)

    def test_midstream_timeout_is_classified_and_provider_details_are_hidden(self):
        wrapped_timeout = requests.ConnectionError(
            ReadTimeoutError(None, "/generate", "private details")
        )
        response = FakeResponse([
            encode_event({"type": "started", "model": "gemma4:latest"}),
            encode_event({"type": "delta", "text": "Partial"}),
            wrapped_timeout,
        ])
        stream, _post = self.open(response)

        iterator = iter(stream)
        self.assertEqual(next(iterator)["text"], "Partial")
        with self.assertRaises(client.GraniteStreamError) as raised:
            next(iterator)

        self.assertEqual(raised.exception.kind, "timeout")
        self.assertNotIn("private details", str(raised.exception))
        self.assertEqual(response.close_calls, 1)

    def test_stream_rejects_trailing_events_and_missing_delta(self):
        invalid_bodies = (
            b"".join((
                encode_event({"type": "started", "model": "gemma4:latest"}),
                encode_event({
                    "type": "completed",
                    "telemetry": {},
                    "metadata": {},
                }),
            )),
            b"".join((
                successful_body(),
                encode_event({"type": "delta", "text": "too late"}),
            )),
            b"".join((
                encode_event({"type": "started", "model": "gemma4:latest"}),
                b"not-json\n",
            )),
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                response = FakeResponse([body])
                stream, _post = self.open(response)
                with self.assertRaises(client.GraniteStreamError) as raised:
                    list(stream)
                self.assertEqual(raised.exception.kind, "bad_response")
                self.assertEqual(response.close_calls, 1)

    def test_stream_line_and_body_limits_fail_closed(self):
        for setting in ("_MAX_STREAM_LINE_BYTES", "_MAX_STREAM_BODY_BYTES"):
            response = FakeResponse([
                encode_event({"type": "started", "model": "gemma4:latest"}),
                b"123456789",
            ])
            with (
                self.subTest(setting=setting),
                patch.object(client, setting, 8),
                patch.object(client.requests, "post", return_value=response),
                self.assertRaises(client.GraniteStreamError) as raised,
            ):
                stream = client.open_granite_stream(
                    "http://granite.test/generate",
                    {},
                    {},
                    170,
                    "gemma4:latest",
                )
                list(stream)
            self.assertEqual(raised.exception.kind, "bad_response")
            self.assertEqual(response.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
