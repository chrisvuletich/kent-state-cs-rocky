from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "api.py"


def load_api_with_test_initialization_seam():
    spec = importlib.util.spec_from_file_location(
        "api_rocky_route_contract",
        MODULE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load api-rocky for route contract tests.")

    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(API_ROCKY_DIR))
    try:
        with patch.dict(
            os.environ,
            {
                "ROCKY_APP_ENV": "test",
                "ROCKY_CHAT_API_KEY": "",
                "ROCKY_TELEMETRY_ENABLED": "false",
                "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
            },
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
