from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import requests
from pymongo import MongoClient
from run_env import normalize_chat_api_urls


VALID_APP_ENVS = {"development", "testing", "production"}
VALID_DB_BACKENDS = {"mongita", "mongodb"}
DEFAULT_MODEL = "gemma4:latest"
PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme")
DEPLOYED_INGRESS_MAX_REQUEST_BYTES = 10 * 1024 * 1024
BUILT_IN_CHAT_MAX_IMAGE_CHARACTERS = 10 * 1024 * 1024
MAX_IMAGE_DATA_URL_PREFIX_CHARACTERS = len("data:image/jpeg;base64,")
PRODUCTION_SECRETS = (
    "ROCKY_HIDDEN_API_KEY_SECRET",
    "ROCKY_SESSION_SECRET",
    "ROCKY_INTERNAL_PROXY_SECRET",
    "ROCKY_GRANITE_TOKEN",
)
IMAGE_LIMIT_SETTINGS = {
    "max_images_per_request": ("ROCKY_MAX_IMAGES_PER_REQUEST", 4),
    "max_image_bytes": ("ROCKY_MAX_IMAGE_BYTES", 4 * 1024 * 1024),
    "max_image_total_bytes": ("ROCKY_MAX_IMAGE_TOTAL_BYTES", 6 * 1024 * 1024),
    "max_image_pixels": ("ROCKY_MAX_IMAGE_PIXELS", 20_000_000),
    "max_image_total_pixels": ("ROCKY_MAX_IMAGE_TOTAL_PIXELS", 40_000_000),
}


@dataclass(frozen=True)
class DoctorCheck:
    status: str
    name: str
    detail: str

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def connectable_host(value: str) -> str:
    return "127.0.0.1" if value in {"0.0.0.0", "::"} else value


def valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.query or parsed.fragment:
        return False
    return True


def configured_boolean(name: str) -> bool | None:
    value = env(name, "false").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def configured_image_limits() -> dict[str, int] | None:
    limits: dict[str, int] = {}
    try:
        for public_name, (environment_name, default) in IMAGE_LIMIT_SETTINGS.items():
            limits[public_name] = int(env(environment_name, str(default)))
    except ValueError:
        return None
    return limits


def derive_frontend_api_url() -> str:
    return env("PUBLIC_API_BASE_URL", "http://localhost:5001").rstrip("/")


def derive_granite_generation_url() -> str:
    return env("ROCKY_GRANITE_URL", "http://127.0.0.1:5002/generate")


def derive_granite_readiness_url() -> str:
    configured = env("ROCKY_GRANITE_READY_URL")
    if configured:
        return configured
    generation_url = derive_granite_generation_url().rstrip("/")
    return generation_url.rsplit("/", 1)[0] + "/ready"


def derive_chat_base_url() -> str:
    configured = env("ROCKY_CHAT_API_URL")
    if not configured:
        host = connectable_host(env("ROCKY_CHAT_API_HOST", "127.0.0.1"))
        port = env("ROCKY_CHAT_API_PORT", "5003")
        configured = f"http://{host}:{port}"
    try:
        return normalize_chat_api_urls(configured)[1]
    except RuntimeError:
        return ""


def derive_backend_health_url() -> str:
    configured = env("ROCKY_BACKEND_HEALTH_URL")
    if configured:
        return configured
    host = connectable_host(env("ROCKY_API_HOST", "127.0.0.1"))
    port = env("ROCKY_API_PORT", "5001")
    return f"http://{host}:{port}/health"


def ping_mongodb(uri: str, _database_name: str) -> None:
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    finally:
        client.close()


