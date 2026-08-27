"""Provider-neutral NDJSON contract for Rocky's internal generation stream."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping


STREAM_CONTENT_TYPE = "application/x-ndjson"
STREAM_EVENT_TYPES = frozenset({"started", "delta", "completed", "error", "cancelled"})
TERMINAL_EVENT_TYPES = frozenset({"completed", "error", "cancelled"})


def validate_stream_event(event: Mapping[str, object]) -> dict[str, object]:
    """Return a normalized copy when an internal stream event is well formed."""
    if not isinstance(event, Mapping):
        raise ValueError("A Granite stream event must be an object.")
    normalized = dict(event)
    event_type = normalized.get("type")
    if event_type not in STREAM_EVENT_TYPES:
        raise ValueError("Unsupported Granite stream event type.")

    expected_keys: set[str]
    if event_type == "started":
        _nonempty_string(normalized.get("model"), "started.model")
        expected_keys = {"type", "model"}
    elif event_type == "delta":
        _nonempty_string(normalized.get("text"), "delta.text")
        expected_keys = {"type", "text"}
    elif event_type == "completed":
        if not isinstance(normalized.get("telemetry"), Mapping):
            raise ValueError("completed.telemetry must be an object.")
        if not isinstance(normalized.get("metadata"), Mapping):
            raise ValueError("completed.metadata must be an object.")
        expected_keys = {"type", "telemetry", "metadata"}
    elif event_type == "error":
        error = normalized.get("error")
        if not isinstance(error, Mapping):
            raise ValueError("error.error must be an object.")
        if set(error) != {"type", "message"}:
            raise ValueError("error.error contains unsupported fields.")
        _nonempty_string(error.get("type"), "error.error.type")
        _nonempty_string(error.get("message"), "error.error.message")
        expected_keys = {"type", "error"}
        if "telemetry" in normalized:
            if not isinstance(normalized.get("telemetry"), Mapping):
                raise ValueError("error.telemetry must be an object.")
            expected_keys.add("telemetry")
    else:
        expected_keys = {"type"}
        if "telemetry" in normalized:
            if not isinstance(normalized.get("telemetry"), Mapping):
                raise ValueError("cancelled.telemetry must be an object.")
            expected_keys.add("telemetry")

    if set(normalized) != expected_keys:
        raise ValueError(f"{event_type} event contains unsupported fields.")
    return normalized


def encode_stream_event(event: Mapping[str, object]) -> str:
    """Encode one validated internal event as a single NDJSON line."""
    normalized = validate_stream_event(event)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def validate_stream(events: Iterable[Mapping[str, object]]) -> None:
    """Validate ordering for one complete internal generation stream."""
    stream = [validate_stream_event(event) for event in events]
    if len(stream) == 1 and stream[0]["type"] in {"error", "cancelled"}:
        return
    if len(stream) < 2 or stream[0]["type"] != "started":
        raise ValueError("A Granite stream must begin with started.")
    if stream[-1]["type"] not in TERMINAL_EVENT_TYPES:
        raise ValueError("A Granite stream must end with one terminal event.")
    if any(event["type"] in TERMINAL_EVENT_TYPES for event in stream[:-1]):
        raise ValueError("A Granite stream cannot continue after a terminal event.")
    if any(event["type"] not in {"delta"} for event in stream[1:-1]):
        raise ValueError("Only delta events may appear between start and termination.")
    if stream[-1]["type"] == "completed" and not any(
        event["type"] == "delta" for event in stream
    ):
        raise ValueError("A completed Granite stream requires at least one text delta.")


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string.")
    return value
