from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from openai import AuthenticationError, OpenAI


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
MODULE_PATH = API_ROCKY_DIR / "api.py"
IMAGE_INPUT_FIXTURE = ROOT / "run-test" / "fixtures" / "responses_image_input.json"


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

    def granite_stream(self, *deltas: str):
        upstream_response = Mock()
        events = [
            {"type": "delta", "text": delta}
            for delta in deltas
        ]
        events.append(
            {
                "type": "completed",
                "telemetry": {
                    "provider": {
                        "prompt_eval_count": 2,
                        "eval_count": 2,
                    },
                },
                "metadata": {},
            }
        )
        return self.api.GraniteEventStream(
            upstream_response,
            iter(
                json.dumps(event, separators=(",", ":")).encode("utf-8") + b"\n"
                for event in events
            ),
            [0],
            self.api.INFERENCE_MODEL,
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

    def test_response_stream_iterates_with_official_sdk(self):
        granite_stream = self.granite_stream("Compatible ", "stream")
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
        ):
            with self.sdk_client() as client:
                stream = client.responses.create(
                    model=self.api.PUBLIC_MODEL,
                    input="Compatibility check",
                    store=False,
                    stream=True,
                )
                received = list(stream)

        self.assertEqual(received[0].type, "response.created")
        self.assertEqual(received[-1].type, "response.completed")
        self.assertEqual(received[-1].response.output_text, "Compatible stream")

    def test_response_image_input_can_stream_through_official_sdk(self):
        payload = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        content = payload["input"][0]["content"]
        granite_stream = self.granite_stream("Compatible image ", "stream")
        with (
            patch.object(self.api, "ENABLE_STREAMING", True),
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai_stream",
                return_value=granite_stream,
            ) as request_ai_stream,
        ):
            with self.sdk_client() as client:
                stream = client.responses.create(
                    model=self.api.PUBLIC_MODEL,
                    input=[{"role": "user", "content": content}],
                    store=False,
                    stream=True,
                )
                received = list(stream)

        self.assertEqual(received[-1].type, "response.completed")
        self.assertEqual(received[-1].response.output_text, "Compatible image stream")
        internal_image = request_ai_stream.call_args.args[0]["input"][0]["content"][1]
        self.assertEqual(internal_image["type"], "input_image")
        self.assertEqual(internal_image["mime_type"], "image/png")
        self.assertNotIn("image_url", internal_image)

    def test_response_image_input_is_accepted_from_official_sdk(self):
        payload = json.loads(IMAGE_INPUT_FIXTURE.read_text(encoding="utf-8"))
        content = payload["input"][0]["content"]
        with (
            patch.object(self.api, "ENABLE_IMAGE_INPUT", True),
            patch.object(
                self.api,
                "get_key_doc",
                return_value={"key_id": "key-one", "owner_id": "student-one"},
            ),
            patch.object(
                self.api,
                "request_ai",
                return_value={
                    "output_text": "Compatible image response",
                    "model": self.api.INFERENCE_MODEL,
                    "metadata": {},
                },
            ) as request_ai,
        ):
            with self.sdk_client() as client:
                response = client.responses.create(
                    model=self.api.PUBLIC_MODEL,
                    input=[{"role": "user", "content": content}],
                    store=False,
                )

        self.assertEqual(response.output_text, "Compatible image response")
        internal_image = request_ai.call_args.args[0]["input"][0]["content"][1]
        self.assertEqual(internal_image["type"], "input_image")
        self.assertEqual(internal_image["mime_type"], "image/png")
        self.assertNotIn("image_url", internal_image)

    def test_authentication_error_parses_with_official_sdk(self):
        with patch.object(self.api, "get_key_doc", return_value=None):
            with self.assertRaises(AuthenticationError) as raised:
                with self.sdk_client(api_key="invalid-key") as client:
                    client.models.list()

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