class RockyDoctor:
    def __init__(
        self,
        *,
        timeout_seconds: float = 3,
        include_network: bool = True,
        session: requests.Session | None = None,
        mongo_pinger: Callable[[str, str], None] = ping_mongodb,
    ):
        self.timeout_seconds = timeout_seconds
        self.include_network = include_network
        self.session = session or requests.Session()
        self.mongo_pinger = mongo_pinger
        self.app_env = env("ROCKY_APP_ENV", "development").lower() or "development"
        self.public_app_env = env("PUBLIC_APP_ENV", self.app_env).lower()
        default_db_backend = "mongodb" if self.app_env == "production" else "mongita"
        self.db_backend = env("ROCKY_DB_BACKEND", default_db_backend).lower() or default_db_backend
        self.db_name = env("ROCKY_DB_NAME", "rocky_db") or "rocky_db"
        self.mongodb_uri = env("ROCKY_MONGODB_URI")
        self.inference_model = env("OLLAMA_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
        self.public_model = env("ROCKY_PUBLIC_MODEL", self.inference_model) or self.inference_model

    def run(self) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        checks.extend(self.configuration_checks())
        checks.extend(self.database_checks())
        if self.include_network:
            checks.extend(self.network_checks())
        else:
            checks.append(DoctorCheck("INFO", "network checks", "Skipped by --skip-network."))
        return checks

    def configuration_checks(self) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        if self.app_env in VALID_APP_ENVS:
            checks.append(DoctorCheck("PASS", "application environment", self.app_env))
        else:
            checks.append(
                DoctorCheck(
                    "FAIL",
                    "application environment",
                    "ROCKY_APP_ENV must be development, testing, or production.",
                )
            )

        if self.public_app_env not in VALID_APP_ENVS:
            checks.append(
                DoctorCheck(
                    "FAIL",
                    "web application environment",
                    "PUBLIC_APP_ENV must be development, testing, or production.",
                )
            )
        elif self.public_app_env != self.app_env:
            checks.append(
                DoctorCheck(
                    "FAIL",
                    "web application environment",
                    "PUBLIC_APP_ENV and ROCKY_APP_ENV must match.",
                )
            )
        else:
            checks.append(
                DoctorCheck("PASS", "web application environment", self.public_app_env)
            )

        if self.db_backend not in VALID_DB_BACKENDS:
            checks.append(
                DoctorCheck(
                    "FAIL",
                    "database backend",
                    "ROCKY_DB_BACKEND must be mongodb or mongita.",
                )
            )
        elif self.app_env == "production" and self.db_backend != "mongodb":
            checks.append(
                DoctorCheck(
                    "FAIL",
                    "database backend",
                    "Production must use mongodb; Mongita is for local development only.",
                )
            )
        else:
            checks.append(DoctorCheck("PASS", "database backend", self.db_backend))

        if self.db_name:
            checks.append(DoctorCheck("PASS", "database name", self.db_name))
        else:
            checks.append(DoctorCheck("FAIL", "database name", "ROCKY_DB_NAME is empty."))

        checks.extend(self.secret_checks())
        checks.extend(self.frontend_flag_checks())
        checks.extend(self.runtime_setting_checks())
        checks.extend(self.request_logging_checks())
        checks.extend(self.authentication_checks())
        checks.extend(self.model_checks())
        checks.extend(self.url_checks())
        return checks

    def runtime_setting_checks(self) -> list[DoctorCheck]:
        boolean_settings = {
            "ROCKY_DEBUG": "false" if self.app_env == "production" else "true",
            "ROCKY_ENABLE_DB_INSPECTOR": (
                "false" if self.app_env == "production" else "true"
            ),
            "ROCKY_ENABLE_MICROSOFT_OAUTH": "false",
            "ROCKY_ENABLE_STREAMING": "false",
            "ROCKY_ENABLE_IMAGE_INPUT": "false",
            "ROCKY_HARDWARE_TELEMETRY_ENABLED": "false",
            "ROCKY_TELEMETRY_ENABLED": "true",
        }
        errors: list[str] = []
        for name, default in boolean_settings.items():
            value = env(name, default).lower()
            if value not in {"true", "false"}:
                errors.append(f"{name} must be exactly true or false")

        if self.app_env == "production":
            if env("ROCKY_DEBUG", "false").lower() != "false":
                errors.append("ROCKY_DEBUG must be false in production")
            if env("ROCKY_ENABLE_DB_INSPECTOR", "false").lower() != "false":
                errors.append("ROCKY_ENABLE_DB_INSPECTOR must be false in production")
            if env("ROCKY_TELEMETRY_ENABLED", "true").lower() != "true":
                errors.append("ROCKY_TELEMETRY_ENABLED must be true in production")

        if env("ROCKY_HARDWARE_TELEMETRY_ENABLED", "false").lower() == "true":
            metrics_token = env("ROCKY_HARDWARE_METRICS_TOKEN")
            if self.app_env == "production" and (
                len(metrics_token) < 32
                or metrics_token.lower().startswith(PLACEHOLDER_PREFIXES)
            ):
                errors.append(
                    "ROCKY_HARDWARE_METRICS_TOKEN must be a non-placeholder value "
                    "of at least 32 characters in production"
                )

        integer_settings = {
            "ROCKY_API_PORT": (5001, 1, 65535),
            "ROCKY_WEB_PORT": (5000, 1, 65535),
            "ROCKY_CHAT_API_PORT": (5003, 1, 65535),
            "ROCKY_GRANITE_PORT": (5002, 1, 65535),
            "ROCKY_HARDWARE_PORT": (5010, 1, 65535),
            "ROCKY_MAX_REQUEST_BYTES": (256 * 1024, 1, None),
            "ROCKY_MAX_OUTPUT_TOKENS": (2048, 1, None),
            "ROCKY_MAX_CONTEXT_CHARS": (60000, 1, None),
            "ROCKY_MAX_IMAGES_PER_REQUEST": (4, 1, 16),
            "ROCKY_MAX_IMAGE_BYTES": (4 * 1024 * 1024, 1, None),
            "ROCKY_MAX_IMAGE_TOTAL_BYTES": (6 * 1024 * 1024, 1, None),
            "ROCKY_MAX_IMAGE_PIXELS": (20_000_000, 1, None),
            "ROCKY_MAX_IMAGE_TOTAL_PIXELS": (40_000_000, 1, None),
            "ROCKY_RESPONSES_RATE_LIMIT_PER_MINUTE": (10, 1, None),
            "ROCKY_MODELS_RATE_LIMIT_PER_MINUTE": (120, 1, None),
            "ROCKY_GRANITE_MAX_CONCURRENT": (1, 1, None),
            "ROCKY_GRANITE_MAX_REQUEST_BYTES": (10 * 1024 * 1024, 1, None),
            "ROCKY_MONGODB_CONNECT_ATTEMPTS": (10, 1, None),
            "ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS": (30, 10, None),
            "ROCKY_HARDWARE_METRICS_TIMEOUT_SECONDS": (5, 1, None),
            "ROCKY_HARDWARE_RETENTION_DAYS": (90, 1, None),
        }
        for name, (default, minimum, maximum) in integer_settings.items():
            raw_value = env(name, str(default))
            try:
                value = int(raw_value)
            except ValueError:
                errors.append(f"{name} must be an integer")
                continue
            if value < minimum or (maximum is not None and value > maximum):
                range_text = (
                    f"between {minimum} and {maximum}"
                    if maximum is not None
                    else f"at least {minimum}"
                )
                errors.append(f"{name} must be {range_text}")

        try:
            max_image_bytes = int(env("ROCKY_MAX_IMAGE_BYTES", str(4 * 1024 * 1024)))
            max_image_total_bytes = int(
                env("ROCKY_MAX_IMAGE_TOTAL_BYTES", str(6 * 1024 * 1024))
            )
            max_image_pixels = int(env("ROCKY_MAX_IMAGE_PIXELS", "20000000"))
            max_image_total_pixels = int(
                env("ROCKY_MAX_IMAGE_TOTAL_PIXELS", "40000000")
            )
        except ValueError:
            pass
        else:
            if max_image_total_bytes < max_image_bytes:
                errors.append(
                    "ROCKY_MAX_IMAGE_TOTAL_BYTES must be at least "
                    "ROCKY_MAX_IMAGE_BYTES"
                )
            if max_image_total_pixels < max_image_pixels:
                errors.append(
                    "ROCKY_MAX_IMAGE_TOTAL_PIXELS must be at least "
                    "ROCKY_MAX_IMAGE_PIXELS"
                )
            if env("ROCKY_ENABLE_IMAGE_INPUT", "false").lower() == "true":
                try:
                    max_images_per_request = int(
                        env("ROCKY_MAX_IMAGES_PER_REQUEST", "4")
                    )
                    max_request_bytes = int(
                        env("ROCKY_MAX_REQUEST_BYTES", str(256 * 1024))
                    )
                    max_context_chars = int(
                        env("ROCKY_MAX_CONTEXT_CHARS", "60000")
                    )
                    granite_max_request_bytes = int(env(
                        "ROCKY_GRANITE_MAX_REQUEST_BYTES",
                        str(10 * 1024 * 1024),
                    ))
                except ValueError:
                    pass
                else:
                    maximum_encoded_image_characters = (
                        4 * ((max_image_total_bytes + 2) // 3)
                        + max_images_per_request * MAX_IMAGE_DATA_URL_PREFIX_CHARACTERS
                    )
                    if maximum_encoded_image_characters > BUILT_IN_CHAT_MAX_IMAGE_CHARACTERS:
                        errors.append(
                            "ROCKY_MAX_IMAGE_TOTAL_BYTES exceeds the built-in chat proxy's "
                            "10 MiB encoded-image ceiling"
                        )
                    minimum_public_bytes = (
                        4 * ((max_image_total_bytes + 2) // 3)
                        + max_context_chars
                        + 16 * 1024
                    )
                    if max_request_bytes < minimum_public_bytes:
                        errors.append(
                            "ROCKY_MAX_REQUEST_BYTES is too small for the "
                            "configured image-input budget"
                        )
                    if max_request_bytes > DEPLOYED_INGRESS_MAX_REQUEST_BYTES:
                        errors.append(
                            "ROCKY_MAX_REQUEST_BYTES exceeds the deployed Nginx 10 MiB "
                            "request ceiling"
                        )
                    minimum_granite_bytes = (
                        4 * ((max_image_total_bytes + 2) // 3)
                        + 128 * 1024
                    )
                    if granite_max_request_bytes < minimum_granite_bytes:
                        errors.append(
                            "ROCKY_GRANITE_MAX_REQUEST_BYTES is too small for "
                            "the configured image-input budget"
                        )

        float_settings = {
            "ROCKY_GRANITE_TIMEOUT_SECONDS": (170.0, 0.0, False),
            "ROCKY_READINESS_TIMEOUT_SECONDS": (3.0, 0.0, False),
            "ROCKY_OLLAMA_TIMEOUT_SECONDS": (150.0, 0.0, False),
            "ROCKY_OLLAMA_READY_TIMEOUT_SECONDS": (2.0, 0.0, False),
            "ROCKY_GRANITE_QUEUE_WAIT_SECONDS": (1.0, 0.0, True),
            "ROCKY_MONGODB_RETRY_SECONDS": (2.0, 0.0, True),
            "ROCKY_HARDWARE_COMMAND_TIMEOUT_SECONDS": (3.0, 0.0, False),
        }
        for name, (default, minimum, allow_minimum) in float_settings.items():
            raw_value = env(name, str(default))
            try:
                value = float(raw_value)
            except ValueError:
                errors.append(f"{name} must be a number")
                continue
            if not math.isfinite(value):
                errors.append(f"{name} must be a finite number")
            elif value < minimum or (value == minimum and not allow_minimum):
                comparison = "at least" if allow_minimum else "greater than"
                errors.append(f"{name} must be {comparison} {minimum:g}")

        return [
            DoctorCheck(
                "FAIL" if errors else "PASS",
                "runtime settings",
                "; ".join(errors) if errors else "Ports, timeouts, limits, and flags are valid.",
            )
        ]

    def request_logging_checks(self) -> list[DoctorCheck]:
        default_value = "true" if self.app_env == "production" else "false"
        value = env("ROCKY_REQUIRE_REQUEST_LOGGING", default_value).lower()
        if value not in {"true", "false"}:
            return [
                DoctorCheck(
                    "FAIL",
                    "ROCKY_REQUIRE_REQUEST_LOGGING",
                    "Must be exactly true or false.",
                )
            ]
        if self.app_env == "production" and value != "true":
            return [
                DoctorCheck(
                    "FAIL",
                    "ROCKY_REQUIRE_REQUEST_LOGGING",
                    "Must be true in production so inference fails closed when audit logging is unavailable.",
                )
            ]
        return [DoctorCheck("PASS", "ROCKY_REQUIRE_REQUEST_LOGGING", value)]

    def frontend_flag_checks(self) -> list[DoctorCheck]:
        name = "PUBLIC_ENABLE_MICROSOFT_OAUTH"
        value = env(name, "false").lower()
        if value not in {"true", "false"}:
            return [DoctorCheck("FAIL", name, "Must be exactly true or false.")]
        return [DoctorCheck("PASS", name, value)]

    def secret_checks(self) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        for name in PRODUCTION_SECRETS:
            value = env(name)
            placeholder = value.lower().startswith(PLACEHOLDER_PREFIXES)
            if self.app_env == "production":
                valid = len(value) >= 32 and not placeholder
                checks.append(
                    DoctorCheck(
                        "PASS" if valid else "FAIL",
                        name,
                        "Configured." if valid else "Must be a non-placeholder value of at least 32 characters.",
                    )
                )
            elif not value or placeholder:
                checks.append(
                    DoctorCheck(
                        "INFO",
                        name,
                        "Not production-ready; acceptable for local development.",
                    )
                )
            else:
                checks.append(DoctorCheck("PASS", name, "Configured."))
        return checks

    def authentication_checks(self) -> list[DoctorCheck]:
        microsoft_override = env("PUBLIC_ENABLE_MICROSOFT_OAUTH", "false").lower()
        microsoft_active = self.public_app_env == "production" or (
            self.public_app_env == "development" and microsoft_override == "true"
        )
        if not microsoft_active:
            return [
                DoctorCheck(
                    "INFO",
                    "Microsoft authentication",
                    "Not active in the configured authentication mode.",
                )
            ]

        tenant_id = env("PUBLIC_MICROSOFT_TENANT_ID")
        values = {
            "PUBLIC_MICROSOFT_CLIENT_ID": env("PUBLIC_MICROSOFT_CLIENT_ID"),
            "PUBLIC_MICROSOFT_TENANT_ID": tenant_id,
        }
        checks = [
            DoctorCheck(
                (
                    "PASS"
                    if value
                    and not (
                        name == "PUBLIC_MICROSOFT_TENANT_ID"
                        and value.lower() in {"common", "organizations", "consumers"}
                    )
                    else "FAIL"
                ),
                name,
                (
                    "Configured."
                    if value
                    and not (
                        name == "PUBLIC_MICROSOFT_TENANT_ID"
                        and value.lower() in {"common", "organizations", "consumers"}
                    )
                    else "Required whenever Microsoft OAuth is active; the tenant must "
                    "be a specific Kent tenant ID."
                ),
            )
            for name, value in values.items()
        ]
        checks.append(
            DoctorCheck(
                "PASS",
                "Microsoft OAuth mode",
                (
                    "Enabled by PUBLIC_APP_ENV=production."
                    if self.public_app_env == "production"
                    else "Enabled by PUBLIC_ENABLE_MICROSOFT_OAUTH=true."
                ),
            )
        )
        return checks

    def model_checks(self) -> list[DoctorCheck]:
        return [
            DoctorCheck(
                "PASS",
                "model mapping",
                f"Public '{self.public_model}' maps to inference '{self.inference_model}'.",
            )
        ]

    def url_checks(self) -> list[DoctorCheck]:
        urls = {
            "frontend API URL": derive_frontend_api_url(),
            "backend health URL": derive_backend_health_url(),
            "Granite generation URL": derive_granite_generation_url(),
            "Granite readiness URL": derive_granite_readiness_url(),
        }
        if env("ROCKY_HARDWARE_TELEMETRY_ENABLED", "false").lower() == "true":
            urls["hardware metrics URL"] = env("ROCKY_HARDWARE_METRICS_URL")
        checks: list[DoctorCheck] = []
        for name, value in urls.items():
            valid = valid_http_url(value)
            checks.append(
                DoctorCheck(
                    "PASS" if valid else "FAIL",
                    name,
                    "Valid URL." if valid else "Missing or not an absolute http(s) URL.",
                )
            )

        chat_base_url = derive_chat_base_url()
        checks.append(
            DoctorCheck(
                "PASS" if chat_base_url else "FAIL",
                "chat API URL",
                (
                    "Valid service base and generation endpoint."
                    if chat_base_url
                    else "Must be an absolute http(s) service URL or /v1/responses "
                    "endpoint without credentials, a query string, or a fragment."
                ),
            )
        )

        ollama_url = env("OLLAMA_BASE_URL")
        if ollama_url:
            valid = valid_http_url(ollama_url)
            checks.append(
                DoctorCheck(
                    "PASS" if valid else "FAIL",
                    "Ollama base URL",
                    "Valid URL." if valid else "Not an absolute http(s) URL.",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "INFO",
                    "Ollama base URL",
                    "Not configured on this host; Granite readiness verifies Ollama remotely.",
                )
            )
        return checks

    def database_checks(self) -> list[DoctorCheck]:
        if self.db_backend != "mongodb":
            return [
                DoctorCheck(
                    "INFO",
                    "MongoDB connection",
                    "Skipped because the configured backend is not MongoDB.",
                )
            ]
        if not self.mongodb_uri:
            return [
                DoctorCheck(
                    "FAIL",
                    "MongoDB connection",
                    "ROCKY_MONGODB_URI is required for the MongoDB backend.",
                )
            ]
        if not self.include_network:
            return [
                DoctorCheck(
                    "INFO",
                    "MongoDB connection",
                    "Skipped by --skip-network; the required URI is configured.",
                )
            ]
        try:
            self.mongo_pinger(self.mongodb_uri, self.db_name)
        except Exception as error:
            return [
                DoctorCheck(
                    "FAIL",
                    "MongoDB connection",
                    f"Ping failed: {type(error).__name__}.",
                )
            ]
        return [DoctorCheck("PASS", "MongoDB connection", "Ping succeeded.")]

    def network_checks(self) -> list[DoctorCheck]:
        checks = [
            self.check_json_service("backend health", derive_backend_health_url()),
            self.check_json_service("chat API health", f"{derive_chat_base_url()}/health"),
            self.check_chat_readiness(),
            self.check_granite_readiness(),
        ]
        return checks

    def get_json(self, url: str, *, headers: dict[str, str] | None = None):
        response = self.session.get(url, headers=headers or {}, timeout=self.timeout_seconds)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response, payload if isinstance(payload, dict) else {}

    def check_json_service(self, name: str, url: str) -> DoctorCheck:
        if not valid_http_url(url):
            return DoctorCheck("FAIL", name, "Service URL is invalid.")
        try:
            response, payload = self.get_json(url)
        except requests.RequestException as error:
            return DoctorCheck("FAIL", name, f"Connection failed: {type(error).__name__}.")
        passed = response.status_code == 200 and payload.get("ok") is True
        return DoctorCheck(
            "PASS" if passed else "FAIL",
            name,
            "Healthy." if passed else f"HTTP {response.status_code} or unhealthy response.",
        )

    def check_chat_readiness(self) -> DoctorCheck:
        url = f"{derive_chat_base_url()}/ready"
        if not valid_http_url(url):
            return DoctorCheck("FAIL", "chat API readiness", "Service URL is invalid.")
        try:
            response, payload = self.get_json(url)
        except requests.RequestException as error:
            return DoctorCheck(
                "FAIL", "chat API readiness", f"Connection failed: {type(error).__name__}."
            )

        dependencies = payload.get("dependencies")
        models = payload.get("models")
        dependency_values = list(dependencies.values()) if isinstance(dependencies, dict) else []
        reported_inference = models.get("inference") if isinstance(models, dict) else None
        reported_granite = models.get("granite") if isinstance(models, dict) else None
        feature_errors = self.chat_feature_errors(payload)
        base_ready = (
            response.status_code == 200
            and payload.get("ok") is True
            and bool(dependency_values)
            and all(value is True for value in dependency_values)
            and reported_inference == self.inference_model
            and reported_granite == self.inference_model
        )
        passed = base_ready and not feature_errors
        if passed:
            detail = (
                f"Ready with inference model '{self.inference_model}'; "
                "streaming and image capabilities match configuration."
            )
        else:
            reasons = []
            if not base_ready:
                reasons.append("dependencies or model mapping are not ready")
            reasons.extend(feature_errors)
            detail = f"HTTP {response.status_code}; " + "; ".join(reasons) + "."
        return DoctorCheck("PASS" if passed else "FAIL", "chat API readiness", detail)

    def chat_feature_errors(self, payload: dict) -> list[str]:
        errors: list[str] = []
        expected_streaming = configured_boolean("ROCKY_ENABLE_STREAMING")
        expected_image_input = configured_boolean("ROCKY_ENABLE_IMAGE_INPUT")
        capabilities = payload.get("capabilities")
        streaming = payload.get("streaming")
        image_input = payload.get("image_input")

        if expected_streaming is None:
            errors.append("ROCKY_ENABLE_STREAMING is invalid")
        if expected_image_input is None:
            errors.append("ROCKY_ENABLE_IMAGE_INPUT is invalid")

        if not isinstance(capabilities, dict):
            errors.append("capabilities were not reported")
        else:
            expected_features = {
                "supports_streaming": expected_streaming,
                "supports_image_input": expected_image_input,
            }
            for name, expected in expected_features.items():
                if expected is not None and capabilities.get(name) is not expected:
                    errors.append(f"capabilities.{name} does not match configuration")

            expected_limits = configured_image_limits()
            if expected_limits is None:
                errors.append("configured image limits are invalid")
            else:
                for name, expected in expected_limits.items():
                    if capabilities.get(name) != expected:
                        errors.append(f"capabilities.{name} does not match configuration")

        if not isinstance(streaming, dict):
            errors.append("streaming readiness was not reported")
        elif expected_streaming is not None:
            for name in ("rocky_enabled", "granite_enabled"):
                if streaming.get(name) is not expected_streaming:
                    errors.append(f"streaming.{name} does not match configuration")

        if not isinstance(image_input, dict):
            errors.append("image-input readiness was not reported")
        elif expected_image_input is not None:
            for name in ("rocky_enabled", "granite_enabled"):
                if image_input.get(name) is not expected_image_input:
                    errors.append(f"image_input.{name} does not match configuration")
            if expected_image_input and image_input.get("limits_match") is not True:
                errors.append("image_input.limits_match is not true")

        return errors

    def check_granite_readiness(self) -> DoctorCheck:
        url = derive_granite_readiness_url()
        if not valid_http_url(url):
            return DoctorCheck("FAIL", "Granite readiness", "Service URL is invalid.")
        token = env("ROCKY_GRANITE_TOKEN")
        headers = {"X-Rocky-Granite-Token": token} if token else {}
        try:
            response, payload = self.get_json(url, headers=headers)
        except requests.RequestException as error:
            return DoctorCheck(
                "FAIL", "Granite readiness", f"Connection failed: {type(error).__name__}."
            )
        passed = (
            response.status_code == 200
            and payload.get("ok") is True
            and payload.get("model") == self.inference_model
            and isinstance(payload.get("dependencies"), dict)
            and payload["dependencies"].get("ollama") is True
            and payload["dependencies"].get("model_available") is True
        )
        detail = (
            f"Ollama has model '{self.inference_model}'."
            if passed
            else f"HTTP {response.status_code}; Ollama or the configured model is unavailable."
        )
        return DoctorCheck("PASS" if passed else "FAIL", "Granite readiness", detail)
