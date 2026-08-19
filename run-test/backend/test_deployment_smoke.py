from __future__ import annotations

import importlib.util
import json
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
    def __init__(self, status_code, payload, headers=None, lines=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._lines = lines
        self.closed = False

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        if self._lines is None:
            raise AssertionError("This fake response was not configured as a stream.")
        for line in self._lines:
            yield line if decode_unicode else line.encode("utf-8")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.routes[(method, url)]
        if isinstance(response, list):
            if not response:
                raise AssertionError(f"No fake responses remain for {method} {url}.")
            return response.pop(0)
        return response


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
            {
                "object": "list",
                "data": [
                    {
                        "id": "course-model",
                        "object": "model",
                        "metadata": {
                            "supports_streaming": True,
                            "supports_image_input": True,
                        },
                    }
                ],
            },
            {
                "X-RateLimit-Limit-Requests": "120",
                "x-ratelimit-remaining-requests": "119",
                "X-Ratelimit-Reset-Requests": "42s",
            },
        ),
        ("POST", f"{base_url}/v1/responses"): FakeResponse(
            200,
            {
                "status": "completed",
                "model": "course-model",
                "output_text": "Rocky deployment smoke passed.",
                "usage": {"input_tokens": 8, "output_tokens": 5, "total_tokens": 13},
            },
            {
                "x-request-id": "req_smoke",
                "x-ratelimit-limit-requests": "10",
                "x-ratelimit-remaining-requests": "9",
                "x-ratelimit-reset-requests": "42s",
            },
        ),
    }


def sse_lines(events):
    lines = []
    for event in events:
        lines.extend(
            (
                f"event: {event['type']}",
                "data: " + json.dumps(event, separators=(",", ":")),
                "",
            )
        )
    return lines


def successful_stream_response(model="course-model", output_text="Rocky passed."):
    item = {
        "id": "msg_smoke",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [
            {"type": "output_text", "text": output_text, "annotations": []}
        ],
    }
    events = [
        {"type": "response.created", "sequence_number": 0},
        {"type": "response.in_progress", "sequence_number": 1},
        {"type": "response.output_item.added", "sequence_number": 2},
        {"type": "response.content_part.added", "sequence_number": 3},
        {
            "type": "response.output_text.delta",
            "sequence_number": 4,
            "delta": output_text,
        },
        {
            "type": "response.output_text.done",
            "sequence_number": 5,
            "text": output_text,
        },
        {
            "type": "response.content_part.done",
            "sequence_number": 6,
            "part": {"type": "output_text", "text": output_text},
        },
        {
            "type": "response.output_item.done",
            "sequence_number": 7,
            "item": item,
        },
        {
            "type": "response.completed",
            "sequence_number": 8,
            "response": {
                "status": "completed",
                "model": model,
                "output": [item],
                "usage": {"input_tokens": 2, "output_tokens": 2, "total_tokens": 4},
            },
        },
    ]
    return FakeResponse(
        200,
        {},
        {
            "Content-Type": "text/event-stream; charset=utf-8",
            "x-request-id": "req_stream_smoke",
            "x-ratelimit-limit-requests": "10",
            "x-ratelimit-remaining-requests": "9",
            "x-ratelimit-reset-requests": "42s",
        },
        sse_lines(events),
    )


