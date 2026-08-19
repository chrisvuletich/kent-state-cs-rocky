from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests


DEFAULT_PROMPT = "Reply with exactly: Rocky deployment smoke passed."
IMAGE_PROMPT = "Briefly confirm that you received this image."
SMOKE_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
)
RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    api_key: str = field(repr=False)
    expected_model: str
    timeout_seconds: float
    include_generation: bool
    include_streaming: bool = False
    include_image: bool = False
    include_advertised: bool = False


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    supports_streaming: bool
    supports_image_input: bool


class StreamContractError(ValueError):
    """Raised when a deployed stream does not satisfy Rocky's public subset."""


def normalize_base_url(value: str) -> str:
    raw_value = value.strip()
    try:
        parsed = urlparse(raw_value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as error:
        raise ValueError(
            "ROCKY_BASE_URL must be an absolute http(s) URL without credentials, "
            "a query string, or a fragment."
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
        raise ValueError(
            "ROCKY_BASE_URL must be an absolute http(s) URL without credentials, "
            "a query string, or a fragment."
        )

    path = parsed.path.rstrip("/")
    for suffix in ("/v1/responses", "/v1/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


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


def response_header(response: requests.Response, name: str) -> str:
    """Read a response header from real or lightweight test responses."""
    expected = name.lower()
    for header_name, value in response.headers.items():
        if str(header_name).lower() == expected:
            return str(value).strip()
    return ""


def request_id_for(response: requests.Response) -> str:
    return response_header(response, "x-request-id") or response_header(
        response,
        "x-rocky-request-id",
    )


def completed_output_text(response: dict[str, Any]) -> str | None:
    """Read Rocky's one-message, one-output-text successful stream subset."""
    output = response.get("output")
    if not isinstance(output, list) or len(output) != 1:
        return None
    item = output[0]
    if not isinstance(item, dict) or item.get("status") != "completed":
        return None
    content = item.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return None
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "output_text":
        return None
    text = part.get("text")
    return text if isinstance(text, str) else None


def parse_stream_events(lines) -> list[tuple[str, dict[str, Any]]]:
    """Parse Rocky's deliberately small SSE representation."""
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    def finish_event():
        nonlocal event_name, data_lines
        if event_name is None and not data_lines:
            return
        if event_name is None or not data_lines:
            raise StreamContractError("Each SSE frame must contain event and data fields.")
        data_text = "\n".join(data_lines)
        if data_text == "[DONE]":
            raise StreamContractError("Rocky streams must not contain a [DONE] sentinel.")
        try:
            payload = json.loads(data_text)
        except (TypeError, ValueError) as error:
            raise StreamContractError("An SSE data field was not valid JSON.") from error
        if not isinstance(payload, dict):
            raise StreamContractError("Every SSE data field must contain a JSON object.")
        if payload.get("type") != event_name:
            raise StreamContractError("The SSE event name did not match payload.type.")
        events.append((event_name, payload))
        event_name = None
        data_lines = []

    for raw_line in lines:
        if isinstance(raw_line, bytes):
            try:
                line = raw_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise StreamContractError("The stream was not valid UTF-8.") from error
        elif isinstance(raw_line, str):
            line = raw_line
        else:
            raise StreamContractError("The stream yielded a non-text line.")
        line = line.rstrip("\r")
        if not line:
            finish_event()
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            if event_name is not None:
                raise StreamContractError("An SSE frame contained more than one event field.")
            event_name = line[6:].lstrip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        else:
            raise StreamContractError("The stream contained an unsupported SSE field.")
    finish_event()
    return events


def validate_stream_events(
    events: list[tuple[str, dict[str, Any]]],
    expected_model: str,
) -> str:
    """Validate ordering and terminal consistency for Rocky's text stream."""
    if not events:
        raise StreamContractError("The stream contained no events.")

    for expected_sequence, (event_name, payload) in enumerate(events):
        if payload.get("sequence_number") != expected_sequence:
            raise StreamContractError(
                f"Expected sequence_number {expected_sequence} in {event_name}."
            )
        if event_name == "error":
            code = payload.get("code")
            message = payload.get("message")
            code_text = code if isinstance(code, str) and code else "stream_error"
            message_text = (
                message if isinstance(message, str) and message else "Unknown stream error."
            )
            raise StreamContractError(f"Rocky ended the stream with {code_text}: {message_text}")

    event_names = [event_name for event_name, _payload in events]
    required_prefix = [
        "response.created",
        "response.in_progress",
        "response.output_item.added",
        "response.content_part.added",
    ]
    required_suffix = [
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    if event_names[:4] != required_prefix or event_names[-4:] != required_suffix:
        raise StreamContractError("The stream lifecycle events were missing or out of order.")
    delta_events = events[4:-4]
    if not delta_events or any(name != "response.output_text.delta" for name, _ in delta_events):
        raise StreamContractError("The stream must contain one or more text delta events.")
    deltas = [payload.get("delta") for _name, payload in delta_events]
    if any(not isinstance(delta, str) or not delta for delta in deltas):
        raise StreamContractError("Every text delta must be a non-empty string.")
    output_text = "".join(deltas)

    done_text = events[-4][1].get("text")
    part = events[-3][1].get("part")
    item = events[-2][1].get("item")
    completed = events[-1][1].get("response")
    if not isinstance(part, dict) or part.get("text") != output_text:
        raise StreamContractError("The completed content part did not match the text deltas.")
    if not isinstance(item, dict):
        raise StreamContractError("The completed output item was missing.")
    item_text = completed_output_text({"output": [item]})
    if done_text != output_text or item_text != output_text:
        raise StreamContractError("A completed text field did not match the text deltas.")
    if not isinstance(completed, dict):
        raise StreamContractError("The response.completed payload was missing its response.")
    completed_text = completed_output_text(completed)
    if (
        completed.get("status") != "completed"
        or completed.get("model") != expected_model
        or not isinstance(completed.get("usage"), dict)
        or completed_text != output_text
    ):
        raise StreamContractError(
            "The completed response was missing status, model, output, or usage."
        )
    return output_text


def check_rate_limit_headers(response: requests.Response, name: str) -> SmokeCheck:
    """Validate Rocky's request-limit header contract without exhausting a key."""
    headers = {
        str(header_name).lower(): str(value).strip()
        for header_name, value in response.headers.items()
    }
    missing = [
        header_name for header_name in RATE_LIMIT_HEADERS if header_name not in headers
    ]
    if missing:
        return SmokeCheck(
            name,
            False,
            "Missing required header(s): " + ", ".join(missing) + ".",
        )

    limit_text = headers["x-ratelimit-limit-requests"]
    remaining_text = headers["x-ratelimit-remaining-requests"]
    reset_text = headers["x-ratelimit-reset-requests"]
    if re.fullmatch(r"[0-9]+", limit_text) is None:
        return SmokeCheck(name, False, "Request limit must be a positive integer.")
    if re.fullmatch(r"[0-9]+", remaining_text) is None:
        return SmokeCheck(
            name,
            False,
            "Remaining requests must be a non-negative integer.",
        )

    reset_match = re.fullmatch(r"([0-9]+)s", reset_text)
    if reset_match is None:
        return SmokeCheck(
            name,
            False,
            "Reset must be a whole number of seconds such as '17s'.",
        )

    try:
        limit = int(limit_text)
        remaining = int(remaining_text)
        reset_seconds = int(reset_match.group(1))
    except ValueError:
        return SmokeCheck(
            name,
            False,
            "Rate-limit header values are too large to parse.",
        )

    if limit < 1:
        return SmokeCheck(name, False, "Request limit must be greater than zero.")
    if remaining > limit:
        return SmokeCheck(
            name,
            False,
            "Remaining requests cannot exceed the request limit.",
        )
    if not 1 <= reset_seconds <= RATE_LIMIT_WINDOW_SECONDS:
        return SmokeCheck(
            name,
            False,
            f"Reset must be between 1s and {RATE_LIMIT_WINDOW_SECONDS}s.",
        )

    return SmokeCheck(
        name,
        True,
        f"{limit} request(s)/minute; {remaining} remaining; resets in {reset_seconds}s.",
    )


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
        models_check, models_rate_limit_check, model = self.check_models()
        checks.extend((models_check, models_rate_limit_check))
        include_generation = (
            self.config.include_generation or self.config.include_advertised
        )
        include_streaming = self.config.include_streaming or (
            self.config.include_advertised
            and model is not None
            and model.supports_streaming
        )
        include_image = self.config.include_image or (
            self.config.include_advertised
            and model is not None
            and model.supports_image_input
        )
        requested_checks = [
            ("generation", include_generation, self.check_generation),
            (
                "streaming generation",
                include_streaming,
                self.check_streaming_generation,
            ),
            ("image generation", include_image, self.check_image_generation),
        ]
        failed_prerequisites = [check.name for check in checks if not check.passed]
        for name, enabled, check_function in requested_checks:
            if not enabled:
                continue
            if failed_prerequisites:
                detail = (
                    "Skipped because prerequisite checks failed: "
                    + ", ".join(failed_prerequisites)
                    + "."
                )
                checks.extend(self.skipped_generation_checks(name, detail))
            elif model is None:
                checks.extend(
                    self.skipped_generation_checks(
                        name,
                        "Skipped because model discovery failed.",
                    )
                )
            else:
                checks.extend(check_function(model))
        return checks

    @staticmethod
    def skipped_generation_checks(name: str, detail: str) -> tuple[SmokeCheck, SmokeCheck]:
        return (
            SmokeCheck(name, False, detail),
            SmokeCheck(
                f"{name} rate limit",
                False,
                "Skipped because no generation request was sent.",
            ),
        )

    def check_web_health(self) -> SmokeCheck:
        try:
            response = self.request("GET", "/api/health")
        except requests.RequestException as error:
            return SmokeCheck(
                "web health",
                False,
                f"Connection failed: {type(error).__name__}",
            )

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
        passed = (
            response.status_code == 200
            and payload.get("ok") is True
            and not unavailable
        )
        if passed:
            detail = "All reported services are healthy."
        elif unavailable:
            detail = "Unavailable: " + ", ".join(unavailable)
        else:
            detail = error_detail(response, payload)
        return SmokeCheck("service health", passed, detail)

    def check_models(self) -> tuple[SmokeCheck, SmokeCheck, ModelInfo | None]:
        try:
            response = self.request("GET", "/v1/models", headers=self.auth_headers)
        except requests.RequestException as error:
            return (
                SmokeCheck(
                    "model discovery",
                    False,
                    f"Connection failed: {type(error).__name__}",
                ),
                SmokeCheck(
                    "model rate limit",
                    False,
                    "Unavailable because model discovery did not receive a response.",
                ),
                None,
            )

        payload = response_payload(response)
        rate_limit_check = check_rate_limit_headers(response, "model rate limit")
        if response.status_code != 200:
            return (
                SmokeCheck("model discovery", False, error_detail(response, payload)),
                rate_limit_check,
                None,
            )

        data = payload.get("data")
        models_by_id = {
            item["id"].strip(): item
            for item in data
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item["id"].strip()
        } if isinstance(data, list) else {}
        if not models_by_id:
            return (
                SmokeCheck("model discovery", False, "No model identifiers were returned."),
                rate_limit_check,
                None,
            )

        expected = self.config.expected_model
        if expected and expected not in models_by_id:
            return (
                SmokeCheck(
                    "model discovery",
                    False,
                    f"Expected model '{expected}' was not advertised.",
                ),
                rate_limit_check,
                None,
            )

        selected = expected or next(iter(models_by_id))
        selected_payload = models_by_id[selected]
        metadata = selected_payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return (
            SmokeCheck("model discovery", True, f"Using model '{selected}'."),
            rate_limit_check,
            ModelInfo(
                model_id=selected,
                supports_streaming=metadata.get("supports_streaming") is True,
                supports_image_input=metadata.get("supports_image_input") is True,
            ),
        )

    def check_generation(self, model: ModelInfo) -> tuple[SmokeCheck, SmokeCheck]:
        try:
            response = self.request(
                "POST",
                "/v1/responses",
                headers={**self.auth_headers, "Content-Type": "application/json"},
                json={
                    "model": model.model_id,
                    "input": DEFAULT_PROMPT,
                    "max_output_tokens": 32,
                    "store": False,
                },
            )
        except requests.RequestException as error:
            return (
                SmokeCheck(
                    "generation",
                    False,
                    f"Connection failed: {type(error).__name__}",
                ),
                SmokeCheck(
                    "generation rate limit",
                    False,
                    "Unavailable because generation did not receive a response.",
                ),
            )

        payload = response_payload(response)
        rate_limit_check = check_rate_limit_headers(response, "generation rate limit")
        if response.status_code != 200:
            return (
                SmokeCheck("generation", False, error_detail(response, payload)),
                rate_limit_check,
            )

        return (
            self.completed_json_check("generation", response, payload, model.model_id),
            rate_limit_check,
        )

    def check_streaming_generation(
        self,
        model: ModelInfo,
    ) -> tuple[SmokeCheck, SmokeCheck]:
        name = "streaming generation"
        if not model.supports_streaming:
            return self.skipped_generation_checks(
                name,
                f"Model '{model.model_id}' does not advertise supports_streaming=true.",
            )
        try:
            response = self.request(
                "POST",
                "/v1/responses",
                headers={
                    **self.auth_headers,
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model.model_id,
                    "input": DEFAULT_PROMPT,
                    "max_output_tokens": 32,
                    "store": False,
                    "stream": True,
                },
                stream=True,
            )
        except requests.RequestException as error:
            return (
                SmokeCheck(name, False, f"Connection failed: {type(error).__name__}"),
                SmokeCheck(
                    f"{name} rate limit",
                    False,
                    "Unavailable because streaming generation did not receive a response.",
                ),
            )

        rate_limit_check = check_rate_limit_headers(response, f"{name} rate limit")
        if response.status_code != 200:
            payload = response_payload(response)
            response.close()
            return SmokeCheck(name, False, error_detail(response, payload)), rate_limit_check

        request_id = request_id_for(response)
        content_type = response_header(response, "content-type").lower()
        if not content_type.startswith("text/event-stream"):
            response.close()
            return (
                SmokeCheck(name, False, "Response Content-Type was not text/event-stream."),
                rate_limit_check,
            )

        try:
            events = parse_stream_events(response.iter_lines(decode_unicode=True))
            output_text = validate_stream_events(events, model.model_id)
        except (requests.RequestException, StreamContractError, UnicodeError) as error:
            return SmokeCheck(name, False, str(error)), rate_limit_check
        finally:
            response.close()

        valid_request_id = bool(request_id)
        detail = (
            f"Completed {len(events)} SSE events and {len(output_text)} text character(s) "
            f"with request ID {request_id}."
            if valid_request_id
            else "The stream completed but its response was missing a request ID."
        )
        return SmokeCheck(name, valid_request_id, detail), rate_limit_check

    def check_image_generation(
        self,
        model: ModelInfo,
    ) -> tuple[SmokeCheck, SmokeCheck]:
        name = "image generation"
        if not model.supports_image_input:
            return self.skipped_generation_checks(
                name,
                f"Model '{model.model_id}' does not advertise supports_image_input=true.",
            )
        try:
            response = self.request(
                "POST",
                "/v1/responses",
                headers={**self.auth_headers, "Content-Type": "application/json"},
                json={
                    "model": model.model_id,
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": IMAGE_PROMPT},
                                {
                                    "type": "input_image",
                                    "image_url": SMOKE_IMAGE_DATA_URL,
                                    "detail": "auto",
                                },
                            ],
                        }
                    ],
                    "max_output_tokens": 32,
                    "store": False,
                    "stream": False,
                },
            )
        except requests.RequestException as error:
            return (
                SmokeCheck(name, False, f"Connection failed: {type(error).__name__}"),
                SmokeCheck(
                    f"{name} rate limit",
                    False,
                    "Unavailable because image generation did not receive a response.",
                ),
            )

        payload = response_payload(response)
        rate_limit_check = check_rate_limit_headers(response, f"{name} rate limit")
        if response.status_code != 200:
            return SmokeCheck(name, False, error_detail(response, payload)), rate_limit_check
        return (
            self.completed_json_check(name, response, payload, model.model_id),
            rate_limit_check,
        )

    @staticmethod
    def completed_json_check(
        name: str,
        response: requests.Response,
        payload: dict[str, Any],
        expected_model: str,
    ) -> SmokeCheck:
        output_text = payload.get("output_text")
        usage = payload.get("usage")
        request_id = request_id_for(response)
        valid = (
            payload.get("status") == "completed"
            and payload.get("model") == expected_model
            and isinstance(output_text, str)
            and bool(output_text.strip())
            and isinstance(usage, dict)
            and bool(request_id)
        )
        detail = (
            f"Completed with request ID {request_id}."
            if valid
            else "Response was missing status, model, output, usage, or request ID."
        )
        return SmokeCheck(name, valid, detail)


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
        include_streaming=args.include_streaming,
        include_image=args.include_image,
        include_advertised=args.include_advertised,
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
        help="Submit one small, audited model request after non-generating checks pass.",
    )
    parser.add_argument(
        "--include-streaming",
        action="store_true",
        help="Submit one small, audited SSE request when the model advertises streaming.",
    )
    parser.add_argument(
        "--include-image",
        action="store_true",
        help="Submit one small, audited PNG request when the model advertises image input.",
    )
    parser.add_argument(
        "--include-advertised",
        action="store_true",
        help=(
            "Submit buffered generation plus every optional inference path the "
            "selected model advertises."
        ),
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
