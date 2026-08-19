"""Bounded client for Granite's provider-neutral NDJSON generation stream."""

from __future__ import annotations

import json
from collections.abc import Mapping

import requests
from urllib3.exceptions import ReadTimeoutError


STREAM_CONTENT_TYPE = "application/x-ndjson"
_STREAM_CHUNK_BYTES = 16 * 1024
_MAX_STREAM_LINE_BYTES = 1024 * 1024
_MAX_STREAM_BODY_BYTES = 16 * 1024 * 1024
_MAX_ERROR_MESSAGE_LENGTH = 512


class GraniteStreamError(Exception):
    """A sanitized Granite stream failure safe for Rocky error mapping."""

    def __init__(self, kind, telemetry=None, message=None):
        super().__init__(kind)
        self.kind = kind
        self.telemetry = telemetry if isinstance(telemetry, dict) else {}
        self.message = (
            message.strip()[:_MAX_ERROR_MESSAGE_LENGTH]
            if isinstance(message, str) and message.strip()
            else None
        )


def _request_error_kind(error):
    wrapped_read_timeout = any(
        isinstance(detail, ReadTimeoutError)
        for detail in getattr(error, "args", ())
    )
    return (
        "timeout"
        if isinstance(error, requests.Timeout) or wrapped_read_timeout
        else "network"
    )


def _close_response(response):
    try:
        response.close()
    except (AttributeError, requests.RequestException):
        pass


def _iter_bounded_lines(response, byte_counter):
    buffer = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=_STREAM_CHUNK_BYTES):
            if not chunk:
                continue
            if not isinstance(chunk, bytes):
                raise GraniteStreamError("bad_response")

            byte_counter[0] += len(chunk)
            if byte_counter[0] > _MAX_STREAM_BODY_BYTES:
                raise GraniteStreamError("bad_response")
            buffer.extend(chunk)

            while True:
                newline_index = buffer.find(b"\n")
                if newline_index < 0:
                    if len(buffer) > _MAX_STREAM_LINE_BYTES:
                        raise GraniteStreamError("bad_response")
                    break
                line = bytes(buffer[:newline_index])
                del buffer[:newline_index + 1]
                if line.endswith(b"\r"):
                    line = line[:-1]
                if len(line) > _MAX_STREAM_LINE_BYTES:
                    raise GraniteStreamError("bad_response")
                if line.strip():
                    yield line
    except requests.RequestException as error:
        raise GraniteStreamError(_request_error_kind(error)) from error

    if buffer:
        if len(buffer) > _MAX_STREAM_LINE_BYTES:
            raise GraniteStreamError("bad_response")
        line = bytes(buffer[:-1] if buffer.endswith(b"\r") else buffer)
        if line.strip():
            yield line


