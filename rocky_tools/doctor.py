from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import requests
from pymongo import MongoClient


VALID_APP_ENVS = {"development", "testing", "production"}
VALID_DB_BACKENDS = {"mongita", "mongodb"}
PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme")
PRODUCTION_SECRETS = (
    "ROCKY_HIDDEN_API_KEY_SECRET",
    "ROCKY_SESSION_SECRET",
    "ROCKY_INTERNAL_PROXY_SECRET",
    "ROCKY_GRANITE_TOKEN",
)


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
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def derive_chat_base_url() -> str:
    configured = env("ROCKY_CHAT_API_URL")
    if configured:
        normalized = configured.rstrip("/")
        if normalized.endswith("/v1/responses"):
            return normalized[: -len("/v1/responses")]
        return normalized
    host = connectable_host(env("ROCKY_CHAT_API_HOST", "127.0.0.1"))
    port = env("ROCKY_CHAT_API_PORT", "5003")
    return f"http://{host}:{port}"


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
        self.app_env = env("ROCKY_APP_ENV", "development").lower()
        self.public_app_env = env("PUBLIC_APP_ENV").lower()
        self.db_backend = env(
            "ROCKY_DB_BACKEND",
            "mongodb" if self.app_env == "production" else "mongita",
        ).lower()
        self.db_name = env("ROCKY_DB_NAME", "rocky_db")
        self.mongodb_uri = env("ROCKY_MONGODB_URI")
        self.public_model = env("ROCKY_PUBLIC_MODEL")
        self.inference_model = env("OLLAMA_MODEL")

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
        checks.extend(self.request_logging_checks())
        checks.extend(self.authentication_checks())
        checks.extend(self.model_checks())
        checks.extend(self.url_checks())
        return checks

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
        checks: list[DoctorCheck] = []
        for name in ("PUBLIC_ENABLE_DBTEST", "PUBLIC_ENABLE_MICROSOFT_OAUTH"):
            value = env(name, "false").lower()
            if value not in {"true", "false"}:
                checks.append(
                    DoctorCheck(
                        "FAIL",
                        name,
                        "Must be exactly true or false.",
                    )
                )
            elif (
                name == "PUBLIC_ENABLE_DBTEST"
                and self.public_app_env == "production"
                and value == "true"
            ):
                checks.append(
                    DoctorCheck(
                        "FAIL",
                        name,
                        "Must be false in production.",
                    )
                )
            else:
                checks.append(DoctorCheck("PASS", name, value))
        return checks

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
        if self.public_app_env != "production":
            return [DoctorCheck("INFO", "Microsoft authentication", "Not required outside production.")]

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
                    else "A specific Kent tenant ID is required in production."
                ),
            )
            for name, value in values.items()
        ]
        checks.append(
            DoctorCheck(
                "PASS",
                "Microsoft OAuth mode",
                "Enabled by PUBLIC_APP_ENV=production.",
            )
        )
        return checks

    def model_checks(self) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        if self.public_model and self.inference_model:
            checks.append(
                DoctorCheck(
                    "PASS",
                    "model mapping",
                    f"Public '{self.public_model}' maps to inference '{self.inference_model}'.",
                )
            )
        else:
            missing = [
                name
                for name, value in (
                    ("ROCKY_PUBLIC_MODEL", self.public_model),
                    ("OLLAMA_MODEL", self.inference_model),
                )
                if not value
            ]
            checks.append(
                DoctorCheck("FAIL", "model mapping", "Missing: " + ", ".join(missing))
            )
        return checks

    def url_checks(self) -> list[DoctorCheck]:
        urls = {
            "frontend API URL": env("PUBLIC_API_BASE_URL"),
            "backend health URL": derive_backend_health_url(),
            "chat API URL": derive_chat_base_url(),
            "Granite generation URL": env("ROCKY_GRANITE_URL"),
            "Granite readiness URL": env("ROCKY_GRANITE_READY_URL"),
        }
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
        passed = (
            response.status_code == 200
            and payload.get("ok") is True
            and bool(dependency_values)
            and all(value is True for value in dependency_values)
            and reported_inference == self.inference_model
            and reported_granite == self.inference_model
        )
        if passed:
            detail = f"Ready with inference model '{self.inference_model}'."
        else:
            detail = f"HTTP {response.status_code}; dependencies or model mapping are not ready."
        return DoctorCheck("PASS" if passed else "FAIL", "chat API readiness", detail)

    def check_granite_readiness(self) -> DoctorCheck:
        url = env("ROCKY_GRANITE_READY_URL")
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
