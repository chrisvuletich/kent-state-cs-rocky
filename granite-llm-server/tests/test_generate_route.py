import base64
import hashlib
import json
import threading
import time
import unittest
from unittest.mock import Mock, call, patch

import requests

import app.main as granite_main
from app.inference_queue import (
    ADMITTED,
    QUEUE_FULL,
    QUEUE_MEMORY_FULL,
    TIMED_OUT,
    WAITING,
    InferenceQueue,
    QueueTicketSnapshot,
)
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


def make_admission(
    status=ADMITTED,
    *,
    snapshot_status=None,
    initial_position=None,
):
    ticket = Mock()
    ticket.wait.return_value = status
    final_status = snapshot_status or status
    if initial_position is None and final_status == ADMITTED:
        initial_position = 0
    ticket.snapshot.return_value = QueueTicketSnapshot(
        status=final_status,
        initial_position=initial_position,
        depth_on_arrival=0,
        queued_bytes_on_arrival=0,
        wait_ms=0,
        capacity=12,
        released=False,
    )
    queue = Mock()
    queue.request_slot.return_value = ticket
    return queue, ticket


def wait_for_queue_depth(queue, expected, timeout=1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if queue.snapshot().waiting_requests == expected:
            return True
        time.sleep(0.001)
    return queue.snapshot().waiting_requests == expected


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

    def test_generate_returns_safe_retryable_queue_rejections(self):
        request_body = encode_json(granite_payload())
        for status, expected_reason in (
            (QUEUE_FULL, "queue_full"),
            (QUEUE_MEMORY_FULL, "queue_memory_full"),
            (TIMED_OUT, "queue_timeout"),
        ):
            with self.subTest(status=status):
                queue, ticket = make_admission(status)
                with patch.object(granite_main, "INFERENCE_QUEUE", queue):
                    response = self.client.post(
                        "/generate",
                        data=request_body,
                        content_type="application/json",
                    )

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.get_json()["error"], {
                    "type": "model_busy",
                    "message": "The model is busy. Try again shortly.",
                    "queue_reason": expected_reason,
                })
                self.assertEqual(response.get_json()["telemetry"]["queue"], {
                    "status": status,
                    "depth_on_arrival": 0,
                    "wait_ms": 0,
                    "capacity": 12,
                    "queued_bytes_on_arrival": 0,
                })
                self.assertEqual(response.headers["Retry-After"], "2")
                queue.request_slot.assert_called_once_with(len(request_body))
                ticket.wait.assert_called_once_with()
                ticket.release.assert_not_called()

    def test_buffered_generation_releases_its_admitted_ticket(self):
        request_body = encode_json(granite_payload())
        queue, ticket = make_admission()
        result = {
            "content": "Hello back.",
            "thinking_present": False,
            "telemetry": {},
        }

        def call_ollama(*_args):
            ticket.release.assert_not_called()
            return result

        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat",
                side_effect=call_ollama,
            ),
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post(
                "/generate",
                data=request_body,
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        queue.request_slot.assert_called_once_with(len(request_body))
        ticket.wait.assert_called_once_with()
        begin.assert_called_once_with()
        end.assert_called_once_with()
        ticket.release.assert_called_once_with()

    def test_buffered_provider_failure_releases_its_admitted_ticket(self):
        queue, ticket = make_admission()
        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat",
                side_effect=OllamaCallError("timeout", {}),
            ),
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post("/generate", json=granite_payload())

        self.assertEqual(response.status_code, 504)
        begin.assert_called_once_with()
        end.assert_called_once_with()
        ticket.release.assert_called_once_with()

    def test_buffered_failure_paths_leave_capacity_for_the_next_request(self):
        cases = (
            (OllamaCallError("timeout", {}), 504),
            (OllamaCallError("bad_response", {}), 502),
            (RuntimeError("unexpected provider failure"), 502),
        )
        successful_result = {
            "content": "Recovered.",
            "thinking_present": False,
            "telemetry": {},
        }

        for failure, expected_status in cases:
            with self.subTest(failure=type(failure).__name__):
                queue = InferenceQueue(
                    max_active_requests=1,
                    max_waiting_requests=1,
                    max_queued_bytes=4096,
                    wait_timeout_seconds=1,
                )
                with (
                    patch.object(granite_main, "INFERENCE_QUEUE", queue),
                    patch.object(
                        granite_main,
                        "call_ollama_chat",
                        side_effect=[failure, successful_result],
                    ),
                ):
                    failed = self.client.post(
                        "/generate",
                        json=granite_payload("first"),
                    )
                    recovered = self.client.post(
                        "/generate",
                        json=granite_payload("second"),
                    )

                self.assertEqual(failed.status_code, expected_status)
                self.assertEqual(recovered.status_code, 200)
                self.assertEqual(
                    recovered.get_json()["output_text"],
                    "Recovered.",
                )
                self.assertEqual(queue.snapshot().active_requests, 0)
                self.assertEqual(queue.snapshot().waiting_requests, 0)

    def test_buffered_request_waits_for_the_active_route_to_finish(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=2,
            max_queued_bytes=4096,
            wait_timeout_seconds=2,
        )
        first_started = threading.Event()
        release_first = threading.Event()
        call_order = []
        responses = {}

        def call_ollama(_model, messages, _options, _think):
            text = messages[0]["content"]
            call_order.append(text)
            if text == "first":
                first_started.set()
                release_first.wait(timeout=2)
            return {
                "content": f"response to {text}",
                "thinking_present": False,
                "telemetry": {},
            }

        def post_message(name):
            with flask_app.test_client() as client:
                responses[name] = client.post(
                    "/generate",
                    json=granite_payload(name),
                ).status_code

        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat",
                side_effect=call_ollama,
            ),
        ):
            first = threading.Thread(target=post_message, args=("first",))
            second = threading.Thread(target=post_message, args=("second",))
            first.start()
            self.assertTrue(first_started.wait(timeout=1))
            second.start()
            deadline = time.monotonic() + 1
            while (
                queue.snapshot().waiting_requests != 1
                and time.monotonic() < deadline
            ):
                time.sleep(0.001)
            self.assertEqual(queue.snapshot().waiting_requests, 1)
            self.assertEqual(call_order, ["first"])
            release_first.set()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(responses, {"first": 200, "second": 200})
        self.assertEqual(call_order, ["first", "second"])
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)

    def test_six_validated_requests_complete_fifo_with_one_active_inference(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=6,
            max_queued_bytes=64 * 1024,
            wait_timeout_seconds=2,
        )
        first_started = threading.Event()
        release_first = threading.Event()
        state_lock = threading.Lock()
        call_order = []
        responses = {}
        worker_errors = []
        active_calls = 0
        maximum_active_calls = 0

        def call_ollama(_model, messages, _options, _think):
            nonlocal active_calls, maximum_active_calls
            text = messages[0]["content"]
            with state_lock:
                call_order.append(text)
                active_calls += 1
                maximum_active_calls = max(maximum_active_calls, active_calls)
            try:
                if text == "burst-0":
                    first_started.set()
                    if not release_first.wait(timeout=2):
                        raise RuntimeError("test did not release first request")
                return {
                    "content": f"response to {text}",
                    "thinking_present": False,
                    "telemetry": {},
                }
            finally:
                with state_lock:
                    active_calls -= 1

        def post_message(index):
            try:
                with flask_app.test_client() as client:
                    response = client.post(
                        "/generate",
                        json=granite_payload(f"burst-{index}"),
                    )
                    responses[index] = (
                        response.status_code,
                        response.get_json(),
                    )
            except Exception as error:  # pragma: no cover - asserted below
                with state_lock:
                    worker_errors.append(
                        f"request {index}: {type(error).__name__}"
                    )

        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat",
                side_effect=call_ollama,
            ),
        ):
            threads = [
                threading.Thread(target=post_message, args=(index,))
                for index in range(6)
            ]
            threads[0].start()
            self.assertTrue(first_started.wait(timeout=1))
            for index in range(1, 6):
                threads[index].start()
                self.assertTrue(wait_for_queue_depth(queue, index))

            self.assertEqual(queue.snapshot().active_requests, 1)
            self.assertEqual(queue.snapshot().waiting_requests, 5)
            release_first.set()
            for thread in threads:
                thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(worker_errors, [])
        self.assertEqual(maximum_active_calls, 1)
        self.assertEqual(call_order, [f"burst-{index}" for index in range(6)])
        self.assertEqual(
            [responses[index][0] for index in range(6)],
            [200] * 6,
        )
        self.assertEqual(
            [
                responses[index][1]["telemetry"]["queue"]["status"]
                for index in range(6)
            ],
            ["not_queued", *(["admitted"] * 5)],
        )
        self.assertEqual(
            [
                responses[index][1]["telemetry"]["queue"]["initial_position"]
                for index in range(6)
            ],
            list(range(6)),
        )
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)

    def test_buffered_and_streaming_routes_share_fifo_admission_order(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=3,
            max_queued_bytes=4096,
            wait_timeout_seconds=2,
        )
        first_started = threading.Event()
        release_first = threading.Event()
        call_order = []
        responses = {}

        def call_buffered(_model, messages, _options, _think):
            text = messages[0]["content"]
            call_order.append(text)
            if text == "first":
                first_started.set()
                release_first.wait(timeout=2)
            return {
                "content": f"response to {text}",
                "thinking_present": False,
                "telemetry": {},
            }

        def call_streamed(_model, messages, _options, _think):
            text = messages[0]["content"]
            call_order.append(text)
            return FakeOllamaStream([f"response to {text}"])

        def post_message(name, *, stream=False):
            payload = granite_payload(name)
            if stream:
                payload["stream"] = True
            with flask_app.test_client() as client:
                responses[name] = client.post(
                    "/generate",
                    json=payload,
                    buffered=True,
                ).status_code

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "QUEUE_HEARTBEAT_SECONDS", 0.01),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat",
                side_effect=call_buffered,
            ),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                side_effect=call_streamed,
            ),
        ):
            first = threading.Thread(
                target=post_message,
                args=("first",),
            )
            second = threading.Thread(
                target=post_message,
                args=("second",),
                kwargs={"stream": True},
            )
            third = threading.Thread(
                target=post_message,
                args=("third",),
            )
            first.start()
            self.assertTrue(first_started.wait(timeout=1))
            second.start()
            self.assertTrue(wait_for_queue_depth(queue, 1))
            third.start()
            self.assertTrue(wait_for_queue_depth(queue, 2))
            release_first.set()
            for thread in (first, second, third):
                thread.join(timeout=2)

        self.assertTrue(all(not thread.is_alive() for thread in (first, second, third)))
        self.assertEqual(responses, {"first": 200, "second": 200, "third": 200})
        self.assertEqual(call_order, ["first", "second", "third"])
        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)

    def test_begin_inference_failure_does_not_leak_queue_capacity(self):
        queue, ticket = make_admission()
        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "begin_inference",
                side_effect=RuntimeError("state failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "state failure"),
        ):
            self.client.post("/generate", json=granite_payload())

        ticket.release.assert_called_once_with()

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
        queue = Mock()
        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
        ):
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("stream", response.get_json()["error"]["message"])
        call_stream.assert_not_called()
        queue.request_slot.assert_not_called()

    def test_generate_streams_normalized_ndjson_and_holds_capacity_until_done(self):
        payload = granite_payload()
        payload.update({
            "stream": True,
            "max_output_tokens": 40,
        })
        upstream = FakeOllamaStream(["Hello ", "Rocky!"])
        queue, ticket = make_admission()

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
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
        self.assertEqual(
            {
                key: value
                for key, value in events[-1]["telemetry"].items()
                if key != "queue"
            },
            upstream.telemetry,
        )
        self.assertEqual(events[-1]["telemetry"]["queue"]["status"], "not_queued")
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
        queue.request_slot.assert_called_once()
        ticket.wait.assert_called_once_with(poll_seconds=0)
        ticket.release.assert_called_once_with()
        begin.assert_called_once()
        end.assert_called_once()
        self.assertEqual(upstream.close_calls, 1)

    def test_active_stream_emits_heartbeats_while_ollama_is_silent(self):
        release_upstream = threading.Event()

        class SilentOllamaStream(FakeOllamaStream):
            def __iter__(self):
                if not release_upstream.wait(timeout=1):
                    raise RuntimeError("test did not release upstream")
                yield "Answer"

        upstream = SilentOllamaStream(thinking_present=True)
        _queue, ticket = make_admission()
        body = granite_main.iter_stream_events(
            "gemma4:latest",
            upstream,
            {"effort": "medium", "summary": "detailed"},
            0.01,
            ticket,
        )

        started = json.loads(next(body))
        heartbeat = next(body)
        release_upstream.set()
        remaining = [json.loads(line) for line in body if line.strip()]

        self.assertEqual(started, {
            "type": "started",
            "model": "gemma4:latest",
        })
        self.assertEqual(heartbeat, "\n")
        self.assertEqual([event["type"] for event in remaining], [
            "delta",
            "completed",
        ])

    def test_queued_stream_emits_heartbeats_until_it_is_admitted(self):
        payload = granite_payload()
        payload["stream"] = True
        upstream = FakeOllamaStream(["Queued answer"])
        queue, ticket = make_admission(initial_position=1)
        ticket.wait.side_effect = [WAITING, WAITING, WAITING, ADMITTED]

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "QUEUE_HEARTBEAT_SECONDS", 0.25),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
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

        response_body = response.get_data()
        events = decode_ndjson(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response_body.startswith(b"\n\n\n"))
        self.assertEqual([event["type"] for event in events], [
            "started",
            "delta",
            "completed",
        ])
        self.assertEqual(events[-1]["telemetry"]["queue"], {
            "status": "admitted",
            "initial_position": 1,
            "depth_on_arrival": 0,
            "wait_ms": 0,
            "capacity": 12,
            "queued_bytes_on_arrival": 0,
        })
        self.assertEqual(ticket.wait.call_args_list, [
            call(poll_seconds=0),
            call(poll_seconds=0.25),
            call(poll_seconds=0.25),
            call(poll_seconds=0.25),
        ])
        call_stream.assert_called_once()
        begin.assert_called_once_with()
        end.assert_called_once_with()
        ticket.cancel.assert_not_called()
        ticket.release.assert_called_once_with()

    def test_stream_queue_rejection_remains_json_before_response_commit(self):
        payload = granite_payload()
        payload["stream"] = True
        queue, ticket = make_admission(QUEUE_FULL)

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
        ):
            response = self.client.post("/generate", json=payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(
            response.get_json()["error"]["queue_reason"],
            "queue_full",
        )
        ticket.wait.assert_called_once_with(poll_seconds=0)
        ticket.cancel.assert_not_called()
        ticket.release.assert_not_called()
        call_stream.assert_not_called()

    @patch.object(granite_main, "check_ollama_readiness", return_value=True)
    def test_readiness_reports_only_aggregate_queue_state(self, _check):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=2,
            max_queued_bytes=4096,
            wait_timeout_seconds=30,
        )
        active = queue.request_slot(100)
        waiting = queue.request_slot(200)

        with patch.object(granite_main, "INFERENCE_QUEUE", queue):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["queue"], {
            "active_requests": 1,
            "waiting_requests": 1,
            "queued_bytes": 200,
            "max_active_requests": 1,
            "max_waiting_requests": 2,
            "max_queued_bytes": 4096,
        })
        active.release()
        waiting.release()

    def test_queued_stream_timeout_is_a_terminal_model_busy_event(self):
        payload = granite_payload()
        payload["stream"] = True
        queue, ticket = make_admission(
            snapshot_status=TIMED_OUT,
            initial_position=1,
        )
        ticket.wait.side_effect = [WAITING, TIMED_OUT]

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
            patch.object(granite_main, "begin_inference") as begin,
            patch.object(granite_main, "end_inference") as end,
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_data().startswith(b"\n"))
        events = decode_ndjson(response)
        validate_stream(events)
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"], {
            "type": "model_busy",
            "message": "The model is busy. Try again shortly.",
        })
        self.assertEqual(events[0]["telemetry"]["queue"]["status"], "timed_out")
        self.assertEqual(events[0]["telemetry"]["queue"]["initial_position"], 1)
        call_stream.assert_not_called()
        begin.assert_not_called()
        end.assert_not_called()
        ticket.cancel.assert_called_once_with()
        ticket.release.assert_called_once_with()

    def test_queued_stream_provider_failure_releases_admitted_capacity(self):
        payload = granite_payload()
        payload["stream"] = True
        queue, ticket = make_admission(initial_position=1)
        ticket.wait.side_effect = [WAITING, ADMITTED]

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "call_ollama_chat_stream",
                side_effect=OllamaCallError("timeout", {}),
            ),
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
        self.assertEqual(events[0]["type"], "error")
        self.assertEqual(events[0]["error"], {
            "type": "model_timeout",
            "message": "Model request timed out.",
        })
        self.assertEqual(events[0]["telemetry"]["queue"]["status"], "admitted")
        self.assertEqual(events[0]["telemetry"]["queue"]["initial_position"], 1)
        begin.assert_called_once_with()
        end.assert_called_once_with()
        ticket.cancel.assert_not_called()
        ticket.release.assert_called_once_with()

    def test_closing_a_waiting_stream_cancels_its_queue_ticket(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=2,
            max_queued_bytes=4096,
            wait_timeout_seconds=2,
        )
        active = queue.request_slot(1)
        payload = granite_payload()
        payload["stream"] = True

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=False,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(queue.snapshot().waiting_requests, 1)
            response.close()

        self.assertEqual(queue.snapshot().waiting_requests, 0)
        self.assertEqual(queue.snapshot().active_requests, 1)
        call_stream.assert_not_called()
        active.release()
        self.assertEqual(queue.snapshot().active_requests, 0)

    def test_closing_a_just_admitted_stream_releases_without_starting_ollama(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=2,
            max_queued_bytes=4096,
            wait_timeout_seconds=2,
        )
        active = queue.request_slot(1)
        payload = granite_payload()
        payload["stream"] = True

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(granite_main, "call_ollama_chat_stream") as call_stream,
            patch.object(granite_main, "begin_inference") as begin,
        ):
            response = self.client.post(
                "/generate",
                json=payload,
                buffered=False,
            )
            self.assertEqual(queue.snapshot().waiting_requests, 1)
            active.release()
            self.assertEqual(queue.snapshot().active_requests, 1)
            response.close()

        self.assertEqual(queue.snapshot().active_requests, 0)
        self.assertEqual(queue.snapshot().waiting_requests, 0)
        call_stream.assert_not_called()
        begin.assert_not_called()

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
        self.assertEqual(events[-1]["telemetry"]["model_input_bytes"], 10)
        self.assertEqual(events[-1]["telemetry"]["model_output_bytes"], 20)
        self.assertEqual(events[-1]["telemetry"]["queue"]["status"], "not_queued")
        self.assertEqual(upstream.close_calls, 1)

    def test_generate_stream_returns_json_for_pre_stream_timeout(self):
        payload = granite_payload()
        payload["stream"] = True
        telemetry = {
            "model_input_bytes": 10,
            "model_output_bytes": 0,
            "provider": {},
        }
        queue, ticket = make_admission()

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
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
        response_telemetry = response.get_json()["telemetry"]
        self.assertEqual(
            {key: value for key, value in response_telemetry.items() if key != "queue"},
            telemetry,
        )
        self.assertEqual(response_telemetry["queue"]["status"], "not_queued")
        begin.assert_called_once()
        end.assert_called_once()
        ticket.release.assert_called_once_with()

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
        queue, ticket = make_admission()

        with (
            patch.object(granite_main, "ENABLE_STREAMING", True),
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
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
            ticket.release.assert_not_called()
            end.assert_not_called()
            response.close()

        begin.assert_called_once()
        end.assert_called_once()
        ticket.release.assert_called_once_with()
        self.assertEqual(upstream.close_calls, 1)

    def test_stream_cleanup_releases_capacity_even_if_upstream_close_fails(self):
        upstream = Mock()
        upstream.close.side_effect = RuntimeError("close failed")
        ticket = Mock()
        body = granite_main.GraniteStreamBody(
            "gemma4:latest",
            upstream,
            None,
            ticket,
            0.1,
        )

        with (
            patch.object(granite_main, "end_inference") as end,
            self.assertRaisesRegex(RuntimeError, "close failed"),
        ):
            body.close()

        end.assert_called_once()
        ticket.release.assert_called_once_with()
        body.close()
        upstream.close.assert_called_once()
        ticket.release.assert_called_once_with()

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
        self.assertEqual(response.get_json()["timeouts"], {
            "ollama_request_seconds": granite_main.OLLAMA_TIMEOUT_SECONDS,
            "queue_wait_seconds": granite_main.QUEUE_WAIT_SECONDS,
            "heartbeat_seconds": granite_main.QUEUE_HEARTBEAT_SECONDS,
        })
        check.assert_called_once_with(
            response.get_json()["model"],
            require_vision=True,
        )

    def test_ready_remains_healthy_while_inference_queue_is_saturated(self):
        queue = InferenceQueue(
            max_active_requests=1,
            max_waiting_requests=1,
            max_queued_bytes=1024,
            wait_timeout_seconds=30,
        )
        active = queue.request_slot(1)
        waiting = queue.request_slot(1)

        with (
            patch.object(granite_main, "INFERENCE_QUEUE", queue),
            patch.object(
                granite_main,
                "check_ollama_readiness",
                return_value=True,
            ),
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(queue.snapshot().active_requests, 1)
        self.assertEqual(queue.snapshot().waiting_requests, 1)
        waiting.cancel()
        active.release()

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
