import json
import requests
from urllib3.exceptions import ReadTimeoutError

from app.config import env_float, env_http_url


OLLAMA_BASE_URL = env_http_url("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT_SECONDS = env_float(
    "ROCKY_OLLAMA_TIMEOUT_SECONDS", 150, minimum=0, allow_minimum=False
)
OLLAMA_READY_TIMEOUT_SECONDS = env_float(
    "ROCKY_OLLAMA_READY_TIMEOUT_SECONDS", 2, minimum=0, allow_minimum=False
)

# Ollama metadata fields that contain int
_PROVIDER_INTEGER_FIELDS = (
    "prompt_eval_count",
    "eval_count",
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
)
# Max string length for Metadata fields
_MAX_PROVIDER_STRING_LENGTH = 256
_STREAM_CHUNK_BYTES = 16 * 1024
_MAX_STREAM_LINE_BYTES = 1024 * 1024
_MAX_STREAM_BODY_BYTES = 16 * 1024 * 1024


class OllamaCallError(Exception):
    """A sanitized Ollama failure with safe request telemetry."""

    def __init__(self, kind, telemetry):
        super().__init__(kind)
        self.kind = kind
        self.telemetry = telemetry


def _request_error_kind(error):
    wrapped_read_timeout = any(
        isinstance(detail, ReadTimeoutError)
        for detail in getattr(error, "args", ())
    )
    return (
        "timeout"
        if isinstance(error, requests.Timeout) or wrapped_read_timeout
        else "network_error"
    )


def check_ollama_readiness(model, *, require_vision=False):
    if require_vision:
        # /api/show both proves the configured model exists and exposes the
        # capability needed for image input, avoiding two serial readiness calls.
        try:
            response = requests.post(
                OLLAMA_BASE_URL + "/api/show",
                json={"model": model},
                timeout=OLLAMA_READY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            details = response.json()
        except (requests.RequestException, ValueError):
            return False
        capabilities = (
            details.get("capabilities")
            if isinstance(details, dict)
            else None
        )
        return isinstance(capabilities, list) and "vision" in capabilities

    try:
        response = requests.get(
            OLLAMA_BASE_URL + "/api/tags",
            timeout=OLLAMA_READY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return False

    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return False
    available_names = {
        candidate
        for item in models
        if isinstance(item, dict)
        for candidate in (item.get("name"), item.get("model"))
        if isinstance(candidate, str)
    }
    if model not in available_names:
        return False
    return True


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


def _build_chat_request(model, messages, options, think, *, stream):
    ollama_payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
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
    return request_body, telemetry


def _close_response(response):
    try:
        response.close()
    except (AttributeError, requests.RequestException):
        pass


def _iter_bounded_ndjson_lines(response, telemetry):
    buffer = bytearray()

    try:
        chunks = response.iter_content(chunk_size=_STREAM_CHUNK_BYTES)
        for chunk in chunks:
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise OllamaCallError("invalid_response", telemetry)

            telemetry["model_output_bytes"] += len(chunk)
            if telemetry["model_output_bytes"] > _MAX_STREAM_BODY_BYTES:
                raise OllamaCallError("invalid_response", telemetry)

            buffer.extend(chunk)
            while True:
                newline_index = buffer.find(b"\n")
                if newline_index < 0:
                    if len(buffer) > _MAX_STREAM_LINE_BYTES:
                        raise OllamaCallError("invalid_response", telemetry)
                    break

                line = bytes(buffer[:newline_index])
                del buffer[:newline_index + 1]
                if line.endswith(b"\r"):
                    line = line[:-1]
                if len(line) > _MAX_STREAM_LINE_BYTES:
                    raise OllamaCallError("invalid_response", telemetry)
                if line.strip():
                    yield line
    except requests.RequestException as error:
        raise OllamaCallError(_request_error_kind(error), telemetry) from error

    if buffer:
        if len(buffer) > _MAX_STREAM_LINE_BYTES:
            raise OllamaCallError("invalid_response", telemetry)
        line = bytes(buffer[:-1] if buffer.endswith(b"\r") else buffer)
        if line.strip():
            yield line


class OllamaChatStream:
    """Single-use, bounded iterator over Ollama chat text deltas."""

    def __init__(self, response, telemetry):
        self._response = response
        self._telemetry = telemetry
        self._iterated = False
        self._closed = False
        self._thinking_present = False
        self._completed = False
        self._content_present = False

    @property
    def telemetry(self):
        return self._telemetry

    @property
    def thinking_present(self):
        return self._thinking_present

    def close(self):
        if not self._closed:
            self._closed = True
            _close_response(self._response)

    def __iter__(self):
        if self._iterated:
            raise RuntimeError("An Ollama chat stream can only be consumed once.")
        self._iterated = True

        try:
            for raw_line in _iter_bounded_ndjson_lines(
                self._response,
                self._telemetry,
            ):
                try:
                    data = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise OllamaCallError(
                        "invalid_response",
                        self._telemetry,
                    ) from error

                if not isinstance(data, dict) or "error" in data:
                    raise OllamaCallError("invalid_response", self._telemetry)

                done = data.get("done")
                message = data.get("message")
                if not isinstance(done, bool) or not isinstance(message, dict):
                    raise OllamaCallError("invalid_response", self._telemetry)

                content = message.get("content")
                thinking = message.get("thinking")
                if not isinstance(content, str) or (
                    thinking is not None and not isinstance(thinking, str)
                ):
                    raise OllamaCallError("invalid_response", self._telemetry)

                if thinking:
                    self._thinking_present = True
                if content:
                    self._content_present = True
                    yield content

                if done:
                    self._telemetry["provider"] = _extract_provider_telemetry(data)
                    self._completed = True
                    break

            if not self._completed or not self._content_present:
                raise OllamaCallError("invalid_response", self._telemetry)
        finally:
            self.close()


def call_ollama_chat(model, messages, options=None, think=None):
    url = OLLAMA_BASE_URL + "/api/chat"
    request_body, telemetry = _build_chat_request(
        model,
        messages,
        options,
        think,
        stream=False,
    )

    try:
        response = requests.post(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise OllamaCallError(_request_error_kind(error), telemetry) from error

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


def call_ollama_chat_stream(model, messages, options=None, think=None):
    """Open an Ollama chat stream without consuming its NDJSON body."""
    url = OLLAMA_BASE_URL + "/api/chat"
    request_body, telemetry = _build_chat_request(
        model,
        messages,
        options,
        think,
        stream=True,
    )

    try:
        response = requests.post(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise OllamaCallError(_request_error_kind(error), telemetry) from error

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        status_code = getattr(response, "status_code", None)
        _close_response(response)
        kind = "timeout" if status_code in (408, 504) else "http_error"
        raise OllamaCallError(kind, telemetry) from error

    return OllamaChatStream(response, telemetry)
