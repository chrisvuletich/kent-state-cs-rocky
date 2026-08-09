from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import AuthenticationError, OpenAI


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "api.py"


def load_test_api():
    spec = importlib.util.spec_from_file_location("api_rocky_openai_compat", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load api-rocky for OpenAI SDK compatibility tests.")

    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(API_ROCKY_DIR))
    try:
        with patch.dict(os.environ, {
            "ROCKY_APP_ENV": "test",
            "ROCKY_CHAT_API_KEY": "",
            "ROCKY_TELEMETRY_ENABLED": "false",
            "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
        }):
            spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(API_ROCKY_DIR))
    return module


class OpenAiSdkCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_test_api()
        cls.api.app.config["TESTING"] = True
        cls.flask_client = cls.api.app.test_client()

    def sdk_client(self, api_key="valid-key"):
        def forward(request: httpx.Request) -> httpx.Response:
            response = self.flask_client.open(
                path=request.url.raw_path.decode("utf-8"),
                method=request.method,
                headers=dict(request.headers),
                data=request.content,
            )
            return httpx.Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=response.data,
                request=request,
            )

        http_client = httpx.Client(transport=httpx.MockTransport(forward))
        return OpenAI(
            api_key=api_key,
            base_url="http://rocky.test/v1",
            http_client=http_client,
            max_retries=0,
        )

    def test_models_list_parses_with_official_sdk(self):
        with patch.object(self.api, "get_key_doc", return_value={"key_id": "key-one"}):
            with self.sdk_client() as client:
                models = client.models.list()

        self.assertEqual(len(models.data), 1)
        self.assertEqual(models.data[0].id, self.api.PUBLIC_MODEL)
        self.assertEqual(models.data[0].object, "model")
        self.assertEqual(models.data[0].owned_by, "kent-state")

    def test_response_create_exposes_output_text(self):
        with (
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Compatible response",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ),
        ):
            with self.sdk_client() as client:
                response = client.responses.create(
                    model=self.api.PUBLIC_MODEL,
                    input="Compatibility check",
                    store=False,
                )

        self.assertEqual(response.status, "completed")
        self.assertEqual(response.output_text, "Compatible response")

    def test_authentication_error_parses_with_official_sdk(self):
        with patch.object(self.api, "get_key_doc", return_value=None):
            with self.assertRaises(AuthenticationError) as raised:
                with self.sdk_client(api_key="invalid-key") as client:
                    client.models.list()

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
