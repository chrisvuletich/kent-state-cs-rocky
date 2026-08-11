from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from run_env import env_bool, normalize_chat_api_urls


class RunEnvironmentTests(unittest.TestCase):
    def test_boolean_values_are_exact(self):
        for raw_value, expected in (("true", True), (" FALSE ", False)):
            with self.subTest(raw_value=raw_value):
                with patch.dict(os.environ, {"ROCKY_TEST_FLAG": raw_value}, clear=True):
                    self.assertEqual(env_bool("ROCKY_TEST_FLAG", False), expected)

    def test_invalid_boolean_names_the_setting(self):
        with patch.dict(os.environ, {"ROCKY_TEST_FLAG": "yes"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ROCKY_TEST_FLAG"):
                env_bool("ROCKY_TEST_FLAG", False)

    def test_chat_url_accepts_a_base_or_generation_endpoint(self):
        expected = (
            "http://127.0.0.1:5003/v1/responses",
            "http://127.0.0.1:5003",
        )
        for value in (
            "http://127.0.0.1:5003",
            "http://127.0.0.1:5003/",
            "http://127.0.0.1:5003/v1/responses",
            "http://127.0.0.1:5003/v1/responses/",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_chat_api_urls(value), expected)

    def test_chat_url_supports_a_reverse_proxy_base_path(self):
        self.assertEqual(
            normalize_chat_api_urls("https://rocky.example.edu/chat"),
            (
                "https://rocky.example.edu/chat/v1/responses",
                "https://rocky.example.edu/chat",
            ),
        )

    def test_chat_url_rejects_ambiguous_or_unsafe_values(self):
        for value in (
            "",
            "localhost:5003/v1/responses",
            "ftp://localhost/v1/responses",
            "http://user:password@localhost:5003/v1/responses",
            "http://localhost:5003/v1/responses?tenant=one",
            "http://localhost:5003/v1/responses#internal",
            "http://localhost:70000/v1/responses",
            "http://local host:5003/v1/responses",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "ROCKY_CHAT_API_URL"):
                    normalize_chat_api_urls(value)


if __name__ == "__main__":
    unittest.main()
