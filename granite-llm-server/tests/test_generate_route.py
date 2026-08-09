import json
import unittest
from unittest.mock import Mock, patch

import requests

import app.main as granite_main
from app.main import app as flask_app


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

    def test_generate_returns_retryable_busy_response(self):
        gate = Mock()
        gate.acquire.return_value = False
        with patch.object(granite_main, "INFERENCE_GATE", gate):
            response = self.client.post("/generate", json=granite_payload())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"]["type"], "model_busy")
        self.assertEqual(response.headers["Retry-After"], "2")

    def test_ready_checks_ollama_and_configured_model(self):
        with patch.object(granite_main, "check_ollama_readiness", return_value=True) as check:
            response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["dependencies"]["ollama"])
        check.assert_called_once()

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
