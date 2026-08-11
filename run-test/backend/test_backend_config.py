from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend import config


class BackendConfigurationTests(unittest.TestCase):
    def settings_for(self, values: dict[str, str]):
        with (
            patch.dict(os.environ, values, clear=True),
            patch.object(config, "_load_env_files"),
        ):
            return config.get_settings()

    def test_development_defaults_are_local_and_consistent(self):
        settings = self.settings_for({})

        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.db_backend, "mongita")
        self.assertEqual((settings.host, settings.port), ("127.0.0.1", 5001))
        self.assertTrue(settings.debug)
        self.assertTrue(settings.enable_db_inspector)
        self.assertTrue(settings.enable_preview_login)

    def test_production_defaults_to_mongodb_and_microsoft_authentication(self):
        settings = self.settings_for(
            {
                "ROCKY_APP_ENV": "production",
                "ROCKY_MONGODB_URI": "mongodb://database.example/rocky",
                "ROCKY_HIDDEN_API_KEY_SECRET": "h" * 40,
                "ROCKY_INTERNAL_PROXY_SECRET": "p" * 40,
            }
        )

        self.assertEqual(settings.db_backend, "mongodb")
        self.assertFalse(settings.debug)
        self.assertFalse(settings.enable_db_inspector)
        self.assertFalse(settings.enable_preview_login)
        self.assertTrue(settings.enable_microsoft_oauth)

    def test_invalid_environment_values_fail_with_the_setting_name(self):
        invalid_cases = (
            ({"ROCKY_APP_ENV": "prod"}, "ROCKY_APP_ENV"),
            ({"ROCKY_DB_BACKEND": "sqlite"}, "ROCKY_DB_BACKEND"),
            ({"ROCKY_DEBUG": "yes"}, "ROCKY_DEBUG"),
            ({"ROCKY_API_PORT": "abc"}, "ROCKY_API_PORT"),
            ({"ROCKY_API_PORT": "70000"}, "ROCKY_API_PORT"),
            (
                {"ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS": "9"},
                "ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS",
            ),
        )
        for values, expected_name in invalid_cases:
            with self.subTest(values=values):
                with self.assertRaisesRegex(RuntimeError, expected_name):
                    self.settings_for(values)

    def test_production_rejects_unsafe_overrides_and_placeholders(self):
        base = {
            "ROCKY_APP_ENV": "production",
            "ROCKY_MONGODB_URI": "mongodb://database.example/rocky",
            "ROCKY_HIDDEN_API_KEY_SECRET": "h" * 40,
            "ROCKY_INTERNAL_PROXY_SECRET": "p" * 40,
        }
        invalid_cases = (
            ({"ROCKY_DB_BACKEND": "mongita"}, "ROCKY_DB_BACKEND"),
            ({"ROCKY_DEBUG": "true"}, "ROCKY_DEBUG"),
            ({"ROCKY_ENABLE_DB_INSPECTOR": "true"}, "ROCKY_ENABLE_DB_INSPECTOR"),
            (
                {"ROCKY_HIDDEN_API_KEY_SECRET": "replace-with-a-long-random-secret"},
                "ROCKY_HIDDEN_API_KEY_SECRET",
            ),
        )
        for override, expected_name in invalid_cases:
            with self.subTest(override=override):
                with self.assertRaisesRegex(RuntimeError, expected_name):
                    self.settings_for({**base, **override})

    def test_enabled_hardware_telemetry_validates_url_and_token(self):
        development = {
            "ROCKY_HARDWARE_TELEMETRY_ENABLED": "true",
            "ROCKY_HARDWARE_METRICS_URL": "not-a-url",
        }
        with self.assertRaisesRegex(RuntimeError, "ROCKY_HARDWARE_METRICS_URL"):
            self.settings_for(development)

        production = {
            "ROCKY_APP_ENV": "production",
            "ROCKY_MONGODB_URI": "mongodb://database.example/rocky",
            "ROCKY_HIDDEN_API_KEY_SECRET": "h" * 40,
            "ROCKY_INTERNAL_PROXY_SECRET": "p" * 40,
            "ROCKY_HARDWARE_TELEMETRY_ENABLED": "true",
            "ROCKY_HARDWARE_METRICS_URL": "http://granite.example:5010/hardware",
            "ROCKY_HARDWARE_METRICS_TOKEN": "short",
        }
        with self.assertRaisesRegex(RuntimeError, "ROCKY_HARDWARE_METRICS_TOKEN"):
            self.settings_for(production)

        for value in (
            "http://granite.example:5010/hardware?tenant=one",
            "http://granite.example:5010/hardware#internal",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    RuntimeError, "ROCKY_HARDWARE_METRICS_URL"
                ):
                    self.settings_for(
                        {
                            "ROCKY_HARDWARE_TELEMETRY_ENABLED": "true",
                            "ROCKY_HARDWARE_METRICS_URL": value,
                        }
                    )


if __name__ == "__main__":
    unittest.main()
