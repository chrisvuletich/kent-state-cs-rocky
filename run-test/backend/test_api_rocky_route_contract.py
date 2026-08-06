from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


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
                    "model": "rocky",
                    "input": "route contract prompt",
                    "store": False,
                },
                headers={"Authorization": "Bearer route-contract-key"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["object"], "response")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["model"], "rocky")
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
                "model": "rocky",
                "input": "route contract prompt",
                "store": False,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Invalid API key"})

    def test_public_model_alias_maps_to_configured_inference_model(self):
        payload = self.api._build_granite_payload({
            "model": "rocky",
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
            ):
                response = self.client.post(
                    "/v1/responses",
                    json={"model": "rocky", "input": "Hello", **extra},
                    headers={"Authorization": "Bearer valid-key"},
                )
                self.assertEqual(response.status_code, 400)

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
