from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rocky_tools.doctor import RockyDoctor


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.routes[url]


def production_env():
    return {
        "ROCKY_APP_ENV": "production",
        "PUBLIC_APP_ENV": "production",
        "ROCKY_DB_BACKEND": "mongodb",
        "ROCKY_DB_NAME": "rocky_db",
        "ROCKY_MONGODB_URI": "mongodb://database.example/rocky_db",
        "PUBLIC_API_BASE_URL": "http://127.0.0.1:5001",
        "ROCKY_API_HOST": "127.0.0.1",
        "ROCKY_API_PORT": "5001",
        "ROCKY_CHAT_API_URL": "http://127.0.0.1:5003/v1/responses",
        "ROCKY_GRANITE_URL": "http://granite.example:5002/generate",
        "ROCKY_GRANITE_READY_URL": "http://granite.example:5002/ready",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OLLAMA_MODEL": "course-model",
        "ROCKY_PUBLIC_MODEL": "course-model",
        "ROCKY_HIDDEN_API_KEY_SECRET": "h" * 40,
        "ROCKY_SESSION_SECRET": "s" * 40,
        "ROCKY_INTERNAL_PROXY_SECRET": "p" * 40,
        "ROCKY_GRANITE_TOKEN": "g" * 40,
        "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE": "10",
        "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE": "120",
        "BODY_SIZE_LIMIT": "10M",
        "ROCKY_GRANITE_TIMEOUT_SECONDS": "315",
        "ROCKY_OLLAMA_TIMEOUT_SECONDS": "150",
        "ROCKY_GRANITE_QUEUE_WAIT_SECONDS": "120",
        "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS": "10",
        "ROCKY_GRANITE_MAX_CONCURRENT": "1",
        "ROCKY_GRANITE_QUEUE_CAPACITY": "12",
        "ROCKY_GRANITE_QUEUE_MAX_BYTES": str(64 * 1024 * 1024),
        "PUBLIC_ENABLE_MICROSOFT_OAUTH": "true",
        "PUBLIC_MICROSOFT_CLIENT_ID": "client-id",
        "PUBLIC_MICROSOFT_TENANT_ID": "tenant-id",
    }


def healthy_routes():
    return {
        "http://127.0.0.1:5001/health": FakeResponse(
            200, {"ok": True, "service": "rocky-backend"}
        ),
        "http://127.0.0.1:5003/health": FakeResponse(
            200, {"ok": True, "service": "api-rocky"}
        ),
        "http://127.0.0.1:5003/ready": FakeResponse(
            200,
            {
                "ok": True,
                "dependencies": {"database": True, "granite": True},
                "models": {
                    "public": "course-model",
                    "inference": "course-model",
                    "granite": "course-model",
                },
                "capabilities": {
                    "supports_streaming": False,
                    "supports_image_input": False,
                    "max_images_per_request": 4,
                    "max_image_bytes": 4 * 1024 * 1024,
                    "max_image_total_bytes": 6 * 1024 * 1024,
                    "max_image_pixels": 20_000_000,
                    "max_image_total_pixels": 40_000_000,
                },
                "streaming": {
                    "rocky_enabled": False,
                    "granite_enabled": False,
                },
                "image_input": {
                    "rocky_enabled": False,
                    "granite_enabled": False,
                    "limits_match": True,
                },
                "timeouts": {
                    "granite_client_seconds": 315,
                    "granite": {
                        "ollama_request_seconds": 150,
                        "queue_wait_seconds": 120,
                        "heartbeat_seconds": 10,
                    },
                    "configuration_matches": True,
                },
                "queue": {
                    "active_requests": 0,
                    "waiting_requests": 0,
                    "queued_bytes": 0,
                    "max_active_requests": 1,
                    "max_waiting_requests": 12,
                    "max_queued_bytes": 64 * 1024 * 1024,
                },
                "queue_configuration_matches": True,
            },
        ),
        "http://granite.example:5002/ready": FakeResponse(
            200,
            {
                "ok": True,
                "model": "course-model",
                "dependencies": {"ollama": True, "model_available": True},
                "timeouts": {
                    "ollama_request_seconds": 150,
                    "queue_wait_seconds": 120,
                    "heartbeat_seconds": 10,
                },
                "queue": {
                    "active_requests": 0,
                    "waiting_requests": 0,
                    "queued_bytes": 0,
                    "max_active_requests": 1,
                    "max_waiting_requests": 12,
                    "max_queued_bytes": 64 * 1024 * 1024,
                },
            },
        ),
    }


