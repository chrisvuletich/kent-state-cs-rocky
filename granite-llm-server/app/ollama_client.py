import json
import os
import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("ROCKY_OLLAMA_TIMEOUT_SECONDS", "150"))

# Ollama metadata fields that contain int
_PROVIDER_INTEGER_FIELDS = (
    "prompt_eval_count",
    "eval_count",
)
# Max string length for Metadata fields
_MAX_PROVIDER_STRING_LENGTH = 256


class OllamaCallError(Exception):
    """A sanitized Ollama failure with safe request telemetry."""

    def __init__(self, kind, telemetry):
        super().__init__(kind)
        self.kind = kind
        self.telemetry = telemetry


def _extract_provider_telemetry(data):
    if not isinstance(data, dict):
        return {}

    provider = {}

    for source, target in (("model", "actual_model"), ("done_reason", "stop_reason"), ("stop_reason", "stop_reason")):
        if target in provider:
            continue

        value = data.get(source)

        if isinstance(value, str):
            value = value.strip()
            if value and len(value) <= _MAX_PROVIDER_STRING_LENGTH:
                provider[target] = value

    for field in _PROVIDER_INTEGER_FIELDS:
        value = data.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            provider[field] = value

    return provider


def call_ollama_chat(model, messages, options=None, think=None):
    url = OLLAMA_BASE_URL + "/api/chat"

    ollama_payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    if options:
        ollama_payload["options"] = options

    if think is not None:
        ollama_payload["think"] = think

    request_body = json.dumps(
        ollama_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    telemetry = {
        "model_input_bytes": len(request_body),
        "model_output_bytes": 0,
        "provider": {},
    }

    try:
        response = requests.post(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        kind = "timeout" if isinstance(error, requests.Timeout) else "network_error"
        raise OllamaCallError(kind, telemetry) from error

    response_body = response.content
    if not isinstance(response_body, bytes):
        response_body = b""
    telemetry["model_output_bytes"] = len(response_body)

    try:
        data = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    telemetry["provider"] = _extract_provider_telemetry(data)

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        kind = "timeout" if response.status_code in (408, 504) else "http_error"
        raise OllamaCallError(kind, telemetry) from error

    message = data.get("message") if isinstance(data, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise OllamaCallError("invalid_response", telemetry)

    return {
        "content": content,
        "thinking_present": bool(message.get("thinking")),
        "telemetry": telemetry,
    }
