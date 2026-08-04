from __future__ import annotations

import os
from pathlib import Path

API_HOST_VAR = "ROCKY_API_HOST"
API_PORT_VAR = "ROCKY_API_PORT"
WEB_HOST_VAR = "ROCKY_WEB_HOST"
WEB_PORT_VAR = "ROCKY_WEB_PORT"
ALLOWED_HOSTS_VAR = "ROCKY_ALLOWED_HOSTS"
GRANITE_HOST_VAR = "ROCKY_GRANITE_HOST"
GRANITE_PORT_VAR = "ROCKY_GRANITE_PORT"
CHAT_API_HOST_VAR = "ROCKY_CHAT_API_HOST"
CHAT_API_PORT_VAR = "ROCKY_CHAT_API_PORT"


def load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue

        if override or key not in os.environ:
            os.environ[key] = value


def load_project_env(repo_root: Path, backend_dir: Path, frontend_dir: Path, *extra_dirs: Path) -> None:
    load_env_file(repo_root / ".env", override=False)
    load_env_file(repo_root / ".env.local", override=True)

    load_env_file(backend_dir / ".env", override=False)
    load_env_file(backend_dir / ".env.local", override=True)

    load_env_file(frontend_dir / ".env", override=False)
    load_env_file(frontend_dir / ".env.local", override=True)

    for service_dir in extra_dirs:
        load_env_file(service_dir / ".env", override=False)
        load_env_file(service_dir / ".env.local", override=True)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def require_port(name: str) -> str:
    value = require_env(name)
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid {name}: \"{value}\". Expected an integer between 1 and 65535.") from exc

    if port < 1 or port > 65535:
        raise RuntimeError(f"Invalid {name}: \"{value}\". Expected an integer between 1 and 65535.")
    return str(port)


def backend_bind() -> tuple[str, str]:
    host = require_env(API_HOST_VAR)
    port = require_port(API_PORT_VAR)
    return host, port


def backend_url() -> str:
    host, port = backend_bind()
    return f"http://{host}:{port}"


def frontend_bind() -> tuple[str, str]:
    host = require_env(WEB_HOST_VAR)
    port = require_port(WEB_PORT_VAR)
    return host, port


def allowed_hosts() -> str:
    value = require_env(ALLOWED_HOSTS_VAR)
    hosts = [entry.strip() for entry in value.split(",") if entry.strip()]
    if not hosts:
        raise RuntimeError(
            "Invalid ROCKY_ALLOWED_HOSTS: provide at least one host, e.g. \"localhost,127.0.0.1\"."
        )
    return ",".join(hosts)


def granite_bind() -> tuple[str, str]:
    host = require_env(GRANITE_HOST_VAR)
    port = require_port(GRANITE_PORT_VAR)
    return host, port


def granite_url() -> str:
    host, port = granite_bind()
    return f"http://{host}:{port}/generate"


def chat_api_bind() -> tuple[str, str]:
    host = require_env(CHAT_API_HOST_VAR)
    port = require_port(CHAT_API_PORT_VAR)
    return host, port


def chat_api_url() -> str:
    chat_host, chat_port = chat_api_bind()
    completed_URL = f"http://{chat_host}:{chat_port}/v1/responses"
    return completed_URL