class RockyDoctorTests(unittest.TestCase):
    def test_installed_deployment_files_have_queue_and_timeout_headroom(self):
        root = Path(__file__).resolve().parents[2]
        deployment_files = {
            "granite": root / "deploy/systemd/rocky-granite.service.example",
            "chat": root / "deploy/systemd/rocky-chat-api.service.example",
            "nginx": root / "deploy/nginx/rocky.cs.kent.edu.conf",
        }
        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(
                include_network=False,
                deployment_files=deployment_files,
            ).run()

        installed = [check for check in checks if check.name.startswith("installed ")]
        self.assertEqual(len(installed), 3)
        self.assertFalse(any(check.failed for check in installed))

    def test_installed_deployment_files_reject_outdated_capacity(self):
        root = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            granite = temporary / "rocky-granite.service"
            chat = temporary / "rocky-chat-api.service"
            nginx = temporary / "rocky.conf"
            granite.write_text(
                "ExecStart=/app/gunicorn --worker-class gthread --workers 1 "
                "--threads 4 --timeout 165 app.main:app\n",
                encoding="utf-8",
            )
            chat.write_text(
                "ExecStart=/app/gunicorn --worker-class gthread --workers 2 "
                "--threads 4 --timeout 330 api:app\n",
                encoding="utf-8",
            )
            nginx.write_text(
                "location = /v1/responses { proxy_read_timeout 190s; "
                "proxy_send_timeout 190s; }\n"
                "location / { proxy_read_timeout 190s; proxy_send_timeout 190s; }\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", production_env(), clear=True):
                checks = RockyDoctor(
                    include_network=False,
                    deployment_files={
                        "granite": granite,
                        "chat": chat,
                        "nginx": nginx,
                    },
                ).run()

        failures = {check.name: check.detail for check in checks if check.failed}
        self.assertIn("installed Granite systemd unit", failures)
        self.assertIn("installed chat API systemd unit", failures)
        self.assertIn("installed Nginx config", failures)
        self.assertIn("--threads must be at least 15", failures["installed Granite systemd unit"])
        self.assertIn("workers times threads must be at least 15", failures["installed chat API systemd unit"])
        self.assertIn("must exceed 330s", failures["installed Nginx config"])

    def test_image_input_rollout_body_budgets_are_accepted(self):
        values = production_env()
        values.update({
            "ROCKY_ENABLE_IMAGE_INPUT": "true",
            "ROCKY_MAX_REQUEST_BYTES": str(9 * 1024 * 1024),
            "ROCKY_GRANITE_MAX_REQUEST_BYTES": str(10 * 1024 * 1024),
        })
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(
            check for check in checks if check.name == "runtime settings"
        )
        self.assertEqual(runtime_check.status, "PASS")

    def test_production_requires_the_bounded_frontend_body_limit(self):
        values = production_env()
        values.pop("BODY_SIZE_LIMIT")
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(
            check for check in checks if check.name == "runtime settings"
        )
        self.assertEqual(runtime_check.status, "FAIL")
        self.assertIn("BODY_SIZE_LIMIT must be 10M in production", runtime_check.detail)

    def test_image_input_rejects_an_undersized_frontend_body_limit(self):
        values = production_env()
        values.update({
            "BODY_SIZE_LIMIT": "512K",
            "ROCKY_ENABLE_IMAGE_INPUT": "true",
            "ROCKY_MAX_REQUEST_BYTES": str(9 * 1024 * 1024),
            "ROCKY_GRANITE_MAX_REQUEST_BYTES": str(10 * 1024 * 1024),
        })
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(
            check for check in checks if check.name == "runtime settings"
        )
        self.assertEqual(runtime_check.status, "FAIL")
        self.assertIn(
            "BODY_SIZE_LIMIT is too small for the configured image-input budget",
            runtime_check.detail,
        )

    def test_image_input_budgets_must_fit_the_deployed_ingress_and_chat_proxy(self):
        values = production_env()
        values.update({
            "ROCKY_ENABLE_IMAGE_INPUT": "true",
            "ROCKY_MAX_IMAGE_BYTES": str(8 * 1024 * 1024),
            "ROCKY_MAX_IMAGE_TOTAL_BYTES": str(8 * 1024 * 1024),
            "ROCKY_MAX_REQUEST_BYTES": str(12 * 1024 * 1024),
            "ROCKY_GRANITE_MAX_REQUEST_BYTES": str(12 * 1024 * 1024),
        })
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(
            check for check in checks if check.name == "runtime settings"
        )
        self.assertEqual(runtime_check.status, "FAIL")
        self.assertIn("built-in chat proxy's 10 MiB", runtime_check.detail)
        self.assertIn("deployed Nginx 10 MiB", runtime_check.detail)

    def test_healthy_production_configuration_and_services_pass(self):
        pinged = []

        def ping(uri, database_name):
            pinged.append((uri, database_name))

        session = FakeSession(healthy_routes())
        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(session=session, mongo_pinger=ping).run()

        self.assertFalse(any(check.failed for check in checks))
        self.assertEqual(
            pinged,
            [("mongodb://database.example/rocky_db", "rocky_db")],
        )
        granite_call = next(
            call for call in session.calls if call[0] == "http://granite.example:5002/ready"
        )
        self.assertEqual(
            granite_call[1]["headers"],
            {"X-Rocky-Granite-Token": "g" * 40},
        )
        rendered = " ".join(check.detail for check in checks)
        self.assertNotIn("mongodb://database.example", rendered)
        self.assertNotIn("g" * 40, rendered)

    def test_timeout_ladder_must_cover_queue_wait_and_model_generation(self):
        values = production_env()
        values["ROCKY_GRANITE_TIMEOUT_SECONDS"] = "280"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(
            check for check in checks if check.name == "runtime settings"
        )
        self.assertEqual(runtime_check.status, "FAIL")
        self.assertIn(
            "must cover the queue wait plus Ollama timeout",
            runtime_check.detail,
        )

    def test_readiness_rejects_timeout_configuration_drift(self):
        routes = healthy_routes()
        routes["http://127.0.0.1:5003/ready"]._payload["timeouts"][
            "configuration_matches"
        ] = False
        routes["http://granite.example:5002/ready"]._payload["timeouts"][
            "queue_wait_seconds"
        ] = 1

        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(
                session=FakeSession(routes),
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name: check.detail for check in checks if check.failed}
        self.assertIn("chat API readiness", failures)
        self.assertIn("Granite readiness", failures)
        self.assertIn("timeout", failures["chat API readiness"])
        self.assertIn("timeout", failures["Granite readiness"])

    def test_readiness_rejects_queue_configuration_drift(self):
        routes = healthy_routes()
        routes["http://127.0.0.1:5003/ready"]._payload["queue"][
            "max_active_requests"
        ] = 8
        routes["http://127.0.0.1:5003/ready"]._payload[
            "queue_configuration_matches"
        ] = False
        routes["http://granite.example:5002/ready"]._payload["queue"][
            "max_active_requests"
        ] = 8

        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(
                session=FakeSession(routes),
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name: check.detail for check in checks if check.failed}
        self.assertIn("chat API readiness", failures)
        self.assertIn("Granite readiness", failures)
        self.assertIn("queue", failures["chat API readiness"])
        self.assertIn("queue", failures["Granite readiness"])

    def test_readiness_rejects_a_frontend_and_service_streaming_mismatch(self):
        values = production_env()
        values["ROCKY_ENABLE_STREAMING"] = "true"

        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                session=FakeSession(healthy_routes()),
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        readiness = next(check for check in checks if check.name == "chat API readiness")
        self.assertEqual(readiness.status, "FAIL")
        self.assertIn("supports_streaming", readiness.detail)
        self.assertIn("streaming.rocky_enabled", readiness.detail)

    def test_fully_enabled_streaming_and_image_readiness_passes(self):
        values = production_env()
        values.update(
            {
                "ROCKY_ENABLE_STREAMING": "true",
                "ROCKY_ENABLE_IMAGE_INPUT": "true",
                "ROCKY_MAX_REQUEST_BYTES": str(9 * 1024 * 1024),
                "ROCKY_GRANITE_MAX_REQUEST_BYTES": str(10 * 1024 * 1024),
            }
        )
        routes = healthy_routes()
        ready_payload = routes["http://127.0.0.1:5003/ready"]._payload
        ready_payload["capabilities"]["supports_streaming"] = True
        ready_payload["capabilities"]["supports_image_input"] = True
        ready_payload["streaming"] = {
            "rocky_enabled": True,
            "granite_enabled": True,
        }
        ready_payload["image_input"] = {
            "rocky_enabled": True,
            "granite_enabled": True,
            "limits_match": True,
        }

        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                session=FakeSession(routes),
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        self.assertFalse(any(check.failed for check in checks))
        readiness = next(check for check in checks if check.name == "chat API readiness")
        self.assertIn("capabilities match configuration", readiness.detail)

    def test_readiness_rejects_image_limits_that_do_not_match_configuration(self):
        values = production_env()
        values["ROCKY_MAX_IMAGES_PER_REQUEST"] = "3"

        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                session=FakeSession(healthy_routes()),
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        readiness = next(check for check in checks if check.name == "chat API readiness")
        self.assertEqual(readiness.status, "FAIL")
        self.assertIn("max_images_per_request", readiness.detail)

    def test_production_rejects_mongita_placeholders_and_missing_oauth(self):
        values = production_env()
        values.update(
            {
                "ROCKY_DB_BACKEND": "mongita",
                "ROCKY_HIDDEN_API_KEY_SECRET": "replace-with-secret",
                "PUBLIC_ENABLE_MICROSOFT_OAUTH": "false",
                "PUBLIC_MICROSOFT_CLIENT_ID": "",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(include_network=False).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("database backend", failures)
        self.assertIn("ROCKY_HIDDEN_API_KEY_SECRET", failures)
        self.assertIn("PUBLIC_MICROSOFT_CLIENT_ID", failures)
        self.assertNotIn("Microsoft OAuth mode", failures)

    def test_production_requires_matching_web_environment_and_specific_tenant(self):
        values = production_env()
        values.update(
            {
                "PUBLIC_APP_ENV": "development",
                "PUBLIC_MICROSOFT_TENANT_ID": "common",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("web application environment", failures)

        values["PUBLIC_APP_ENV"] = "production"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()
        failures = {check.name for check in checks if check.failed}
        self.assertIn("PUBLIC_MICROSOFT_TENANT_ID", failures)

    def test_development_oauth_requires_client_and_specific_tenant(self):
        values = production_env()
        values.update(
            {
                "ROCKY_APP_ENV": "development",
                "PUBLIC_APP_ENV": "development",
                "ROCKY_DB_BACKEND": "mongita",
                "ROCKY_MONGODB_URI": "",
                "PUBLIC_ENABLE_MICROSOFT_OAUTH": "true",
                "PUBLIC_MICROSOFT_CLIENT_ID": "",
                "PUBLIC_MICROSOFT_TENANT_ID": "common",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(include_network=False).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("PUBLIC_MICROSOFT_CLIENT_ID", failures)
        self.assertIn("PUBLIC_MICROSOFT_TENANT_ID", failures)

    def test_testing_mode_ignores_the_development_oauth_override(self):
        values = production_env()
        values.update(
            {
                "ROCKY_APP_ENV": "testing",
                "PUBLIC_APP_ENV": "testing",
                "ROCKY_DB_BACKEND": "mongita",
                "ROCKY_MONGODB_URI": "",
                "PUBLIC_ENABLE_MICROSOFT_OAUTH": "true",
                "PUBLIC_MICROSOFT_CLIENT_ID": "",
                "PUBLIC_MICROSOFT_TENANT_ID": "",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(include_network=False).run()

        failures = {check.name for check in checks if check.failed}
        self.assertNotIn("PUBLIC_MICROSOFT_CLIENT_ID", failures)
        self.assertNotIn("PUBLIC_MICROSOFT_TENANT_ID", failures)

    def test_production_rejects_invalid_frontend_boolean_flags(self):
        values = production_env()
        values["PUBLIC_ENABLE_MICROSOFT_OAUTH"] = "yes"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("PUBLIC_ENABLE_MICROSOFT_OAUTH", failures)

    def test_production_requires_request_logging(self):
        values = production_env()
        values["ROCKY_REQUIRE_REQUEST_LOGGING"] = "false"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("ROCKY_REQUIRE_REQUEST_LOGGING", failures)

        values["ROCKY_REQUIRE_REQUEST_LOGGING"] = "sometimes"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()
        failures = {check.name for check in checks if check.failed}
        self.assertIn("ROCKY_REQUIRE_REQUEST_LOGGING", failures)

    def test_development_allows_local_database_and_skips_network(self):
        values = production_env()
        values.update(
            {
                "ROCKY_APP_ENV": "development",
                "PUBLIC_APP_ENV": "development",
                "ROCKY_DB_BACKEND": "mongita",
                "ROCKY_MONGODB_URI": "",
                "ROCKY_HIDDEN_API_KEY_SECRET": "",
                "ROCKY_SESSION_SECRET": "",
                "ROCKY_INTERNAL_PROXY_SECRET": "",
                "ROCKY_GRANITE_TOKEN": "",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(include_network=False).run()

        self.assertFalse(any(check.failed for check in checks))
        self.assertTrue(any(check.name == "MongoDB connection" for check in checks))
        self.assertTrue(any(check.name == "network checks" for check in checks))

    def test_development_uses_the_same_defaults_as_runtime_services(self):
        values = {
            "ROCKY_APP_ENV": "development",
            "ROCKY_DB_BACKEND": "mongita",
            "PUBLIC_ENABLE_MICROSOFT_OAUTH": "false",
        }
        with patch.dict("os.environ", values, clear=True):
            doctor = RockyDoctor(include_network=False)
            checks = doctor.run()

        self.assertFalse(any(check.failed for check in checks))
        self.assertEqual(doctor.public_app_env, "development")
        self.assertEqual(doctor.inference_model, "gemma4:latest")
        self.assertEqual(doctor.public_model, "gemma4:latest")
        passed = {check.name for check in checks if check.status == "PASS"}
        self.assertIn("frontend API URL", passed)
        self.assertIn("Granite generation URL", passed)
        self.assertIn("Granite readiness URL", passed)

    def test_blank_runtime_fallbacks_match_service_defaults(self):
        values = {
            "ROCKY_APP_ENV": "",
            "ROCKY_DB_BACKEND": "",
            "ROCKY_DB_NAME": "",
            "OLLAMA_MODEL": "",
            "ROCKY_PUBLIC_MODEL": "",
        }
        with patch.dict("os.environ", values, clear=True):
            doctor = RockyDoctor(include_network=False)
            checks = doctor.run()

        self.assertFalse(any(check.failed for check in checks))
        self.assertEqual(doctor.app_env, "development")
        self.assertEqual(doctor.db_backend, "mongita")
        self.assertEqual(doctor.db_name, "rocky_db")
        self.assertEqual(doctor.public_model, "gemma4:latest")

    def test_runtime_setting_errors_are_actionable(self):
        values = production_env()
        values.update(
            {
                "ROCKY_DEBUG": "true",
                "ROCKY_ENABLE_DB_INSPECTOR": "sometimes",
                "ROCKY_ENABLE_STREAMING": "sometimes",
                "ROCKY_ENABLE_IMAGE_INPUT": "true",
                "ROCKY_CHAT_API_PORT": "not-a-port",
                "ROCKY_GRANITE_TIMEOUT_SECONDS": "nan",
                "ROCKY_GRANITE_MAX_CONCURRENT": "0",
                "ROCKY_GRANITE_QUEUE_CAPACITY": "-1",
                "ROCKY_GRANITE_QUEUE_MAX_BYTES": "unbounded",
                "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS": "0.09",
                "BODY_SIZE_LIMIT": "unbounded",
                "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE": "0",
                "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE": "not-an-integer",
                "ROCKY_MAX_IMAGES_PER_REQUEST": "17",
                "ROCKY_MAX_IMAGE_BYTES": "200",
                "ROCKY_MAX_IMAGE_TOTAL_BYTES": "100",
                "ROCKY_MAX_IMAGE_PIXELS": "200",
                "ROCKY_MAX_IMAGE_TOTAL_PIXELS": "100",
                "ROCKY_MAX_REQUEST_BYTES": "1000",
                "ROCKY_GRANITE_MAX_REQUEST_BYTES": "1000",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(check for check in checks if check.name == "runtime settings")
        self.assertEqual(runtime_check.status, "FAIL")
        self.assertIn("ROCKY_DEBUG must be false in production", runtime_check.detail)
        self.assertIn("ROCKY_ENABLE_DB_INSPECTOR must be exactly true or false", runtime_check.detail)
        self.assertIn("ROCKY_ENABLE_STREAMING must be exactly true or false", runtime_check.detail)
        self.assertIn("ROCKY_CHAT_API_PORT must be an integer", runtime_check.detail)
        self.assertIn("ROCKY_GRANITE_TIMEOUT_SECONDS must be a finite number", runtime_check.detail)
        self.assertIn("ROCKY_GRANITE_MAX_CONCURRENT must be at least 1", runtime_check.detail)
        self.assertIn("ROCKY_GRANITE_QUEUE_CAPACITY must be at least 0", runtime_check.detail)
        self.assertIn("ROCKY_GRANITE_QUEUE_MAX_BYTES must be an integer", runtime_check.detail)
        self.assertIn(
            "BODY_SIZE_LIMIT must be a positive byte size such as 10M",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_GRANITE_QUEUE_HEARTBEAT_SECONDS must be at least 0.1",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE must be at least 1",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE must be an integer",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_MAX_IMAGES_PER_REQUEST must be between 1 and 16",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_MAX_IMAGE_TOTAL_BYTES must be at least ROCKY_MAX_IMAGE_BYTES",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_MAX_IMAGE_TOTAL_PIXELS must be at least ROCKY_MAX_IMAGE_PIXELS",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_MAX_REQUEST_BYTES is too small for the configured image-input budget",
            runtime_check.detail,
        )
        self.assertIn(
            "ROCKY_GRANITE_MAX_REQUEST_BYTES is too small for the configured "
            "image-input budget",
            runtime_check.detail,
        )

    def test_service_urls_reject_credentials_and_invalid_ports(self):
        values = production_env()
        values.update(
            {
                "PUBLIC_API_BASE_URL": "http://user:password@127.0.0.1:5001",
                "ROCKY_GRANITE_URL": "http://granite.example:99999/generate",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("frontend API URL", failures)
        self.assertIn("Granite generation URL", failures)

    def test_composable_service_urls_reject_queries_and_fragments(self):
        values = production_env()
        values.update(
            {
                "PUBLIC_API_BASE_URL": "http://127.0.0.1:5001?tenant=one",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434#internal",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        failures = {check.name for check in checks if check.failed}
        self.assertIn("frontend API URL", failures)
        self.assertIn("Ollama base URL", failures)

    def test_chat_url_rejects_queries_and_fragments(self):
        for value in (
            "http://127.0.0.1:5003/v1/responses?tenant=one",
            "http://127.0.0.1:5003/v1/responses#internal",
        ):
            with self.subTest(value=value):
                values = production_env()
                values["ROCKY_CHAT_API_URL"] = value
                with patch.dict("os.environ", values, clear=True):
                    checks = RockyDoctor(include_network=False).run()

                check = next(check for check in checks if check.name == "chat API URL")
                self.assertEqual(check.status, "FAIL")

    def test_chat_url_accepts_a_service_base(self):
        values = production_env()
        values["ROCKY_CHAT_API_URL"] = "http://127.0.0.1:5003"
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(include_network=False).run()

        check = next(check for check in checks if check.name == "chat API URL")
        self.assertEqual(check.status, "PASS")

    def test_production_validates_required_telemetry_settings(self):
        values = production_env()
        values.update(
            {
                "ROCKY_TELEMETRY_ENABLED": "false",
                "ROCKY_HARDWARE_TELEMETRY_ENABLED": "true",
                "ROCKY_HARDWARE_METRICS_URL": "not-a-url",
                "ROCKY_HARDWARE_METRICS_TOKEN": "replace-with-a-token",
            }
        )
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        runtime_check = next(check for check in checks if check.name == "runtime settings")
        self.assertIn("ROCKY_TELEMETRY_ENABLED must be true", runtime_check.detail)
        self.assertIn("ROCKY_HARDWARE_METRICS_TOKEN", runtime_check.detail)
        failures = {check.name for check in checks if check.failed}
        self.assertIn("hardware metrics URL", failures)

    def test_rocky_host_does_not_require_a_local_ollama_url(self):
        values = production_env()
        values.pop("OLLAMA_BASE_URL")
        with patch.dict("os.environ", values, clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda _uri, _database: None,
            ).run()

        ollama_check = next(check for check in checks if check.name == "Ollama base URL")
        self.assertEqual(ollama_check.status, "INFO")
        self.assertFalse(any(check.failed for check in checks))

    def test_skip_network_validates_mongodb_configuration_without_connecting(self):
        pinged = []
        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(
                include_network=False,
                mongo_pinger=lambda uri, database: pinged.append((uri, database)),
            ).run()

        self.assertEqual(pinged, [])
        mongodb_check = next(
            check for check in checks if check.name == "MongoDB connection"
        )
        self.assertEqual(mongodb_check.status, "INFO")
        self.assertIn("--skip-network", mongodb_check.detail)
        self.assertFalse(any(check.failed for check in checks))

    def test_database_and_model_service_failures_are_specific_and_secret_safe(self):
        routes = healthy_routes()
        routes["http://127.0.0.1:5003/ready"] = FakeResponse(
            503,
            {
                "ok": False,
                "dependencies": {"database": True, "granite": False},
                "models": {
                    "public": "course-model",
                    "inference": "course-model",
                    "granite": "other-model",
                },
            },
        )
        routes["http://granite.example:5002/ready"] = FakeResponse(
            503,
            {
                "ok": False,
                "model": "other-model",
                "dependencies": {"ollama": True, "model_available": False},
            },
        )

        def failed_ping(_uri, _database_name):
            raise RuntimeError("database secret must not be rendered")

        with patch.dict("os.environ", production_env(), clear=True):
            checks = RockyDoctor(
                session=FakeSession(routes),
                mongo_pinger=failed_ping,
            ).run()

        failures = {check.name: check.detail for check in checks if check.failed}
        self.assertIn("MongoDB connection", failures)
        self.assertIn("chat API readiness", failures)
        self.assertIn("Granite readiness", failures)
        self.assertNotIn("database secret", " ".join(failures.values()))


if __name__ == "__main__":
    unittest.main()
