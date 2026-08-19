"""Contract helpers for Rocky's Responses API text stream."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping


SSE_CONTENT_TYPE = "text/event-stream"
SSE_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

TEXT_STREAM_PREFIX = (
    "response.created",
    "response.in_progress",
    "response.output_item.added",
    "response.content_part.added",
)
TEXT_STREAM_DELTA = "response.output_text.delta"
TEXT_STREAM_ERROR = "error"
TEXT_STREAM_SUFFIX = (
    "response.output_text.done",
    "response.content_part.done",
    "response.output_item.done",
    "response.completed",
)
TEXT_STREAM_EVENT_TYPES = frozenset(
    (*TEXT_STREAM_PREFIX, TEXT_STREAM_DELTA, *TEXT_STREAM_SUFFIX, TEXT_STREAM_ERROR)
)


def encode_sse_event(event: Mapping[str, object]) -> str:
    """Encode one typed Responses event as a deterministic SSE frame."""
    event_type = event.get("type") if isinstance(event, Mapping) else None
    if event_type not in TEXT_STREAM_EVENT_TYPES:
        raise ValueError("Unsupported Rocky text stream event type.")
    payload = json.dumps(
        dict(event),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"event: {event_type}\ndata: {payload}\n\n"


def build_text_stream_prefix(response_id, item_id, created_at, model):
    """Build the four fixed events that precede text deltas."""
    in_progress_response = {
        "id": response_id,
        "created_at": created_at,
        "model": model,
        "object": "response",
        "output": [],
        "parallel_tool_calls": False,
        "tool_choice": "none",
        "tools": [],
        "status": "in_progress",
    }
    return [
        {
            "type": "response.created",
            "sequence_number": 0,
            "response": dict(in_progress_response),
        },
        {
            "type": "response.in_progress",
            "sequence_number": 1,
            "response": dict(in_progress_response),
        },
        {
            "type": "response.output_item.added",
            "sequence_number": 2,
            "output_index": 0,
            "item": {
                "id": item_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        },
        {
            "type": "response.content_part.added",
            "sequence_number": 3,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "part": {
                "type": "output_text",
                "text": "",
                "annotations": [],
            },
        },
    ]


def build_text_delta_event(item_id, text, sequence_number):
    """Build one output-text delta event."""
    if not isinstance(text, str) or not text:
        raise ValueError("A Rocky text delta must be a non-empty string.")
    return {
        "type": TEXT_STREAM_DELTA,
        "sequence_number": sequence_number,
        "output_index": 0,
        "item_id": item_id,
        "content_index": 0,
        "delta": text,
        "logprobs": [],
    }


def build_text_stream_suffix(final_response, item_id, output_text, sequence_number):
    """Build the four successful terminal events after all deltas."""
    completed_part = {
        "type": "output_text",
        "text": output_text,
        "annotations": [],
    }
    completed_item = {
        "id": item_id,
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [completed_part],
    }
    response = dict(final_response)
    response["output"] = [completed_item]
    response["output_text"] = output_text
    return [
        {
            "type": "response.output_text.done",
            "sequence_number": sequence_number,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "text": output_text,
            "logprobs": [],
        },
        {
            "type": "response.content_part.done",
            "sequence_number": sequence_number + 1,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "part": completed_part,
        },
        {
            "type": "response.output_item.done",
            "sequence_number": sequence_number + 2,
            "output_index": 0,
            "item": completed_item,
        },
        {
            "type": "response.completed",
            "sequence_number": sequence_number + 3,
            "response": response,
        },
    ]


def build_stream_error_event(message, code, sequence_number):
    """Build an SDK-compatible terminal error event after SSE has begun."""
    if not isinstance(message, str) or not message:
        raise ValueError("A stream error message must be a non-empty string.")
    if code is not None and (not isinstance(code, str) or not code):
        raise ValueError("A stream error code must be null or a non-empty string.")
    return {
        "type": TEXT_STREAM_ERROR,
        "sequence_number": sequence_number,
        "code": code,
        "message": message,
        "param": None,
    }


def validate_text_stream_events(events: Iterable[Mapping[str, object]]) -> None:
    """Validate Rocky's deliberately small successful text-stream subset."""
    stream = [dict(event) for event in events]
    if len(stream) < len(TEXT_STREAM_PREFIX) + len(TEXT_STREAM_SUFFIX) + 1:
        raise ValueError("A text stream requires at least one delta event.")

    event_types = [event.get("type") for event in stream]
    delta_end = len(stream) - len(TEXT_STREAM_SUFFIX)
    if tuple(event_types[: len(TEXT_STREAM_PREFIX)]) != TEXT_STREAM_PREFIX:
        raise ValueError("Text stream prefix events are out of order.")
    if tuple(event_types[delta_end:]) != TEXT_STREAM_SUFFIX:
        raise ValueError("Text stream terminal events are out of order.")
    if any(
        event_type != TEXT_STREAM_DELTA
        for event_type in event_types[len(TEXT_STREAM_PREFIX) : delta_end]
    ):
        raise ValueError("Only output-text deltas may appear during generation.")

    for sequence_number, event in enumerate(stream):
        if event.get("sequence_number") != sequence_number:
            raise ValueError("Text stream sequence numbers must be contiguous from zero.")

    created_response = _object(stream[0].get("response"), "response.created.response")
    progress_response = _object(stream[1].get("response"), "response.in_progress.response")
    completed_response = _object(stream[-1].get("response"), "response.completed.response")
    response_id = _nonempty_string(created_response.get("id"), "response id")
    if any(
        response.get("id") != response_id
        for response in (progress_response, completed_response)
    ):
        raise ValueError("Every lifecycle event must use the same response id.")
    if created_response.get("status") != "in_progress":
        raise ValueError("The created response must be in progress.")
    if progress_response.get("status") != "in_progress":
        raise ValueError("The progress response must be in progress.")
    if completed_response.get("status") != "completed":
        raise ValueError("The completed response must have completed status.")

    added_item = _object(stream[2].get("item"), "response.output_item.added.item")
    item_id = _nonempty_string(added_item.get("id"), "output item id")
    if added_item.get("status") != "in_progress" or added_item.get("content") != []:
        raise ValueError("The added message item must begin empty and in progress.")

    added_part = _object(stream[3].get("part"), "response.content_part.added.part")
    if added_part.get("type") != "output_text" or added_part.get("text") != "":
        raise ValueError("The added text part must begin empty.")

    delta_events = stream[len(TEXT_STREAM_PREFIX) : delta_end]
    deltas = []
    for event in delta_events:
        delta = _nonempty_string(event.get("delta"), "text delta")
        if event.get("logprobs") != []:
            raise ValueError("Rocky text deltas must declare an empty logprobs list.")
        deltas.append(delta)
    output_text = "".join(deltas)

    text_done = stream[delta_end]
    content_done = stream[delta_end + 1]
    item_done = stream[delta_end + 2]
    if text_done.get("text") != output_text or text_done.get("logprobs") != []:
        raise ValueError("The text-done event must contain the accumulated output.")
    done_part = _object(content_done.get("part"), "response.content_part.done.part")
    if done_part.get("text") != output_text:
        raise ValueError("The completed content part must contain the accumulated output.")
    completed_item = _object(item_done.get("item"), "response.output_item.done.item")
    if completed_item.get("id") != item_id or completed_item.get("status") != "completed":
        raise ValueError("The completed item must match the added item.")
    completed_content = completed_item.get("content")
    if not isinstance(completed_content, list) or completed_content != [done_part]:
        raise ValueError("The completed item must contain the completed text part.")
    if completed_response.get("output") != [completed_item]:
        raise ValueError("The final response must contain the completed item.")

    indexed_events = stream[2:-1]
    for event in indexed_events:
        if event.get("output_index") != 0:
            raise ValueError("Rocky's text-only stream uses output index zero.")
        if "item_id" in event and event.get("item_id") != item_id:
            raise ValueError("Every content event must use the same item id.")
        if "content_index" in event and event.get("content_index") != 0:
            raise ValueError("Rocky's text-only stream uses content index zero.")


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object.")
    return dict(value)


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string.")
    return value
