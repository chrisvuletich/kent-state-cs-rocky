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
    def test_generate_sends_exact_payload_to_ollama(self, mock_post):
        # Arrange: create a fake successful Ollama HTTP response.
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {
                "content": "Fake Ollama response"
            }
        }
        mock_post.return_value = mock_response

        granite_payload = {
            "model": "qwen3:0.6b",
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
            "top_p": 0.9
        }

        expected_ollama_payload = {
            "model": "qwen3:0.6b",
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
                "top_p": 0.9
            }
        }

        # Act: send the request through the real Flask route.
        response = self.client.post("/generate", json=granite_payload)

        # Assert: Granite returned a successful response.
        self.assertEqual(response.status_code, 200)

        response_data = response.get_json()

        self.assertEqual(response_data["model"], "qwen3:0.6b")
        self.assertEqual(
            response_data["output_text"],
            "Fake Ollama response"
        )
        self.assertEqual(
            response_data["metadata"]["source"],
            "ollama"
        )

        # Assert: the external Ollama request happened exactly once.
        mock_post.assert_called_once()

        # requests.post(url, json=ollama_payload, timeout=...)
        _, keyword_arguments = mock_post.call_args

        actual_ollama_payload = keyword_arguments["json"]

        self.assertEqual(
            actual_ollama_payload,
            expected_ollama_payload
        )

    @patch("app.ollama_client.requests.post")
    def test_generate_returns_400_and_does_not_call_ollama_when_validation_fails(
        self,
        mock_post
    ):
        invalid_payload = {
            "model": "qwen3:0.6b",
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

        response = self.client.post("/generate", json=invalid_payload)

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


if __name__ == "__main__":
    unittest.main()