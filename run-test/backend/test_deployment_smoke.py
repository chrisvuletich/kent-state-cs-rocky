from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "run-test" / "integration" / "deployment_smoke.py"


def load_module():
    spec = importlib.util.spec_from_file_location("rocky_deployment_smoke", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load deployment smoke module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = load_module()


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.routes[(method, url)]


def successful_routes(base_url="https://rocky.example"):
    return {
        ("GET", f"{base_url}/api/health"): FakeResponse(
            200, {"ok": True, "service": "rocky-web"}
        ),
        ("GET", f"{base_url}/api/server-health"): FakeResponse(
            200,
            {
                "ok": True,
                "services": [
                    {"name": "web", "ok": True},
                    {"name": "backend", "ok": True},
                    {"name": "granite", "ok": True},
                    {"name": "chat-api", "ok": True},
                    {"name": "ollama", "ok": True},
                ],
            },
        ),
        ("GET", f"{base_url}/v1/models"): FakeResponse(
            200,
            {"object": "list", "data": [{"id": "course-model", "object": "model"}]},
        ),
        ("POST", f"{base_url}/v1/responses"): FakeResponse(
            200,
            {
                "status": "completed",
                "model": "course-model",
                "output_text": "Rocky deployment smoke passed.",
                "usage": {"input_tokens": 8, "output_tokens": 5, "total_tokens": 13},
            },
            {"x-request-id": "req_smoke"},
        ),
    }


class DeploymentSmokeTests(unittest.TestCase):
    def config(self, include_generation=False, expected_model="course-model"):
        return smoke.SmokeConfig(
            base_url="https://rocky.example",
            api_key="sk_kent_test_value",
            expected_model=expected_model,
            timeout_seconds=5,
            include_generation=include_generation,
        )

    def test_read_only_smoke_checks_public_health_and_models(self):
        session = FakeSession(successful_routes())
        checks = smoke.DeploymentSmoke(self.config(), session=session).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual([check.name for check in checks], [
            "web health",
            "service health",
            "model discovery",
        ])
        self.assertFalse(any(method == "POST" for method, _url, _kwargs in session.calls))
        model_call = next(call for call in session.calls if call[1].endswith("/v1/models"))
        self.assertEqual(
            model_call[2]["headers"]["Authorization"],
            "Bearer sk_kent_test_value",
        )

    def test_generation_is_explicit_and_uses_safe_request_shape(self):
        session = FakeSession(successful_routes())
        checks = smoke.DeploymentSmoke(
            self.config(include_generation=True), session=session
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        generation_call = next(call for call in session.calls if call[0] == "POST")
        self.assertEqual(generation_call[2]["json"]["model"], "course-model")
        self.assertEqual(generation_call[2]["json"]["store"], False)
        self.assertEqual(generation_call[2]["json"]["max_output_tokens"], 32)

    def test_failed_service_and_model_mismatch_are_reported(self):
        routes = successful_routes()
        routes[("GET", "https://rocky.example/api/server-health")] = FakeResponse(
            503,
            {
                "ok": False,
                "services": [
                    {"name": "backend", "ok": True},
                    {"name": "ollama", "ok": False},
                ],
            },
        )
        session = FakeSession(routes)
        checks = smoke.DeploymentSmoke(
            self.config(expected_model="missing-model"), session=session
        ).run()

        self.assertFalse(checks[1].passed)
        self.assertEqual(checks[1].detail, "Unavailable: ollama")
        self.assertFalse(checks[2].passed)
        self.assertIn("missing-model", checks[2].detail)

    def test_configuration_uses_environment_without_exposing_key(self):
        args = smoke.parse_args(["--base-url", "https://rocky.example/v1/responses"])
        with patch.dict(
            os.environ,
            {"ROCKY_API_KEY": "sk_kent_secret", "ROCKY_EXPECTED_MODEL": "course-model"},
            clear=False,
        ):
            config = smoke.build_config(args)

        self.assertEqual(config.base_url, "https://rocky.example")
        self.assertEqual(config.api_key, "sk_kent_secret")
        self.assertNotIn("sk_kent_secret", repr(config))

    def test_configuration_rejects_missing_key_and_invalid_url(self):
        with patch.dict(os.environ, {"ROCKY_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "ROCKY_API_KEY"):
                smoke.build_config(smoke.parse_args(["--base-url", "https://rocky.example"]))

        with self.assertRaisesRegex(ValueError, "absolute"):
            smoke.normalize_base_url("rocky.example")


if __name__ == "__main__":
    unittest.main()
