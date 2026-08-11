from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


VALID_APP_ENVS = {"development", "testing", "production"}
VALID_DB_BACKENDS = {"mongita", "mongodb"}
PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme")


@dataclass(frozen=True)
class Settings:
    app_env: str
    host: str
    port: int
    debug: bool
    db_backend: str
    mongodb_uri: str
    db_name: str
    mongita_path: str
    enable_db_inspector: bool
    enable_preview_login: bool
    enable_microsoft_oauth: bool
    internal_proxy_secret: str = ""
    hardware_telemetry_enabled: bool = False
    hardware_metrics_url: str = ""
    hardware_metrics_token: str = ""
    hardware_sample_interval_seconds: int = 30
    hardware_metrics_timeout_seconds: int = 5
    hardware_retention_days: int = 90


def _env_value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_choice(name: str, default: str, choices: set[str]) -> str:
    value = _env_value(name, default).lower() or default
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise RuntimeError(f"Invalid {name}: expected one of {expected}.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = _env_value(name, "true" if default else "false").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError(f"Invalid {name}: expected exactly true or false.")


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw_value = _env_value(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"Invalid {name}: expected an integer.") from error
    if minimum is not None and value < minimum:
        raise RuntimeError(f"Invalid {name}: must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"Invalid {name}: must be at most {maximum}.")
    return value


def _valid_http_url(value: str) -> bool:
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


def _require_production_secret(name: str, value: str) -> None:
    is_placeholder = value.lower().startswith(PLACEHOLDER_PREFIXES)
    if len(value) < 32 or is_placeholder:
        raise RuntimeError(
            f"{name} must be a non-placeholder value of at least 32 characters in production"
        )


def _load_env_files() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    load_dotenv(base_dir / ".env", override=False)
    load_dotenv(base_dir / ".env.local", override=True)


def _resolve_mongita_path(value: str) -> str:
    repository_root = Path(__file__).resolve().parents[2]
    configured_path = Path(value.strip() or ".rocky-data/mongita").expanduser()
    if not configured_path.is_absolute():
        configured_path = repository_root / configured_path
    return str(configured_path.resolve())


def get_settings() -> Settings:
    _load_env_files()

    app_env = _env_choice("ROCKY_APP_ENV", "development", VALID_APP_ENVS)
    default_db_backend = "mongodb" if app_env == "production" else "mongita"
    db_backend = _env_choice(
        "ROCKY_DB_BACKEND", default_db_backend, VALID_DB_BACKENDS
    )
    mongodb_uri = _env_value("ROCKY_MONGODB_URI")
    hidden_api_key_secret = _env_value("ROCKY_HIDDEN_API_KEY_SECRET")
    internal_proxy_secret = _env_value("ROCKY_INTERNAL_PROXY_SECRET")

    if app_env == "production" and db_backend != "mongodb":
        raise RuntimeError("ROCKY_DB_BACKEND must be mongodb in production")
    if db_backend == "mongodb" and not mongodb_uri:
        raise RuntimeError("ROCKY_MONGODB_URI is required for the MongoDB backend")
    if app_env == "production":
        _require_production_secret(
            "ROCKY_HIDDEN_API_KEY_SECRET", hidden_api_key_secret
        )
        _require_production_secret(
            "ROCKY_INTERNAL_PROXY_SECRET", internal_proxy_secret
        )

    debug = _env_bool("ROCKY_DEBUG", app_env != "production")
    enable_db_inspector = _env_bool(
        "ROCKY_ENABLE_DB_INSPECTOR", app_env != "production"
    )
    if app_env == "production" and debug:
        raise RuntimeError("ROCKY_DEBUG must be false in production")
    if app_env == "production" and enable_db_inspector:
        raise RuntimeError("ROCKY_ENABLE_DB_INSPECTOR must be false in production")

    hardware_telemetry_enabled = _env_bool(
        "ROCKY_HARDWARE_TELEMETRY_ENABLED", False
    )
    hardware_metrics_url = _env_value("ROCKY_HARDWARE_METRICS_URL")
    hardware_metrics_token = _env_value("ROCKY_HARDWARE_METRICS_TOKEN")
    if hardware_telemetry_enabled and not hardware_metrics_url:
        raise RuntimeError(
            "ROCKY_HARDWARE_METRICS_URL is required when hardware telemetry is enabled"
        )
    if hardware_telemetry_enabled and not _valid_http_url(hardware_metrics_url):
        raise RuntimeError(
            "Invalid ROCKY_HARDWARE_METRICS_URL: expected an absolute http(s) URL "
            "without credentials, a query string, or a fragment."
        )
    if app_env == "production" and hardware_telemetry_enabled:
        _require_production_secret(
            "ROCKY_HARDWARE_METRICS_TOKEN", hardware_metrics_token
        )

    host = _env_value("ROCKY_API_HOST", "127.0.0.1") or "127.0.0.1"
    port = _env_int("ROCKY_API_PORT", 5001, minimum=1, maximum=65535)

    microsoft_override = _env_bool("ROCKY_ENABLE_MICROSOFT_OAUTH", False)
    if app_env == "production":
        enable_microsoft_oauth = True
    elif app_env == "testing":
        enable_microsoft_oauth = False
    else:
        enable_microsoft_oauth = microsoft_override

    return Settings(
        app_env=app_env,
        host=host,
        port=port,
        debug=debug,
        db_backend=db_backend,
        mongodb_uri=mongodb_uri,
        db_name=_env_value("ROCKY_DB_NAME", "rocky_db") or "rocky_db",
        mongita_path=_resolve_mongita_path(
            _env_value("ROCKY_MONGITA_PATH", ".rocky-data/mongita")
        ),
        enable_db_inspector=enable_db_inspector,
        enable_preview_login=not enable_microsoft_oauth,
        enable_microsoft_oauth=enable_microsoft_oauth,
        internal_proxy_secret=internal_proxy_secret,
        hardware_telemetry_enabled=hardware_telemetry_enabled,
        hardware_metrics_url=hardware_metrics_url,
        hardware_metrics_token=hardware_metrics_token,
        hardware_sample_interval_seconds=_env_int(
            "ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS", 30, minimum=10
        ),
        hardware_metrics_timeout_seconds=_env_int(
            "ROCKY_HARDWARE_METRICS_TIMEOUT_SECONDS", 5, minimum=1
        ),
        hardware_retention_days=_env_int(
            "ROCKY_HARDWARE_RETENTION_DAYS", 90, minimum=1
        ),
    )
