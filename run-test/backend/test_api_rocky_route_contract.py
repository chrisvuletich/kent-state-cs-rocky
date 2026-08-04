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
                    "api-key": "route-contract-key",
                    "message": "route contract prompt",
                    "store": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "route-contract-reply")
        request_ai.assert_called_once()

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
