from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from mongita import MongitaClientMemory
from openai.types.responses import ResponseStreamEvent
from pydantic import TypeAdapter


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "api.py"
IMAGE_INPUT_FIXTURE = ROOT / "run-test" / "fixtures" / "responses_image_input.json"
STREAM_EVENT_ADAPTER = TypeAdapter(ResponseStreamEvent)


def encode_ndjson_events(events):
    return [
        json.dumps(event, separators=(",", ":")).encode("utf-8") + b"\n"
        for event in events
    ]


def make_granite_event_stream(api, events):
    upstream_response = Mock()
    upstream_response.close = Mock()
    stream = api.GraniteEventStream(
        upstream_response,
        iter(encode_ndjson_events(events)),
        [0],
        api.INFERENCE_MODEL,
    )
    return stream, upstream_response


def decode_sse_events(response):
    events = []
    for frame in response.get_data(as_text=True).strip().split("\n\n"):
        lines = frame.splitlines()
        if len(lines) != 2:
            raise AssertionError(f"Invalid SSE frame: {frame!r}")
        event_type = lines[0].removeprefix("event: ")
        event = json.loads(lines[1].removeprefix("data: "))
        if event.get("type") != event_type:
            raise AssertionError("SSE event name differs from payload type.")
        events.append(event)
    return events


def load_api_with_test_initialization_seam(environment_overrides=None):
    spec = importlib.util.spec_from_file_location(
        "api_rocky_route_contract",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load api-rocky for route contract tests.")

    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(API_ROCKY_DIR))
    environment = {
        "ROCKY_APP_ENV": "test",
        "ROCKY_CHAT_API_KEY": "",
        "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE": "10",
        "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE": "120",
        "ROCKY_ENABLE_STREAMING": "false",
        "ROCKY_ENABLE_IMAGE_INPUT": "false",
        "ROCKY_MAX_IMAGES_PER_REQUEST": "4",
        "ROCKY_MAX_IMAGE_BYTES": str(4 * 1024 * 1024),
        "ROCKY_MAX_IMAGE_TOTAL_BYTES": str(6 * 1024 * 1024),
        "ROCKY_MAX_IMAGE_PIXELS": "20000000",
        "ROCKY_TELEMETRY_ENABLED": "false",
        "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
    }
    environment.update(environment_overrides or {})
    try:
        with patch.dict(
            os.environ,
            environment,
        ):
            spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(API_ROCKY_DIR))
    return module


class ApiRockyRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_api_with_test_initialization_seam()
        cls.api.app.config["TESTING"] = True
        cls.client = cls.api.app.test_client()

    def test_runtime_configuration_parsers_fail_with_setting_names(self):
        invalid_cases = (
            ("ROCKY_CHAT_API_PORT", "abc", self.api._env_int, (5003, 1, 65535)),
            (
                "ROCKY_GRANITE_TIMEOUT_SECONDS",
                "nan",
                self.api._env_float,
                (170, 0, False),
            ),
            (
                "ROCKY_REQUIRE_REQUEST_LOGGING",
                "yes",
                self.api._env_bool,
                (False,),
            ),
            (
                "ROCKY_GRANITE_URL",
                "http://user:password@granite.example:5002/generate",
                self.api._env_http_url,
                ("http://127.0.0.1:5002/generate",),
            ),
        )
        for name, value, parser, arguments in invalid_cases:
            with self.subTest(name=name):
                with (
                    patch.dict(os.environ, {name: value}),
                    self.assertRaisesRegex(RuntimeError, name),
                ):
                    parser(name, *arguments)

    def test_runtime_service_urls_reject_queries_and_fragments(self):
        for value in (
            "http://granite.example:5002/generate?tenant=one",
            "http://granite.example:5002/generate#internal",
        ):
            with self.subTest(value=value):
                with (
                    patch.dict(os.environ, {"ROCKY_GRANITE_URL": value}),
                    self.assertRaisesRegex(RuntimeError, "ROCKY_GRANITE_URL"),
                ):
                    self.api._env_http_url(
                        "ROCKY_GRANITE_URL",
                        "http://127.0.0.1:5002/generate",
                    )

    def test_rate_limit_policy_defaults_and_validation(self):
        self.assertEqual(self.api.RESPONSES_RATE_LIMIT_PER_MINUTE, 10)
        self.assertEqual(self.api.MODELS_RATE_LIMIT_PER_MINUTE, 120)

        invalid_values = (
            ("ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE", "0"),
            ("ROCKY_MODELS_RATE_LIMIT_PER_MINUTE", "not-an-integer"),
        )
        for name, value in invalid_values:
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, name):
                    load_api_with_test_initialization_seam({name: value})

    def test_phase_zero_feature_flags_default_off_with_bounded_image_limits(self):
        self.assertFalse(self.api.ENABLE_STREAMING)
        self.assertFalse(self.api.ENABLE_IMAGE_INPUT)
        self.assertEqual(self.api.MAX_IMAGES_PER_REQUEST, 4)
        self.assertEqual(self.api.MAX_IMAGE_BYTES, 4 * 1024 * 1024)
        self.assertEqual(self.api.MAX_IMAGE_TOTAL_BYTES, 6 * 1024 * 1024)
        self.assertEqual(self.api.MAX_IMAGE_PIXELS, 20_000_000)
        self.assertEqual(self.api.MAX_IMAGE_TOTAL_PIXELS, 40_000_000)

    def test_phase_zero_feature_configuration_fails_closed(self):
        invalid_values = (
            ("ROCKY_ENABLE_STREAMING", "yes"),
            ("ROCKY_ENABLE_IMAGE_INPUT", "1"),
            ("ROCKY_MAX_IMAGES_PER_REQUEST", "0"),
            ("ROCKY_MAX_IMAGES_PER_REQUEST", "17"),
            ("ROCKY_MAX_IMAGE_BYTES", "not-an-integer"),
            ("ROCKY_MAX_IMAGE_TOTAL_BYTES", "0"),
            ("ROCKY_MAX_IMAGE_PIXELS", "0"),
            ("ROCKY_MAX_IMAGE_TOTAL_PIXELS", "0"),
        )
        for name, value in invalid_values:
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, name):
                    load_api_with_test_initialization_seam({name: value})

        with self.assertRaisesRegex(
            RuntimeError,
            "ROCKY_MAX_IMAGE_TOTAL_BYTES must be at least ROCKY_MAX_IMAGE_BYTES",
        ):
            load_api_with_test_initialization_seam({
                "ROCKY_MAX_IMAGE_BYTES": "200",
                "ROCKY_MAX_IMAGE_TOTAL_BYTES": "100",
            })

        with self.assertRaisesRegex(
            RuntimeError,
            "ROCKY_MAX_IMAGE_TOTAL_PIXELS must be at least ROCKY_MAX_IMAGE_PIXELS",
        ):
            load_api_with_test_initialization_seam({
                "ROCKY_MAX_IMAGE_PIXELS": "200",
                "ROCKY_MAX_IMAGE_TOTAL_PIXELS": "100",
            })

        with self.assertRaisesRegex(RuntimeError, "ROCKY_MAX_REQUEST_BYTES"):
            load_api_with_test_initialization_seam({
                "ROCKY_ENABLE_IMAGE_INPUT": "true",
            })

        enabled = load_api_with_test_initialization_seam({
            "ROCKY_ENABLE_IMAGE_INPUT": "true",
            "ROCKY_MAX_REQUEST_BYTES": str(10 * 1024 * 1024),
        })
        self.assertTrue(enabled.ENABLE_IMAGE_INPUT)

    def test_mongodb_rate_limiter_initialization_creates_ttl_index(self):
        collection = Mock()
        with (
            patch.object(self.api, "DB_BACKEND", "mongodb"),
            patch.object(self.api, "rate_limit_windows_col", collection),
            patch.object(self.api, "rate_limiter", None),
            patch.object(self.api, "ensure_rate_limit_ttl_index") as ensure_ttl,
        ):
            self.api.initialize_rate_limiter()

            ensure_ttl.assert_called_once_with(collection)
            self.assertIsInstance(
                self.api.rate_limiter,
                self.api.FixedWindowRateLimiter,
            )

    def test_legacy_key_gets_a_stable_public_id_before_limiting(self):
        legacy_key = {"_id": "legacy-key", "owner_id": "student-one"}
        stored_key = dict(legacy_key)
        collection = Mock()

        def update_one(_query, update):
            stored_key.update(update["$set"])
            return Mock(modified_count=1)

        collection.update_one.side_effect = update_one
        collection.find_one.side_effect = lambda _query: dict(stored_key)

        with (
            patch.object(self.api, "rate_limiter", Mock()),
            patch.object(
                self.api,
                "current_api_keys_collection",
                return_value=collection,
            ),
        ):
            normalized = self.api.rate_limit_key_doc(legacy_key)

        self.assertTrue(normalized["key_id"].startswith("akid_"))
        self.assertEqual(stored_key["key_id"], normalized["key_id"])
        collection.update_one.assert_called_once_with(
            {
                "_id": "legacy-key",
                "key_id": {"$in": [None, ""]},
            },
            {"$set": {"key_id": normalized["key_id"]}},
        )

    def test_development_bypass_has_a_non_secret_rate_limit_identity(self):
        with (
            patch.object(
                self.api,
                "development_auth_bypass_enabled",
                return_value=True,
            ),
        ):
            key_doc = self.api.get_key_doc("unused")

        self.assertEqual(
            key_doc["key_id"],
            self.api.DEVELOPMENT_BYPASS_KEY_ID,
        )
        self.assertNotEqual(key_doc["key_id"], key_doc["api-key"])

    def test_production_secret_validation_rejects_placeholders(self):
        with self.assertRaisesRegex(RuntimeError, "ROCKY_GRANITE_TOKEN"):
            self.api._require_production_secret(
                "ROCKY_GRANITE_TOKEN",
                "replace-with-a-long-random-granite-token",
            )

    def test_post_v1_responses_reaches_generation_handler(self):
        with (
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"owner_id": "route-contract-user", "is_active": True},
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "route-contract-reply",
                    "model": "route-contract-model",
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "route contract prompt",
                    "store": False,
                },
                headers={"Authorization": "Bearer route-contract-key"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["object"], "response")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["model"], self.api.PUBLIC_MODEL)
        self.assertEqual(payload["output_text"], "route-contract-reply")
        self.assertEqual(
            payload["output"][0]["content"][0]["text"],
            "route-contract-reply",
        )
        request_ai.assert_called_once()

    def test_json_api_key_is_not_accepted(self):
        response = self.client.post(
            "/v1/responses",
            json={
                "api-key": "legacy-body-key",
                "model": self.api.PUBLIC_MODEL,
                "input": "route contract prompt",
                "store": False,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "invalid_api_key",
        )

    def test_public_model_alias_maps_to_configured_inference_model(self):
        payload = self.api._build_granite_payload({
            "model": self.api.PUBLIC_MODEL,
            "instructions": "Be concise.",
            "input": [{"role": "user", "content": "Hello"}],
        })

        self.assertEqual(payload["model"], self.api.INFERENCE_MODEL)
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertEqual(payload["input"][1]["role"], "user")

    def test_unknown_public_model_is_rejected_before_generation(self):
        with (
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": "arbitrary-model", "input": "Hello", "store": False},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        request_ai.assert_not_called()

    def test_invalid_gateway_fields_are_rejected_before_generation(self):
        with (
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            for extra in (
                {"store": "false"},
                {"conversation_id": ["not", "a", "string"]},
                {"instructions": "   "},
                {"reasoning": {"effort": "low"}},
            ):
                response = self.client.post(
                    "/v1/responses",
                    json={"model": self.api.PUBLIC_MODEL, "input": "Hello", **extra},
                    headers={"Authorization": "Bearer valid-key"},
                )
                self.assertEqual(response.status_code, 400)

        request_ai.assert_not_called()

    def test_streaming_is_rejected_while_public_rollout_flag_is_disabled(self):
        with (
            patch.object(self.api, "ENABLE_STREAMING", False),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "store": False,
                    "stream": True,
                },
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["param"], "stream")
        self.assertEqual(
            response.get_json()["error"]["code"],
            "unsupported_parameter",
        )
        request_ai.assert_not_called()

    def test_streaming_translates_granite_ndjson_to_sdk_compatible_sse(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=True,
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
            remaining_requests=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1,
            retry_after_seconds=30,
        )
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Hello "},
                {"type": "delta", "text": "Rocky!"},
                {
                    "type": "completed",
                    "telemetry": {
                        "model_input_bytes": 120,
                        "model_output_bytes": 60,
                        "provider": {
                            "actual_model": self.api.INFERENCE_MODEL,
                            "prompt_eval_count": 3,
                            "eval_count": 2,
                        },
                    },
                    "metadata": {"source": "ollama"},
                },
            ],
        )
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ) as request_stream,
            patch.object(self.api, "save_response_context") as save_context,
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Say hello.",
                    "stream": True,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=True,
            )

        events = decode_sse_events(response)
        parsed = [STREAM_EVENT_ADAPTER.validate_python(event) for event in events]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        self.assertEqual(
            response.headers["x-ratelimit-limit-requests"],
            str(self.api.RESPONSES_RATE_LIMIT_PER_MINUTE),
        )
        self.assertEqual(
            response.headers["x-ratelimit-remaining-requests"],
            str(self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1),
        )
        self.assertEqual(response.headers["x-ratelimit-reset-requests"], "30s")
        self.assertTrue(response.headers["x-request-id"].startswith("req_"))
        self.assertEqual([event["type"] for event in events], [
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.delta",
            "response.output_text.done",
            "response.content_part.done",
            "response.output_item.done",
            "response.completed",
        ])
        self.assertEqual(
            [event["sequence_number"] for event in events],
            list(range(len(events))),
        )
        self.assertEqual(parsed[-1].response.output_text, "Hello Rocky!")
        self.assertEqual(parsed[-1].response.usage.input_tokens, 3)
        self.assertEqual(parsed[-1].response.usage.output_tokens, 2)
        request_stream.assert_called_once()
        model_request = request_stream.call_args.args[0]
        self.assertEqual(model_request["model"], self.api.INFERENCE_MODEL)
        context = save_context.call_args.args[2]
        self.assertEqual([message["role"] for message in context], [
            "user",
            "assistant",
        ])
        self.assertEqual(
            save_context.call_args.args[0],
            events[-1]["response"]["id"],
        )
        self.assertEqual(finish_telemetry.call_args.args[1], "completed")
        self.assertEqual(
            finish_telemetry.call_args.kwargs["response_payload"]["output_text"],
            "Hello Rocky!",
        )
        limiter.consume.assert_called_once_with(
            key_id="key-one",
            operation="responses.create",
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
        )
        upstream_response.close.assert_called_once()

    def test_streaming_pre_stream_failure_remains_json_with_real_status(self):
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=self.api.model_failure("timeout"),
            ),
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "stream": True,
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.get_json()["error"]["code"], "model_timeout")

    def test_midstream_timeout_emits_terminal_error_and_logs_partial_output(self):
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Partial answer"},
                {
                    "type": "error",
                    "error": {
                        "type": "model_timeout",
                        "message": "Model request timed out.",
                    },
                },
            ],
        )
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ),
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "stream": True,
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=True,
            )

        events = decode_sse_events(response)
        STREAM_EVENT_ADAPTER.validate_python(events[-1])
        self.assertEqual(events[-1], {
            "type": "error",
            "sequence_number": 5,
            "code": "model_timeout",
            "message": "Model request timed out.",
            "param": None,
        })
        self.assertNotIn("response.completed", [event["type"] for event in events])
        terminal_call = finish_telemetry.call_args
        self.assertEqual(terminal_call.args[1], "timed_out")
        self.assertEqual(
            terminal_call.kwargs["response_payload"]["output_text"],
            "Partial answer",
        )
        upstream_response.close.assert_called_once()

    def test_required_terminal_logging_failure_becomes_stream_error(self):
        granite_stream, _upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Generated answer"},
                {
                    "type": "completed",
                    "telemetry": {},
                    "metadata": {},
                },
            ],
        )
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api, "REQUIRE_REQUEST_LOGGING", True),
            patch.object(
                self.api,
                "begin_telemetry_interaction",
                return_value={"request_id": "req_stream_logging", "persisted": True},
            ),
            patch.object(self.api, "enrich_telemetry_interaction", return_value=True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ),
            patch.object(self.api, "save_response_context") as save_context,
            patch.object(self.api, "delete_response_context") as delete_context,
            patch.object(self.api, "finish_telemetry_interaction", return_value=False),
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "stream": True,
                    "store": True,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=True,
            )

        events = decode_sse_events(response)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["code"], "request_logging_unavailable")
        self.assertNotIn("response.completed", [event["type"] for event in events])
        save_context.assert_called_once()
        delete_context.assert_called_once_with(
            save_context.call_args.args[0],
            "credential:key-one",
        )

    def test_required_terminal_logging_failure_removes_buffered_context(self):
        with (
            patch.object(self.api, "REQUIRE_REQUEST_LOGGING", True),
            patch.object(
                self.api,
                "begin_telemetry_interaction",
                return_value={"request_id": "req_buffered_logging", "persisted": True},
            ),
            patch.object(self.api, "enrich_telemetry_interaction", return_value=True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Generated answer",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ),
            patch.object(self.api, "save_response_context") as save_context,
            patch.object(self.api, "delete_response_context") as delete_context,
            patch.object(self.api, "finish_telemetry_interaction", return_value=False),
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Hello", "store": True},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "request_logging_unavailable",
        )
        save_context.assert_called_once()
        delete_context.assert_called_once_with(
            save_context.call_args.args[0],
            "credential:key-one",
        )

    def test_required_terminal_logging_failure_marks_buffered_web_history_failed(self):
        chat_context = {
            "user_id": "student-one",
            "user_email": "student@kent.edu",
            "user_name": "Student One",
        }
        with (
            patch.object(self.api, "REQUIRE_REQUEST_LOGGING", True),
            patch.object(
                self.api,
                "begin_telemetry_interaction",
                return_value={"request_id": "req_web_logging", "persisted": True},
            ),
            patch.object(self.api, "enrich_telemetry_interaction", return_value=True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(self.api, "should_use_web_history", return_value=True),
            patch.object(self.api, "get_chat_user_context", return_value=chat_context),
            patch.object(
                self.api,
                "get_or_create_conversation",
                return_value="conversation-one",
            ),
            patch.object(self.api, "load_recent_messages", return_value=[]),
            patch.object(
                self.api,
                "save_message",
                side_effect=["user-message-one", "assistant-message-one"],
            ),
            patch.object(self.api, "update_message_status") as update_status,
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Generated answer",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ),
            patch.object(self.api, "finish_telemetry_interaction", return_value=False),
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Hello", "store": True},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["conversation_id"], "conversation-one")
        self.assertTrue(response.get_json()["message_stored"])
        self.assertEqual(
            update_status.call_args_list,
            [
                call("conversation-one", "student-one", "user-message-one", "sent"),
                call("conversation-one", "student-one", "user-message-one", "failed"),
                call("conversation-one", "student-one", "assistant-message-one", "failed"),
            ],
        )

    def test_closing_public_stream_records_disconnect_and_closes_granite(self):
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Unused"},
                {"type": "cancelled"},
            ],
        )
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ),
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "stream": True,
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=False,
            )
            response.close()

        terminal_call = finish_telemetry.call_args
        self.assertEqual(terminal_call.args[1], "failed")
        self.assertEqual(terminal_call.kwargs["error_type"], "client_disconnected")
        upstream_response.close.assert_called_once()

    def test_closing_web_stream_retains_failed_prompt_and_partial_response(self):
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Partial answer"},
                {"type": "cancelled"},
            ],
        )
        chat_context = {
            "user_id": "student-one",
            "user_email": "student@kent.edu",
            "user_name": "Student One",
        }
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(self.api, "should_use_web_history", return_value=True),
            patch.object(self.api, "get_chat_user_context", return_value=chat_context),
            patch.object(
                self.api,
                "get_or_create_conversation",
                return_value="conversation-one",
            ),
            patch.object(self.api, "load_recent_messages", return_value=[]),
            patch.object(
                self.api,
                "save_message",
                side_effect=["user-message-one", "assistant-message-one"],
            ) as save_message,
            patch.object(self.api, "update_message_status") as update_status,
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ),
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Web question",
                    "stream": True,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=False,
            )
            self.assertEqual(response.headers["X-Rocky-Conversation-Id"], "conversation-one")
            for chunk in response.response:
                chunk_text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
                event = json.loads(chunk_text.splitlines()[1].removeprefix("data: "))
                if event["type"] == "response.output_text.delta":
                    break
            response.close()

        update_status.assert_called_once_with(
            "conversation-one",
            "student-one",
            "user-message-one",
            "failed",
        )
        self.assertEqual(save_message.call_count, 2)
        self.assertEqual(
            save_message.call_args_list[1].kwargs,
            {
                "conversation_id": "conversation-one",
                "user_id": "student-one",
                "role": "assistant",
                "content": "Partial answer",
                "model": self.api.INFERENCE_MODEL,
                "user_context": chat_context,
                "status": "failed",
            },
        )
        self.assertEqual(finish_telemetry.call_args.args[1], "failed")
        self.assertEqual(
            finish_telemetry.call_args.kwargs["error_type"],
            "client_disconnected",
        )
        upstream_response.close.assert_called_once()

    def test_disconnect_during_success_suffix_preserves_completion_and_marks_delivery(self):
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Finished answer"},
                {"type": "completed", "telemetry": {}, "metadata": {}},
            ],
        )
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(self.api, "request_ai_stream", return_value=granite_stream),
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
            patch.object(self.api, "record_stream_delivery") as record_delivery,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Hello",
                    "stream": True,
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=False,
            )
            for chunk in response.response:
                chunk_text = (
                    chunk.decode("utf-8")
                    if isinstance(chunk, bytes)
                    else chunk
                )
                event = json.loads(
                    chunk_text.splitlines()[1].removeprefix("data: ")
                )
                if event["type"] == "response.output_item.done":
                    break
            response.close()

        self.assertEqual(finish_telemetry.call_args.args[1], "completed")
        record_delivery.assert_called_once_with(
            finish_telemetry.call_args.args[0],
            "client_disconnected",
        )
        upstream_response.close.assert_called_once()

    def test_all_supported_input_messages_reach_generation(self):
        with (
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "ok",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": [
                        {"role": "developer", "content": "Return JSON."},
                        {"role": "assistant", "content": "Earlier answer"},
                        {"role": "user", "content": "Current question"},
                    ],
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        model_request = request_ai.call_args.args[0]
        self.assertEqual(
            [message["role"] for message in model_request["input"]],
            ["system", "assistant", "user"],
        )

    def test_previous_response_id_prepends_stored_context(self):
        previous_context = [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "First question"}],
            },
            {
                "role": "assistant",
                "content": [{"type": "output_text", "text": "First answer"}],
            },
        ]
        with (
            patch.object(self.api, "get_key_doc", return_value={"key_id": "key-one"}),
            patch.object(self.api, "load_response_context", return_value=previous_context),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Second answer",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Second question",
                    "previous_response_id": "resp_previous",
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["previous_response_id"], "resp_previous")
        self.assertEqual(
            [message["role"] for message in request_ai.call_args.args[0]["input"]],
            ["user", "assistant", "user"],
        )

    def test_models_lists_only_the_configured_public_model(self):
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "get_key_doc", return_value={"key_id": "key-one"}),
        ):
            response = self.client.get(
                "/v1/models",
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"][0]["id"], self.api.PUBLIC_MODEL)
        self.assertEqual(
            response.get_json()["data"][0]["metadata"],
            {
                "max_context_characters": self.api.MAX_CONTEXT_CHARS,
                "max_image_bytes": self.api.MAX_IMAGE_BYTES,
                "max_image_pixels": self.api.MAX_IMAGE_PIXELS,
                "max_image_total_bytes": self.api.MAX_IMAGE_TOTAL_BYTES,
                "max_image_total_pixels": self.api.MAX_IMAGE_TOTAL_PIXELS,
                "max_images_per_request": self.api.MAX_IMAGES_PER_REQUEST,
                "max_output_tokens": self.api.MAX_OUTPUT_TOKENS,
                "supports_image_input": True,
                "supports_instructions": True,
                "supports_previous_response_id": True,
                "supports_streaming": True,
                "model_dependent_parameters": ["frequency_penalty", "presence_penalty"],
            },
        )
        self.assertTrue(response.headers.get("x-request-id"))

    def test_models_uses_its_separate_rate_limit_policy(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=True,
            limit=self.api.MODELS_RATE_LIMIT_PER_MINUTE,
            remaining_requests=self.api.MODELS_RATE_LIMIT_PER_MINUTE - 1,
            retry_after_seconds=30,
        )
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_models"},
            ),
        ):
            response = self.client.get(
                "/v1/models",
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        limiter.consume.assert_called_once_with(
            key_id="akid_models",
            operation="models.list",
            limit=self.api.MODELS_RATE_LIMIT_PER_MINUTE,
        )
        self.assertEqual(
            response.headers["x-ratelimit-limit-requests"],
            str(self.api.MODELS_RATE_LIMIT_PER_MINUTE),
        )
        self.assertEqual(
            response.headers["x-ratelimit-remaining-requests"],
            str(self.api.MODELS_RATE_LIMIT_PER_MINUTE - 1),
        )
        self.assertEqual(response.headers["x-ratelimit-reset-requests"], "30s")

    def test_authenticated_invalid_response_request_consumes_rate_limit(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=True,
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
            remaining_requests=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1,
            retry_after_seconds=30,
        )
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_invalid_request"},
            ),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": "unsupported-model", "input": "Hello"},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        limiter.consume.assert_called_once_with(
            key_id="akid_invalid_request",
            operation="responses.create",
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
        )
        self.assertEqual(
            response.headers["x-ratelimit-remaining-requests"],
            str(self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1),
        )
        self.assertEqual(response.headers["x-ratelimit-reset-requests"], "30s")
        request_ai.assert_not_called()

    def test_invalid_authentication_does_not_consume_rate_limit(self):
        limiter = Mock()
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(self.api, "get_key_doc", return_value=None),
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Hello"},
                headers={"Authorization": "Bearer invalid-key"},
            )

        self.assertEqual(response.status_code, 401)
        limiter.consume.assert_not_called()
        self.assertNotIn("x-ratelimit-limit-requests", response.headers)
        self.assertNotIn("x-ratelimit-remaining-requests", response.headers)
        self.assertNotIn("x-ratelimit-reset-requests", response.headers)

    def test_authenticated_malformed_json_consumes_rate_limit_but_health_does_not(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=True,
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
            remaining_requests=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1,
            retry_after_seconds=30,
        )
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_malformed"},
            ),
        ):
            malformed_response = self.client.post(
                "/v1/responses",
                data="{not-json",
                content_type="application/json",
                headers={"Authorization": "Bearer valid-key"},
            )
            health_response = self.client.get("/health")

        self.assertEqual(malformed_response.status_code, 400)
        self.assertEqual(health_response.status_code, 200)
        limiter.consume.assert_called_once_with(
            key_id="akid_malformed",
            operation="responses.create",
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
        )

    def test_authenticated_oversized_request_is_attributed_and_rate_limited(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=True,
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
            remaining_requests=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE - 1,
            retry_after_seconds=30,
        )
        original_limit = self.api.app.config["MAX_CONTENT_LENGTH"]
        self.api.app.config["MAX_CONTENT_LENGTH"] = 32
        try:
            with (
                patch.object(self.api, "rate_limiter", limiter),
                patch.object(
                    self.api,
                    "get_key_doc",
                    return_value={
                        "key_id": "akid_oversized",
                        "owner_id": "student-one",
                    },
                ),
                patch.object(
                    self.api,
                    "enrich_telemetry_interaction",
                    return_value=True,
                ) as enrich,
            ):
                response = self.client.post(
                    "/v1/responses",
                    data=b"x" * 128,
                    content_type="application/json",
                    headers={"Authorization": "Bearer valid-key"},
                )
        finally:
            self.api.app.config["MAX_CONTENT_LENGTH"] = original_limit

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"]["code"], "request_too_large")
        self.assertTrue(any(
            call.args[1].get("credential", {}).get("key_id") == "akid_oversized"
            for call in enrich.call_args_list
        ))
        limiter.consume.assert_called_once_with(
            key_id="akid_oversized",
            operation="responses.create",
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
        )

    def test_authenticated_oversized_request_fails_closed_without_rate_identity(self):
        original_limit = self.api.app.config["MAX_CONTENT_LENGTH"]
        self.api.app.config["MAX_CONTENT_LENGTH"] = 32
        try:
            with (
                patch.object(
                    self.api,
                    "get_key_doc",
                    return_value={"owner_id": "legacy-student"},
                ),
                patch.object(self.api, "rate_limit_key_doc", return_value=None),
            ):
                response = self.client.post(
                    "/v1/responses",
                    data=b"x" * 128,
                    content_type="application/json",
                    headers={"Authorization": "Bearer valid-key"},
                )
        finally:
            self.api.app.config["MAX_CONTENT_LENGTH"] = original_limit

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "rate_limit_identity_unavailable",
        )

    def test_rate_limited_response_returns_openai_style_error_and_retry_after(self):
        limiter = Mock()
        limiter.consume.return_value = self.api.RateLimitDecision(
            allowed=False,
            limit=self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
            remaining_requests=0,
            retry_after_seconds=17,
        )
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_limited"},
            ),
            patch.object(self.api, "request_ai") as request_ai,
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ) as finish_telemetry,
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Hello"},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "17")
        self.assertEqual(
            response.headers["x-ratelimit-limit-requests"],
            str(self.api.RESPONSES_RATE_LIMIT_PER_MINUTE),
        )
        self.assertEqual(response.headers["x-ratelimit-remaining-requests"], "0")
        self.assertEqual(response.headers["x-ratelimit-reset-requests"], "17s")
        self.assertEqual(response.get_json()["error"], {
            "message": "Rate limit reached for this API key. Please retry shortly.",
            "type": "rate_limit_error",
            "param": None,
            "code": "rate_limit_exceeded",
        })
        request_ai.assert_not_called()
        self.assertEqual(
            finish_telemetry.call_args.kwargs["additional_fields"],
            {
                "rate_limit": {
                    "scope": "api_key",
                    "operation": "responses.create",
                    "limit": self.api.RESPONSES_RATE_LIMIT_PER_MINUTE,
                    "remaining_requests": 0,
                    "window_seconds": 60,
                    "retry_after_seconds": 17,
                }
            },
        )

    def test_rate_limit_headers_track_the_persisted_counter(self):
        collection = MongitaClientMemory()["phase4_route_contract"]["rate_limit_windows"]
        limiter = self.api.FixedWindowRateLimiter(collection, clock=lambda: 120.0)
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(self.api, "RESPONSES_RATE_LIMIT_PER_MINUTE", 2),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_phase4_integration"},
            ),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            responses = [
                self.client.post(
                    "/v1/responses",
                    json={"model": "unsupported-model", "input": "Hello"},
                    headers={"Authorization": "Bearer valid-key"},
                )
                for _ in range(3)
            ]

        self.assertEqual([response.status_code for response in responses], [400, 400, 429])
        self.assertEqual(
            [response.headers["x-ratelimit-limit-requests"] for response in responses],
            ["2", "2", "2"],
        )
        self.assertEqual(
            [response.headers["x-ratelimit-remaining-requests"] for response in responses],
            ["1", "0", "0"],
        )
        self.assertEqual(
            [response.headers["x-ratelimit-reset-requests"] for response in responses],
            ["60s", "60s", "60s"],
        )
        self.assertNotIn("Retry-After", responses[0].headers)
        self.assertEqual(responses[2].headers["Retry-After"], "60")
        request_ai.assert_not_called()

    def test_rate_limit_storage_failure_is_fail_closed(self):
        limiter = Mock()
        limiter.consume.side_effect = self.api.RateLimitStoreUnavailable(
            "synthetic storage failure"
        )
        with (
            patch.object(self.api, "rate_limiter", limiter),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "akid_store_failure"},
            ),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Hello"},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "rate_limit_unavailable",
        )
        request_ai.assert_not_called()

    def test_successful_stored_response_saves_continuation_context(self):
        with (
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "user"},
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Stored answer",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ),
            patch.object(self.api, "save_response_context") as save_context,
        ):
            response = self.client.post(
                "/v1/responses",
                json={"model": self.api.PUBLIC_MODEL, "input": "Stored question"},
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        context = save_context.call_args.args[2]
        self.assertEqual([item["role"] for item in context], ["user", "assistant"])

    def test_readiness_requires_database_and_granite(self):
        database = Mock()
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "ok": True,
            "model": self.api.INFERENCE_MODEL,
            "capabilities": {
                "supports_streaming": False,
                "supports_image_input": False,
            },
        }
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api, "GRANITE_AUTH_TOKEN", "synthetic-granite-token"),
            patch.object(
                self.api.requests,
                "get",
                return_value=granite_response,
            ) as get,
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["dependencies"],
            {"database": True, "granite": True},
        )
        self.assertEqual(
            response.get_json()["models"],
            {
                "public": self.api.PUBLIC_MODEL,
                "inference": self.api.INFERENCE_MODEL,
                "granite": self.api.INFERENCE_MODEL,
            },
        )
        self.assertEqual(response.get_json()["streaming"], {
            "rocky_enabled": False,
            "granite_enabled": False,
        })
        self.assertEqual(response.get_json()["image_input"], {
            "rocky_enabled": False,
            "granite_enabled": False,
            "limits_match": False,
            "rocky_limits": self.api.image_limit_capabilities(),
            "granite_limits": None,
        })
        self.assertEqual(response.get_json()["capabilities"], self.api.model_capabilities())
        self.assertEqual(
            get.call_args.kwargs["headers"],
            {"X-Rocky-Granite-Token": "synthetic-granite-token"},
        )

    def test_readiness_rejects_a_mismatched_granite_model(self):
        database = Mock()
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "ok": True,
            "model": "different-model:latest",
        }
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api.requests, "get", return_value=granite_response),
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["dependencies"]["granite"])
        self.assertEqual(
            response.get_json()["models"]["granite"],
            "different-model:latest",
        )

    def test_readiness_rejects_streaming_configuration_mismatch(self):
        database = Mock()
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "ok": True,
            "model": self.api.INFERENCE_MODEL,
            "capabilities": {"supports_streaming": False},
        }
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api.requests, "get", return_value=granite_response),
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["dependencies"]["granite"])
        self.assertEqual(response.get_json()["streaming"], {
            "rocky_enabled": True,
            "granite_enabled": False,
        })

    def test_readiness_rejects_image_input_configuration_mismatch(self):
        database = Mock()
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "ok": True,
            "model": self.api.INFERENCE_MODEL,
            "capabilities": {
                "supports_streaming": False,
                "supports_image_input": False,
            },
        }
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api.requests, "get", return_value=granite_response),
        ):
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["dependencies"]["granite"])
        self.assertEqual(response.get_json()["image_input"], {
            "rocky_enabled": True,
            "granite_enabled": False,
            "limits_match": False,
            "rocky_limits": self.api.image_limit_capabilities(),
            "granite_limits": None,
        })

    def test_readiness_requires_exact_image_limit_parity(self):
        database = Mock()
        mismatched_limits = self.api.image_limit_capabilities()
        mismatched_limits["max_total_pixels"] -= 1
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "ok": True,
            "model": self.api.INFERENCE_MODEL,
            "capabilities": {
                "supports_streaming": False,
                "supports_image_input": True,
                "image_limits": mismatched_limits,
            },
        }
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api.requests, "get", return_value=granite_response),
        ):
            mismatch = self.client.get("/ready")

        self.assertEqual(mismatch.status_code, 503)
        self.assertFalse(mismatch.get_json()["image_input"]["limits_match"])
        self.assertEqual(
            mismatch.get_json()["image_input"]["granite_limits"],
            mismatched_limits,
        )

        granite_response.json.return_value["capabilities"][
            "image_limits"
        ] = self.api.image_limit_capabilities()
        with (
            patch.object(self.api, "api_keys_col", database),
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api.requests, "get", return_value=granite_response),
        ):
            matched = self.client.get("/ready")

        self.assertEqual(matched.status_code, 200)
        self.assertTrue(matched.get_json()["image_input"]["limits_match"])

    def test_service_key_cannot_call_responses_without_trusted_proxy_context(self):
        service_key = {
            "key_id": "service-key-one",
            "owner_id": "rocky-chat-service@kent.edu",
            "owner_type": "service",
            "key_scope": "service",
            "is_active": True,
        }
        with (
            patch.object(self.api, "get_key_doc", return_value=service_key),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Attempt a direct service-key call.",
                    "store": False,
                },
                headers={"Authorization": "Bearer service-key"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["error"]["code"],
            "invalid_proxy_authentication",
        )
        request_ai.assert_not_called()

    def test_service_key_can_call_responses_through_trusted_proxy(self):
        service_key = {
            "key_id": "service-key-one",
            "owner_id": "rocky-chat-service@kent.edu",
            "owner_type": "service",
            "key_scope": "service",
            "is_active": True,
        }
        with (
            patch.object(self.api, "get_key_doc", return_value=service_key),
            patch.object(
                self.api,
                "INTERNAL_PROXY_SECRET",
                "synthetic-internal-proxy-secret",
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Trusted reply",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "A trusted proxy request.",
                    "store": False,
                },
                headers={
                    "Authorization": "Bearer service-key",
                    "X-Rocky-Internal-Secret": "synthetic-internal-proxy-secret",
                    "X-Rocky-User-Id": "student-one",
                },
            )

        self.assertEqual(response.status_code, 200)
        request_ai.assert_called_once()

    def test_context_budget_drops_oldest_complete_messages(self):
        history = [
            {"role": "user", "content": "oldest-1234"},
            {"role": "assistant", "content": "newest-1234"},
        ]
        current = [{"role": "user", "content": "current"}]
        with patch.object(self.api, "MAX_CONTEXT_CHARS", 20):
            retained, omitted = self.api.bounded_history_messages(history, current)

        self.assertEqual(retained, [history[-1]])
        self.assertEqual(omitted, 1)

    def test_chat_api_authenticates_requests_to_granite(self):
        granite_response = Mock(status_code=200)
        granite_response.json.return_value = {
            "model": self.api.INFERENCE_MODEL,
            "output_text": "Authenticated reply",
            "metadata": {},
            "telemetry": {},
        }
        with (
            patch.object(self.api, "GRANITE_AUTH_TOKEN", "synthetic-granite-token"),
            patch.object(self.api.requests, "post", return_value=granite_response) as post,
        ):
            result = self.api.request_ai({
                "model": self.api.PUBLIC_MODEL,
                "input": "Hello",
            })

        self.assertEqual(result["output_text"], "Authenticated reply")
        self.assertEqual(
            post.call_args.kwargs["headers"]["X-Rocky-Granite-Token"],
            "synthetic-granite-token",
        )

    def test_streaming_client_authenticates_and_targets_inference_model(self):
        granite_stream = Mock(spec=self.api.GraniteEventStream)
        with (
            patch.object(self.api, "GRANITE_AUTH_TOKEN", "synthetic-granite-token"),
            patch.object(
                self.api,
                "open_granite_stream",
                return_value=granite_stream,
            ) as open_stream,
        ):
            result = self.api.request_ai_stream({
                "model": self.api.PUBLIC_MODEL,
                "input": "Hello",
            })

        self.assertIs(result, granite_stream)
        self.assertEqual(open_stream.call_args.args[0], self.api.GRANITE_URL)
        self.assertEqual(
            open_stream.call_args.args[2],
            {"X-Rocky-Granite-Token": "synthetic-granite-token"},
        )
        self.assertEqual(
            open_stream.call_args.args[4],
            self.api.INFERENCE_MODEL,
        )

    def test_streaming_web_history_marks_user_sent_and_saves_assistant(self):
        granite_stream, _upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Web answer"},
                {
                    "type": "completed",
                    "telemetry": {},
                    "metadata": {},
                },
            ],
        )
        chat_context = {
            "user_id": "student-one",
            "user_email": "student@kent.edu",
            "user_name": "Student One",
        }
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(self.api, "should_use_web_history", return_value=True),
            patch.object(
                self.api,
                "get_chat_user_context",
                return_value=chat_context,
            ),
            patch.object(
                self.api,
                "get_or_create_conversation",
                return_value="conversation-one",
            ),
            patch.object(self.api, "load_recent_messages", return_value=[]),
            patch.object(
                self.api,
                "save_message",
                side_effect=["user-message-one", "assistant-message-one"],
            ) as save_message,
            patch.object(self.api, "update_message_status") as update_status,
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ),
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ),
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": "Web question",
                    "stream": True,
                },
                headers={"Authorization": "Bearer valid-key"},
                buffered=True,
            )

        events = decode_sse_events(response)
        self.assertEqual(
            events[-1]["response"]["conversation_id"],
            "conversation-one",
        )
        self.assertEqual(
            response.headers["X-Rocky-Conversation-Id"],
            "conversation-one",
        )
        self.assertEqual(response.headers["X-Rocky-Message-Stored"], "true")
        update_status.assert_called_once_with(
            "conversation-one",
            "student-one",
            "user-message-one",
            "sent",
        )
        self.assertEqual(save_message.call_count, 2)
        assistant_call = save_message.call_args_list[1]
        self.assertEqual(assistant_call.kwargs["role"], "assistant")
        self.assertEqual(assistant_call.kwargs["content"], "Web answer")

    def test_image_input_is_rejected_while_public_rollout_flag_is_disabled(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        request_body["model"] = self.api.PUBLIC_MODEL
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", False),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"]["param"],
            "input[0].content[1].type",
        )
        request_ai.assert_not_called()

    def test_image_input_is_verified_normalized_and_sent_to_granite(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        request_body["model"] = self.api.PUBLIC_MODEL
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "A single pixel.",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
            patch.object(self.api, "enrich_telemetry_interaction") as enrich,
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        model_request = request_ai.call_args.args[0]
        image = model_request["input"][0]["content"][1]
        self.assertEqual(image["type"], "input_image")
        self.assertEqual(image["mime_type"], "image/png")
        self.assertEqual((image["width"], image["height"]), (1, 1))
        self.assertNotIn("image_url", image)
        model_input_record = enrich.call_args_list[-1].args[1]["request"]
        self.assertEqual(len(model_input_record["image_inputs"]), 1)
        self.assertEqual(
            model_input_record["model_input"]["input"][0]["content"][1][
                "image_base64"
            ],
            "[OMITTED: stored image payload]",
        )
        self.assertIn("data:image/png;base64,", str(model_input_record["body"]))

    def test_interleaved_image_content_preserves_public_block_order(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        image = request_body["input"][0]["content"][1]
        request_body["model"] = self.api.PUBLIC_MODEL
        request_body["store"] = False
        request_body["input"][0]["content"] = [
            {"type": "input_text", "text": "Before."},
            image,
            {"type": "input_text", "text": "Between."},
            dict(image),
            {"type": "input_text", "text": "After."},
        ]
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Ordered answer.",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        normalized_content = request_ai.call_args.args[0]["input"][0]["content"]
        self.assertEqual(
            [block["type"] for block in normalized_content],
            ["input_text", "input_image", "input_text", "input_image", "input_text"],
        )
        self.assertEqual(
            [block["text"] for block in normalized_content if block["type"] == "input_text"],
            ["Before.", "Between.", "After."],
        )

    def test_enabled_image_input_rejects_remote_sources_before_generation(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        request_body["model"] = self.api.PUBLIC_MODEL
        request_body["input"][0]["content"][1]["image_url"] = (
            "https://example.test/student-image.png"
        )
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            {
                "message": (
                    "image_url must be a base64 data URL containing a JPEG, PNG, "
                    "or WebP image."
                ),
                "type": "invalid_request_error",
                "param": "input[0].content[1].image_url",
                "code": "unsupported_image_source",
            },
        )
        request_ai.assert_not_called()

    def test_verified_image_input_can_use_the_public_streaming_path(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        request_body["model"] = self.api.PUBLIC_MODEL
        request_body["stream"] = True
        granite_stream, upstream_response = make_granite_event_stream(
            self.api,
            [
                {"type": "delta", "text": "Image answer"},
                {"type": "completed", "telemetry": {}, "metadata": {}},
            ],
        )
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ) as request_stream,
            patch.object(
                self.api,
                "finish_telemetry_interaction",
                return_value=True,
            ),
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
                buffered=True,
            )

        events = decode_sse_events(response)
        self.assertEqual(events[-1]["type"], "response.completed")
        self.assertEqual(events[-1]["response"]["output_text"], "Image answer")
        internal_image = request_stream.call_args.args[0]["input"][0]["content"][1]
        self.assertEqual(internal_image["type"], "input_image")
        upstream_response.close.assert_called_once()

    def test_verified_image_can_be_the_only_user_content(self):
        request_body = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        request_body["model"] = self.api.PUBLIC_MODEL
        request_body["input"][0]["content"] = [
            request_body["input"][0]["content"][1]
        ]
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Image-only answer",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json=request_body,
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            request_ai.call_args.args[0]["input"][0]["content"][0]["type"],
            "input_image",
        )

    def test_owned_history_converts_private_images_to_safe_public_blocks(self):
        internal_image = {
            "type": "input_image",
            "mime_type": "image/png",
            "image_base64": "QUJDRA==",
            "detail": "auto",
            "byte_length": 4,
            "width": 1,
            "height": 1,
            "sha256": "0" * 64,
        }

        exported = self.api.clean_message_for_export({
            "message_id": "message-image",
            "role": "user",
            "content": "Inspect this",
            "input_images": [
                internal_image,
                {**internal_image, "mime_type": "image/svg+xml"},
                {**internal_image, "byte_length": 99},
            ],
        })

        self.assertEqual(
            exported["input_images"],
            [{
                "type": "input_image",
                "image_url": "data:image/png;base64,QUJDRA==",
                "detail": "auto",
            }],
        )
        self.assertNotIn("image_base64", str(exported))
        markdown = self.api.format_conversation_markdown(
            {"title": "Image chat"},
            [{"role": "user", "content": "Inspect this", "input_images": [internal_image]}],
        )
        self.assertIn("1 attached image(s)", markdown)

    def test_post_rocky_api_is_not_registered(self):
        response = self.client.post("/rocky-api", json={})

        self.assertEqual(response.status_code, 404)

    def test_conversation_routes_remain_independently_registered(self):
        rules = {
            (rule.rule, method)
            for rule in self.api.app.url_map.iter_rules()
            for method in rule.methods
        }

        self.assertIn(("/conversations/list", "POST"), rules)
        self.assertIn(("/conversations/<conversation_id>", "POST"), rules)
        self.assertIn(("/conversations/<conversation_id>/export", "POST"), rules)


if __name__ == "__main__":
    unittest.main()
