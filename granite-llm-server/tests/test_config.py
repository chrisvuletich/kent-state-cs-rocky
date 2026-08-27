from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app import config


class GraniteConfigurationTests(unittest.TestCase):
    def test_valid_values_are_parsed(self):
        values = {
            "ROCKY_APP_ENV": "production",
            "ROCKY_GRANITE_PORT": "5002",
            "ROCKY_GRANITE_QUEUE_CAPACITY": "12",
            "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS": "0.25",
            "ROCKY_GRANITE_QUEUE_MAX_BYTES": "67108864",
            "ROCKY_GRANITE_QUEUE_WAIT_SECONDS": "0.5",
            "ROCKY_ENABLE_STREAMING": "true",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434/",
        }
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(config.app_env(), "production")
            self.assertEqual(
                config.env_int("ROCKY_GRANITE_PORT", 5002, minimum=1, maximum=65535),
                5002,
            )
            self.assertEqual(
                config.env_float(
                    "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS",
                    10,
                    minimum=0.1,
                ),
                0.25,
            )
            self.assertEqual(
                config.env_int(
                    "ROCKY_GRANITE_QUEUE_CAPACITY", 12, minimum=0
                ),
                12,
            )
            self.assertEqual(
                config.env_int(
                    "ROCKY_GRANITE_QUEUE_MAX_BYTES", 67108864, minimum=0
                ),
                67108864,
            )
            self.assertEqual(
                config.env_float(
                    "ROCKY_GRANITE_QUEUE_WAIT_SECONDS", 120, minimum=0
                ),
                0.5,
            )
            self.assertEqual(
                config.env_http_url("OLLAMA_BASE_URL", "http://localhost:11434"),
                "http://127.0.0.1:11434",
            )
            self.assertTrue(config.env_bool("ROCKY_ENABLE_STREAMING", False))

    def test_invalid_values_fail_with_the_setting_name(self):
        invalid_cases = (
            ("ROCKY_APP_ENV", "prod", config.app_env, ()),
            (
                "ROCKY_GRANITE_PORT",
                "70000",
                config.env_int,
                (5002,),
                {"minimum": 1, "maximum": 65535},
            ),
            (
                "ROCKY_GRANITE_QUEUE_CAPACITY",
                "-1",
                config.env_int,
                (12,),
                {"minimum": 0},
            ),
            (
                "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS",
                "0.09",
                config.env_float,
                (10,),
                {"minimum": 0.1},
            ),
            (
                "ROCKY_GRANITE_QUEUE_MAX_BYTES",
                "unbounded",
                config.env_int,
                (67108864,),
                {"minimum": 0},
            ),
            (
                "ROCKY_GRANITE_QUEUE_WAIT_SECONDS",
                "nan",
                config.env_float,
                (120,),
                {"minimum": 0},
            ),
            (
                "ROCKY_ENABLE_STREAMING",
                "yes",
                config.env_bool,
                (False,),
            ),
            (
                "OLLAMA_BASE_URL",
                "http://user:password@localhost:11434",
                config.env_http_url,
                ("http://127.0.0.1:11434",),
            ),
            (
                "OLLAMA_BASE_URL",
                "http://localhost:11434?tenant=one",
                config.env_http_url,
                ("http://127.0.0.1:11434",),
            ),
            (
                "OLLAMA_BASE_URL",
                "http://localhost:11434#internal",
                config.env_http_url,
                ("http://127.0.0.1:11434",),
            ),
        )
        for case in invalid_cases:
            name, value, parser, arguments, *keyword_values = case
            kwargs = keyword_values[0] if keyword_values else {}
            with self.subTest(name=name):
                with (
                    patch.dict(os.environ, {name: value}, clear=True),
                    self.assertRaisesRegex(RuntimeError, name),
                ):
                    parser(*arguments, **kwargs) if parser is config.app_env else parser(
                        name, *arguments, **kwargs
                    )

    def test_production_secret_rejects_short_and_placeholder_values(self):
        for value in (
            "short",
            "replace-with-a-long-random-granite-token",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "ROCKY_GRANITE_TOKEN"):
                    config.require_production_secret("ROCKY_GRANITE_TOKEN", value)


if __name__ == "__main__":
    unittest.main()
