import unittest
from unittest.mock import Mock, patch

from app.main import app as flask_app


# Run from the granite-llm-server directory:
# python -m unittest tests.test_generate_route -v


class TestGenerateRoute(unittest.TestCase):

    def setUp(self):
        flask_app.config["TESTING"] = True
        self.client = flask_app.test_client()

    @patch("app.ollama_client.requests.post")
    def test_generate_sends_exact_payload_to_ollama_with_reasoning(
        self,
        mock_post
    ):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {
                "content": "Fake Ollama response",
                "thinking": "Fake private reasoning"
            }
        }
        mock_post.return_value = mock_response

        granite_payload = {
            "model": "gemma4:latest",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Explain gradient descent."
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
                    "content": "Explain gradient descent."
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
            "Fake Ollama response"
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

        mock_post.assert_called_once()

        _, keyword_arguments = mock_post.call_args
        actual_ollama_payload = keyword_arguments["json"]

        self.assertEqual(
            actual_ollama_payload,
            expected_ollama_payload
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
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {
                "content": "Fake Ollama response"
            }
        }
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
        actual_ollama_payload = keyword_arguments["json"]

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
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {
                "content": "Answer without a thinking field"
            }
        }
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

        # The request reached Ollama, but Ollama did not fulfill
        # the reasoning portion of the contract.
        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()