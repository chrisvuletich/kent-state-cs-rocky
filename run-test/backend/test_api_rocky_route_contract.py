from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mongita import MongitaClientMemory


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "api.py"


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

    def test_streaming_is_rejected_instead_of_returning_empty_stream(self):
        with (
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
        with patch.object(self.api, "get_key_doc", return_value={"key_id": "key-one"}):
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
                "max_output_tokens": self.api.MAX_OUTPUT_TOKENS,
                "supports_instructions": True,
                "supports_previous_response_id": True,
                "supports_streaming": False,
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

    def test_malformed_json_and_health_do_not_consume_rate_limit(self):
        limiter = Mock()
        with patch.object(self.api, "rate_limiter", limiter):
            malformed_response = self.client.post(
                "/v1/responses",
                data="{not-json",
                content_type="application/json",
                headers={"Authorization": "Bearer valid-key"},
            )
            health_response = self.client.get("/health")

        self.assertEqual(malformed_response.status_code, 400)
        self.assertEqual(health_response.status_code, 200)
        limiter.consume.assert_not_called()

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

    def test_unsupported_content_reports_the_exact_parameter(self):
        with (
            patch.object(self.api, "get_key_doc", return_value={"owner_id": "user"}),
            patch.object(self.api, "request_ai") as request_ai,
        ):
            response = self.client.post(
                "/v1/responses",
                json={
                    "model": self.api.PUBLIC_MODEL,
                    "input": [{
                        "role": "user",
                        "content": [{"type": "input_image", "image_url": "x"}],
                    }],
                    "store": False,
                },
                headers={"Authorization": "Bearer valid-key"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"]["param"],
            "input[0].content[0].type",
        )
        request_ai.assert_not_called()

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