def _decode_event(raw_line):
    try:
        event = json.loads(raw_line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GraniteStreamError("bad_response") from error
    if not isinstance(event, dict):
        raise GraniteStreamError("bad_response")
    return event


def _validate_event(event):
    event_type = event.get("type")
    if event_type == "started":
        if set(event) != {"type", "model"}:
            raise GraniteStreamError("bad_response")
        model = event.get("model")
        if not isinstance(model, str) or not model.strip():
            raise GraniteStreamError("bad_response")
    elif event_type == "delta":
        if set(event) != {"type", "text"}:
            raise GraniteStreamError("bad_response")
        text = event.get("text")
        if not isinstance(text, str) or not text:
            raise GraniteStreamError("bad_response")
    elif event_type == "completed":
        if set(event) != {"type", "telemetry", "metadata"}:
            raise GraniteStreamError("bad_response")
        if not isinstance(event.get("telemetry"), Mapping):
            raise GraniteStreamError("bad_response")
        if not isinstance(event.get("metadata"), Mapping):
            raise GraniteStreamError("bad_response")
    elif event_type == "error":
        if set(event) != {"type", "error"}:
            raise GraniteStreamError("bad_response")
        error = event.get("error")
        if not isinstance(error, Mapping) or set(error) != {"type", "message"}:
            raise GraniteStreamError("bad_response")
        if not isinstance(error.get("type"), str) or not error.get("type"):
            raise GraniteStreamError("bad_response")
        if not isinstance(error.get("message"), str) or not error.get("message"):
            raise GraniteStreamError("bad_response")
    elif event_type == "cancelled":
        if set(event) != {"type"}:
            raise GraniteStreamError("bad_response")
    else:
        raise GraniteStreamError("bad_response")
    return event


class GraniteEventStream:
    """Single-use iterator over validated Granite events after `started`."""

    def __init__(self, response, line_iterator, byte_counter, model):
        self._response = response
        self._line_iterator = line_iterator
        self._byte_counter = byte_counter
        self.model = model
        self._iterated = False
        self._closed = False

    @property
    def received_bytes(self):
        return self._byte_counter[0]

    def close(self):
        if not self._closed:
            self._closed = True
            _close_response(self._response)

    def __iter__(self):
        if self._iterated:
            raise RuntimeError("A Granite event stream can only be consumed once.")
        self._iterated = True
        saw_delta = False
        terminal_event = None

        try:
            for raw_line in self._line_iterator:
                event = _validate_event(_decode_event(raw_line))
                event_type = event["type"]
                if terminal_event is not None or event_type == "started":
                    raise GraniteStreamError("bad_response")
                if event_type == "delta":
                    saw_delta = True
                    yield event
                    continue

                terminal_event = event

            if terminal_event is None:
                raise GraniteStreamError("bad_response")
            if terminal_event["type"] == "completed" and not saw_delta:
                raise GraniteStreamError("bad_response")
            yield terminal_event
        finally:
            self.close()


def _response_content_type(response):
    headers = getattr(response, "headers", {})
    value = headers.get("Content-Type", "") if isinstance(headers, Mapping) else ""
    return value.split(";", 1)[0].strip().lower()


def _read_error_payload(response, byte_counter):
    body = bytearray()
    try:
        for line in _iter_bounded_lines(response, byte_counter):
            if body:
                body.extend(b"\n")
            body.extend(line)
            if len(body) > _MAX_STREAM_LINE_BYTES:
                return {}
    except GraniteStreamError:
        return {}
    try:
        payload = json.loads(bytes(body)) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def open_granite_stream(url, payload, headers, timeout, expected_model):
    """Open Granite and validate its status, media type, and first event."""
    request_payload = dict(payload)
    request_payload["stream"] = True
    try:
        response = requests.post(
            url,
            json=request_payload,
            headers=dict(headers),
            stream=True,
            timeout=timeout,
        )
    except requests.RequestException as error:
        raise GraniteStreamError(_request_error_kind(error)) from error

    byte_counter = [0]
    status_code = getattr(response, "status_code", 500)
    if not 200 <= status_code < 300:
        try:
            data = _read_error_payload(response, byte_counter)
            granite_error = data.get("error")
            granite_error_type = (
                granite_error.get("type")
                if isinstance(granite_error, dict)
                else None
            )
            telemetry = data.get("telemetry")
            if status_code == 400 or granite_error_type == "bad_request":
                kind = "bad_request"
            elif status_code == 503 or granite_error_type == "model_busy":
                kind = "busy"
            elif status_code == 504 or granite_error_type == "model_timeout":
                kind = "timeout"
            else:
                kind = "network"
            safe_message = (
                granite_error.get("message")
                if kind == "bad_request" and isinstance(granite_error, dict)
                else None
            )
            raise GraniteStreamError(kind, telemetry, safe_message)
        finally:
            _close_response(response)

    if _response_content_type(response) != STREAM_CONTENT_TYPE:
        _close_response(response)
        raise GraniteStreamError("bad_response")

    line_iterator = iter(_iter_bounded_lines(response, byte_counter))
    try:
        first_event = _validate_event(_decode_event(next(line_iterator)))
    except StopIteration as error:
        _close_response(response)
        raise GraniteStreamError("bad_response") from error
    except GraniteStreamError:
        _close_response(response)
        raise

    if first_event.get("type") != "started" or first_event.get("model") != expected_model:
        _close_response(response)
        raise GraniteStreamError("bad_response")

    return GraniteEventStream(
        response,
        line_iterator,
        byte_counter,
        first_event["model"],
    )