class DeploymentSmokeTests(unittest.TestCase):
    def config(
        self,
        include_generation=False,
        include_streaming=False,
        include_image=False,
        include_advertised=False,
        expected_model="course-model",
    ):
        return smoke.SmokeConfig(
            base_url="https://rocky.example",
            api_key="sk_kent_test_value",
            expected_model=expected_model,
            timeout_seconds=5,
            include_generation=include_generation,
            include_streaming=include_streaming,
            include_image=include_image,
            include_advertised=include_advertised,
        )

    def test_non_generating_smoke_checks_public_health_and_models(self):
        session = FakeSession(successful_routes())
        checks = smoke.DeploymentSmoke(self.config(), session=session).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(
            [check.name for check in checks],
            [
                "web health",
                "service health",
                "model discovery",
                "model rate limit",
            ],
        )
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
        self.assertEqual(
            [check.name for check in checks][-2:],
            [
                "generation",
                "generation rate limit",
            ],
        )
        generation_call = next(call for call in session.calls if call[0] == "POST")
        self.assertEqual(generation_call[2]["json"]["model"], "course-model")
        self.assertEqual(generation_call[2]["json"]["store"], False)
        self.assertEqual(generation_call[2]["json"]["max_output_tokens"], 32)

    def test_generation_reports_missing_rate_limit_headers_separately(self):
        routes = successful_routes()
        generation_response = routes[("POST", "https://rocky.example/v1/responses")]
        generation_response.headers = {"x-request-id": "req_smoke"}

        checks = smoke.DeploymentSmoke(
            self.config(include_generation=True),
            session=FakeSession(routes),
        ).run()

        self.assertTrue(checks[4].passed)
        self.assertFalse(checks[5].passed)
        self.assertIn("Missing required header", checks[5].detail)

    def test_streaming_generation_is_explicit_and_validates_the_sse_contract(self):
        routes = successful_routes()
        stream_response = successful_stream_response()
        routes[("POST", "https://rocky.example/v1/responses")] = stream_response
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_streaming=True),
            session=session,
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(
            [check.name for check in checks][-2:],
            ["streaming generation", "streaming generation rate limit"],
        )
        stream_call = next(call for call in session.calls if call[0] == "POST")
        self.assertIs(stream_call[2]["stream"], True)
        self.assertIs(stream_call[2]["json"]["stream"], True)
        self.assertIs(stream_call[2]["json"]["store"], False)
        self.assertEqual(stream_call[2]["headers"]["Accept"], "text/event-stream")
        self.assertTrue(stream_response.closed)

    def test_stream_validator_accepts_the_public_golden_fixture(self):
        fixture = ROOT / "run-test" / "fixtures" / "responses_text_stream.sse"
        events = smoke.parse_stream_events(fixture.read_text(encoding="utf-8").splitlines())

        output_text = smoke.validate_stream_events(events, "rocky-contract-model")

        self.assertEqual(output_text, "Hello Rocky!")

    def test_streaming_generation_rejects_a_sequence_gap(self):
        routes = successful_routes()
        stream_response = successful_stream_response()
        stream_response._lines = [
            line.replace('"sequence_number":4', '"sequence_number":9')
            for line in stream_response._lines
        ]
        routes[("POST", "https://rocky.example/v1/responses")] = stream_response

        checks = smoke.DeploymentSmoke(
            self.config(include_streaming=True),
            session=FakeSession(routes),
        ).run()

        self.assertFalse(checks[4].passed)
        self.assertIn("Expected sequence_number 4", checks[4].detail)
        self.assertTrue(checks[5].passed)
        self.assertTrue(stream_response.closed)

    def test_streaming_generation_reports_a_terminal_error_event(self):
        routes = successful_routes()
        stream_response = FakeResponse(
            200,
            {},
            {
                "content-type": "text/event-stream",
                "x-request-id": "req_stream_error",
                "x-ratelimit-limit-requests": "10",
                "x-ratelimit-remaining-requests": "9",
                "x-ratelimit-reset-requests": "42s",
            },
            sse_lines(
                [
                    {"type": "response.created", "sequence_number": 0},
                    {
                        "type": "error",
                        "sequence_number": 1,
                        "code": "model_timeout",
                        "message": "Model request timed out.",
                    },
                ]
            ),
        )
        routes[("POST", "https://rocky.example/v1/responses")] = stream_response

        checks = smoke.DeploymentSmoke(
            self.config(include_streaming=True),
            session=FakeSession(routes),
        ).run()

        self.assertFalse(checks[4].passed)
        self.assertIn("model_timeout", checks[4].detail)
        self.assertTrue(checks[5].passed)

    def test_streaming_generation_is_not_sent_without_advertised_support(self):
        routes = successful_routes()
        model = routes[("GET", "https://rocky.example/v1/models")]._payload["data"][0]
        model["metadata"]["supports_streaming"] = False
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_streaming=True),
            session=session,
        ).run()

        self.assertFalse(checks[4].passed)
        self.assertIn("supports_streaming=true", checks[4].detail)
        self.assertFalse(any(method == "POST" for method, _url, _kwargs in session.calls))

    def test_image_generation_uses_the_bounded_public_content_shape(self):
        session = FakeSession(successful_routes())

        checks = smoke.DeploymentSmoke(
            self.config(include_image=True),
            session=session,
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(
            [check.name for check in checks][-2:],
            ["image generation", "image generation rate limit"],
        )
        image_call = next(call for call in session.calls if call[0] == "POST")
        payload = image_call[2]["json"]
        blocks = payload["input"][0]["content"]
        self.assertIs(payload["stream"], False)
        self.assertIs(payload["store"], False)
        self.assertEqual(blocks[0]["type"], "input_text")
        self.assertEqual(blocks[1]["type"], "input_image")
        self.assertEqual(blocks[1]["detail"], "auto")
        self.assertTrue(blocks[1]["image_url"].startswith("data:image/png;base64,"))

    def test_all_opt_in_generation_checks_can_run_together(self):
        routes = successful_routes()
        buffered_response = routes[("POST", "https://rocky.example/v1/responses")]
        routes[("POST", "https://rocky.example/v1/responses")] = [
            buffered_response,
            successful_stream_response(),
            buffered_response,
        ]
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(
                include_generation=True,
                include_streaming=True,
                include_image=True,
            ),
            session=session,
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(len(checks), 10)
        post_calls = [call for call in session.calls if call[0] == "POST"]
        self.assertEqual(len(post_calls), 3)
        self.assertNotIn("stream", post_calls[0][2]["json"])
        self.assertIs(post_calls[1][2]["json"]["stream"], True)
        self.assertIs(post_calls[2][2]["json"]["stream"], False)

    def test_advertised_mode_runs_every_supported_inference_path(self):
        routes = successful_routes()
        buffered_response = routes[("POST", "https://rocky.example/v1/responses")]
        routes[("POST", "https://rocky.example/v1/responses")] = [
            buffered_response,
            successful_stream_response(),
            buffered_response,
        ]
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_advertised=True),
            session=session,
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(len([call for call in session.calls if call[0] == "POST"]), 3)
        self.assertEqual(
            [check.name for check in checks[4::2]],
            ["generation", "streaming generation", "image generation"],
        )

    def test_advertised_mode_does_not_require_an_unadvertised_capability(self):
        routes = successful_routes()
        model = routes[("GET", "https://rocky.example/v1/models")]._payload["data"][0]
        model["metadata"]["supports_image_input"] = False
        buffered_response = routes[("POST", "https://rocky.example/v1/responses")]
        routes[("POST", "https://rocky.example/v1/responses")] = [
            buffered_response,
            successful_stream_response(),
        ]
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_advertised=True),
            session=session,
        ).run()

        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(len([call for call in session.calls if call[0] == "POST"]), 2)
        self.assertNotIn("image generation", [check.name for check in checks])

    def test_image_generation_is_not_sent_without_advertised_support(self):
        routes = successful_routes()
        model = routes[("GET", "https://rocky.example/v1/models")]._payload["data"][0]
        model["metadata"]["supports_image_input"] = False
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_image=True),
            session=session,
        ).run()

        self.assertFalse(checks[4].passed)
        self.assertIn("supports_image_input=true", checks[4].detail)
        self.assertFalse(any(method == "POST" for method, _url, _kwargs in session.calls))

    def test_generation_is_skipped_when_a_prerequisite_check_fails(self):
        routes = successful_routes()
        routes[("GET", "https://rocky.example/api/server-health")] = FakeResponse(
            503,
            {
                "ok": False,
                "services": [{"name": "ollama", "ok": False}],
            },
        )
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_generation=True), session=session
        ).run()

        self.assertFalse(checks[1].passed)
        self.assertFalse(checks[4].passed)
        self.assertIn("service health", checks[4].detail)
        self.assertFalse(any(method == "POST" for method, _url, _kwargs in session.calls))

    def test_generation_is_skipped_when_model_rate_limit_contract_fails(self):
        routes = successful_routes()
        routes[("GET", "https://rocky.example/v1/models")].headers = {}
        session = FakeSession(routes)

        checks = smoke.DeploymentSmoke(
            self.config(include_generation=True), session=session
        ).run()

        self.assertTrue(checks[2].passed)
        self.assertFalse(checks[3].passed)
        self.assertFalse(checks[4].passed)
        self.assertIn("model rate limit", checks[4].detail)
        self.assertFalse(any(method == "POST" for method, _url, _kwargs in session.calls))

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
        self.assertTrue(checks[3].passed)

    def test_missing_rate_limit_headers_fail_the_deployed_contract(self):
        routes = successful_routes()
        routes[("GET", "https://rocky.example/v1/models")].headers = {}

        checks = smoke.DeploymentSmoke(self.config(), session=FakeSession(routes)).run()

        self.assertTrue(checks[2].passed)
        self.assertFalse(checks[3].passed)
        self.assertIn("x-ratelimit-limit-requests", checks[3].detail)
        self.assertIn("x-ratelimit-reset-requests", checks[3].detail)

    def test_rate_limit_header_validation_rejects_malformed_values(self):
        invalid_headers = (
            (
                {
                    "x-ratelimit-limit-requests": "ten",
                    "x-ratelimit-remaining-requests": "9",
                    "x-ratelimit-reset-requests": "42s",
                },
                "positive integer",
            ),
            (
                {
                    "x-ratelimit-limit-requests": "10",
                    "x-ratelimit-remaining-requests": "11",
                    "x-ratelimit-reset-requests": "42s",
                },
                "cannot exceed",
            ),
            (
                {
                    "x-ratelimit-limit-requests": "10",
                    "x-ratelimit-remaining-requests": "9",
                    "x-ratelimit-reset-requests": "61s",
                },
                "between 1s and 60s",
            ),
            (
                {
                    "x-ratelimit-limit-requests": "10",
                    "x-ratelimit-remaining-requests": "9",
                    "x-ratelimit-reset-requests": "soon",
                },
                "whole number of seconds",
            ),
        )

        for headers, expected_detail in invalid_headers:
            with self.subTest(headers=headers):
                check = smoke.check_rate_limit_headers(
                    FakeResponse(200, {}, headers),
                    "rate limit",
                )
                self.assertFalse(check.passed)
                self.assertIn(expected_detail, check.detail)

    def test_configuration_uses_environment_without_exposing_key(self):
        args = smoke.parse_args(
            [
                "--base-url",
                "https://rocky.example/v1/responses",
                "--include-streaming",
                "--include-image",
                "--include-advertised",
            ]
        )
        with patch.dict(
            os.environ,
            {"ROCKY_API_KEY": "sk_kent_secret", "ROCKY_EXPECTED_MODEL": "course-model"},
            clear=False,
        ):
            config = smoke.build_config(args)

        self.assertEqual(config.base_url, "https://rocky.example")
        self.assertEqual(config.api_key, "sk_kent_secret")
        self.assertTrue(config.include_streaming)
        self.assertTrue(config.include_image)
        self.assertTrue(config.include_advertised)
        self.assertNotIn("sk_kent_secret", repr(config))

    def test_configuration_rejects_missing_key_and_invalid_url(self):
        with patch.dict(os.environ, {"ROCKY_API_KEY": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "ROCKY_API_KEY"):
                smoke.build_config(smoke.parse_args(["--base-url", "https://rocky.example"]))

        with self.assertRaisesRegex(ValueError, "absolute"):
            smoke.normalize_base_url("rocky.example")

        for value in (
            "https://rocky.example?tenant=one",
            "https://rocky.example#internal",
            "https://user:password@rocky.example",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "ROCKY_BASE_URL"
            ):
                smoke.normalize_base_url(value)


if __name__ == "__main__":
    unittest.main()
