from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


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

    app_env = os.getenv("ROCKY_APP_ENV", "development").strip().lower() or "development"
    db_backend = os.getenv("ROCKY_DB_BACKEND", "mongita").strip().lower() or "mongita"
    mongodb_uri = os.getenv("ROCKY_MONGODB_URI", "").strip()
    internal_proxy_secret = os.getenv("ROCKY_INTERNAL_PROXY_SECRET", "").strip()

    if app_env == "production" and not mongodb_uri:
        raise RuntimeError("ROCKY_MONGODB_URI is required when ROCKY_APP_ENV=production")
    if app_env == "production" and not internal_proxy_secret:
        raise RuntimeError("ROCKY_INTERNAL_PROXY_SECRET is required when ROCKY_APP_ENV=production")
    if app_env == "production" and len(internal_proxy_secret) < 32:
        raise RuntimeError(
            "ROCKY_INTERNAL_PROXY_SECRET must contain at least 32 characters in production"
        )

    hardware_telemetry_enabled = _is_truthy(
        os.getenv("ROCKY_HARDWARE_TELEMETRY_ENABLED", "false")
    )
    hardware_metrics_url = os.getenv("ROCKY_HARDWARE_METRICS_URL", "").strip()
    hardware_metrics_token = os.getenv("ROCKY_HARDWARE_METRICS_TOKEN", "").strip()
    if hardware_telemetry_enabled and not hardware_metrics_url:
        raise RuntimeError(
            "ROCKY_HARDWARE_METRICS_URL is required when hardware telemetry is enabled"
        )
    if app_env == "production" and hardware_telemetry_enabled and not hardware_metrics_token:
        raise RuntimeError(
            "ROCKY_HARDWARE_METRICS_TOKEN is required for production hardware telemetry"
        )

    host = os.getenv("ROCKY_API_HOST", "127.0.0.1")
    port = os.getenv("ROCKY_API_PORT", "5001")

    microsoft_override = _is_truthy(os.getenv("ROCKY_ENABLE_MICROSOFT_OAUTH", "false"))
    if app_env == "production":
        enable_microsoft_oauth = True
    elif app_env == "testing":
        enable_microsoft_oauth = False
    else:
        enable_microsoft_oauth = microsoft_override

    return Settings(
        app_env=app_env,
        host=host.strip() or "127.0.0.1",
        port=int(port),
        debug=_is_truthy(os.getenv("ROCKY_DEBUG", "false" if app_env == "production" else "true")),
        db_backend=db_backend,
        mongodb_uri=mongodb_uri,
        db_name=os.getenv("ROCKY_DB_NAME", "rocky_db").strip() or "rocky_db",
        mongita_path=_resolve_mongita_path(
            os.getenv("ROCKY_MONGITA_PATH", ".rocky-data/mongita")
        ),
        enable_db_inspector=_is_truthy(os.getenv("ROCKY_ENABLE_DB_INSPECTOR", "false" if app_env == "production" else "true")),
        enable_preview_login=not enable_microsoft_oauth,
        enable_microsoft_oauth=enable_microsoft_oauth,
        internal_proxy_secret=internal_proxy_secret,
        hardware_telemetry_enabled=hardware_telemetry_enabled,
        hardware_metrics_url=hardware_metrics_url,
        hardware_metrics_token=hardware_metrics_token,
        hardware_sample_interval_seconds=max(
            10, int(os.getenv("ROCKY_HARDWARE_SAMPLE_INTERVAL_SECONDS", "30"))
        ),
        hardware_metrics_timeout_seconds=max(
            1, int(os.getenv("ROCKY_HARDWARE_METRICS_TIMEOUT_SECONDS", "5"))
        ),
        hardware_retention_days=max(
            1, int(os.getenv("ROCKY_HARDWARE_RETENTION_DAYS", "90"))
        ),
    )
