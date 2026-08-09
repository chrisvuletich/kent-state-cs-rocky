from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_PROMPT = "Reply with exactly: Rocky deployment smoke passed."


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    api_key: str = field(repr=False)
    expected_model: str
    timeout_seconds: float
    include_generation: bool


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str


def normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    for suffix in ("/v1/responses", "/v1/models"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("ROCKY_BASE_URL must be an absolute http:// or https:// URL.")
    return normalized


def response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def error_detail(response: requests.Response, payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return f"HTTP {response.status_code}: {error['message']}"
    if isinstance(error, str) and error.strip():
        return f"HTTP {response.status_code}: {error.strip()}"
    return f"HTTP {response.status_code}"


class DeploymentSmoke:
    def __init__(self, config: SmokeConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self.auth_headers = {"Authorization": f"Bearer {config.api_key}"}

    def request(self, method: str, path: str, **kwargs):
        return self.session.request(
            method,
            f"{self.config.base_url}{path}",
            timeout=self.config.timeout_seconds,
            **kwargs,
        )

    def run(self) -> list[SmokeCheck]:
        checks = [self.check_web_health(), self.check_service_health()]
        models_check, model = self.check_models()
        checks.append(models_check)
        if self.config.include_generation:
            if model:
                checks.append(self.check_generation(model))
            else:
                checks.append(
                    SmokeCheck(
                        "generation",
                        False,
                        "Skipped because model discovery failed.",
                    )
                )
        return checks

    def check_web_health(self) -> SmokeCheck:
        try:
            response = self.request("GET", "/api/health")
        except requests.RequestException as error:
            return SmokeCheck("web health", False, f"Connection failed: {type(error).__name__}")

        payload = response_payload(response)
        passed = response.status_code == 200 and payload.get("ok") is True
        detail = "Rocky web is reachable." if passed else error_detail(response, payload)
        return SmokeCheck("web health", passed, detail)

    def check_service_health(self) -> SmokeCheck:
        try:
            response = self.request("GET", "/api/server-health")
        except requests.RequestException as error:
            return SmokeCheck(
                "service health",
                False,
                f"Connection failed: {type(error).__name__}",
            )

        payload = response_payload(response)
        services = payload.get("services")
        unavailable: list[str] = []
        if isinstance(services, list):
            unavailable = [
                str(service.get("name") or "unknown")
                for service in services
                if isinstance(service, dict) and service.get("ok") is not True
            ]
        passed = response.status_code == 200 and payload.get("ok") is True and not unavailable
        if passed:
            detail = "All reported services are healthy."
        elif unavailable:
            detail = "Unavailable: " + ", ".join(unavailable)
        else:
            detail = error_detail(response, payload)
        return SmokeCheck("service health", passed, detail)

    def check_models(self) -> tuple[SmokeCheck, str | None]:
        try:
            response = self.request("GET", "/v1/models", headers=self.auth_headers)
        except requests.RequestException as error:
            return (
                SmokeCheck("model discovery", False, f"Connection failed: {type(error).__name__}"),
                None,
            )

        payload = response_payload(response)
        if response.status_code != 200:
            return SmokeCheck("model discovery", False, error_detail(response, payload)), None

        data = payload.get("data")
        model_ids = (
            [
                item.get("id").strip()
                for item in data
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and item.get("id").strip()
            ]
            if isinstance(data, list)
            else []
        )
        if not model_ids:
            return SmokeCheck("model discovery", False, "No model identifiers were returned."), None

        expected = self.config.expected_model
        if expected and expected not in model_ids:
            return (
                SmokeCheck(
                    "model discovery",
                    False,
                    f"Expected model '{expected}' was not advertised.",
                ),
                None,
            )

        selected = expected or model_ids[0]
        return SmokeCheck("model discovery", True, f"Using model '{selected}'."), selected

    def check_generation(self, model: str) -> SmokeCheck:
        try:
            response = self.request(
                "POST",
                "/v1/responses",
                headers={**self.auth_headers, "Content-Type": "application/json"},
                json={
                    "model": model,
                    "input": DEFAULT_PROMPT,
                    "max_output_tokens": 32,
                    "store": False,
                },
            )
        except requests.RequestException as error:
            return SmokeCheck("generation", False, f"Connection failed: {type(error).__name__}")

        payload = response_payload(response)
        if response.status_code != 200:
            return SmokeCheck("generation", False, error_detail(response, payload))

        output_text = payload.get("output_text")
        usage = payload.get("usage")
        request_id = response.headers.get("x-request-id") or response.headers.get(
            "X-Rocky-Request-Id"
        )
        valid = (
            payload.get("status") == "completed"
            and payload.get("model") == model
            and isinstance(output_text, str)
            and bool(output_text.strip())
            and isinstance(usage, dict)
            and isinstance(request_id, str)
            and bool(request_id.strip())
        )
        detail = (
            f"Completed with request ID {request_id}."
            if valid
            else "Response was missing status, model, output, usage, or request ID."
        )
        return SmokeCheck("generation", valid, detail)


def build_config(args: argparse.Namespace) -> SmokeConfig:
    base_url = normalize_base_url(args.base_url or os.getenv("ROCKY_BASE_URL", ""))
    api_key = os.getenv("ROCKY_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ROCKY_API_KEY is required.")
    expected_model = (args.expected_model or os.getenv("ROCKY_EXPECTED_MODEL", "")).strip()
    timeout_seconds = args.timeout
    if timeout_seconds <= 0:
        raise ValueError("--timeout must be greater than zero.")
    return SmokeConfig(
        base_url=base_url,
        api_key=api_key,
        expected_model=expected_model,
        timeout_seconds=timeout_seconds,
        include_generation=args.include_generation,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a deployed Rocky public surface.")
    parser.add_argument(
        "--base-url",
        default="",
        help="Public Rocky origin. Defaults to ROCKY_BASE_URL.",
    )
    parser.add_argument(
        "--expected-model",
        default="",
        help="Expected public model. Defaults to ROCKY_EXPECTED_MODEL or the discovered model.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("ROCKY_SMOKE_TIMEOUT_SECONDS", "15")),
        help="Per-request timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--include-generation",
        action="store_true",
        help="Submit one small, audited model request after read-only checks pass.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        config = build_config(parse_args(argv))
    except (TypeError, ValueError) as error:
        print(f"FAIL  configuration: {error}", file=sys.stderr)
        return 2

    checks = DeploymentSmoke(config).run()
    for check in checks:
        label = "PASS" if check.passed else "FAIL"
        print(f"{label:<4}  {check.name}: {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
