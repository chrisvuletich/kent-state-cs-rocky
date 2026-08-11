from __future__ import annotations

import math
import os
from urllib.parse import urlparse


VALID_APP_ENVS = {"development", "testing", "production"}
PLACEHOLDER_PREFIXES = ("replace-with", "change-me", "changeme")


def env_text(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_choice(name: str, default: str, choices: set[str]) -> str:
    value = env_text(name, default).lower() or default
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise RuntimeError(f"Invalid {name}: expected one of {expected}.")
    return value


def env_bool(name: str, default: bool) -> bool:
    value = env_text(name, "true" if default else "false").lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError(f"Invalid {name}: expected exactly true or false.")


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw_value = env_text(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"Invalid {name}: expected an integer.") from error
    if minimum is not None and value < minimum:
        raise RuntimeError(f"Invalid {name}: must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise RuntimeError(f"Invalid {name}: must be at most {maximum}.")
    return value


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    allow_minimum: bool = True,
) -> float:
    raw_value = env_text(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"Invalid {name}: expected a number.") from error
    if not math.isfinite(value):
        raise RuntimeError(f"Invalid {name}: expected a finite number.")
    if minimum is not None and (
        value < minimum or (value == minimum and not allow_minimum)
    ):
        comparison = "at least" if allow_minimum else "greater than"
        raise RuntimeError(f"Invalid {name}: must be {comparison} {minimum:g}.")
    return value


def env_http_url(name: str, default: str) -> str:
    value = env_text(name, default)
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as error:
        raise RuntimeError(
            f"Invalid {name}: expected an absolute http(s) URL without credentials."
        ) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise RuntimeError(
            f"Invalid {name}: expected an absolute http(s) URL without credentials, "
            "a query string, or a fragment."
        )
    return value.rstrip("/")


def app_env() -> str:
    return env_choice("ROCKY_APP_ENV", "development", VALID_APP_ENVS)


def require_production_secret(name: str, value: str) -> None:
    is_placeholder = value.lower().startswith(PLACEHOLDER_PREFIXES)
    if len(value) < 32 or is_placeholder:
        raise RuntimeError(
            f"{name} must be a non-placeholder value of at least 32 characters in production."
        )
