from __future__ import annotations

import base64
import copy
import json
import sys
import unittest
from pathlib import Path

from openai.types.responses import (
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseErrorEvent,
    ResponseInProgressEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
)
from openai.types.responses.response_input_image_param import ResponseInputImageParam
from pydantic import TypeAdapter


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
FIXTURE_PATH = ROOT / "run-test" / "fixtures" / "responses_text_stream.sse"
IMAGE_FIXTURE_PATH = ROOT / "run-test" / "fixtures" / "responses_image_input.json"
sys.path.insert(0, str(API_ROCKY_DIR))
try:
    from response_stream_contract import (
        build_stream_error_event,
        encode_sse_event,
        validate_text_stream_events,
    )
finally:
    sys.path.remove(str(API_ROCKY_DIR))


SDK_EVENT_TYPES = {
    "response.created": ResponseCreatedEvent,
    "response.in_progress": ResponseInProgressEvent,
    "response.output_item.added": ResponseOutputItemAddedEvent,
    "response.content_part.added": ResponseContentPartAddedEvent,
    "response.output_text.delta": ResponseTextDeltaEvent,
    "response.output_text.done": ResponseTextDoneEvent,
    "response.content_part.done": ResponseContentPartDoneEvent,
    "response.output_item.done": ResponseOutputItemDoneEvent,
    "response.completed": ResponseCompletedEvent,
}


def load_fixture_events() -> list[dict[str, object]]:
    events = []
    for frame in FIXTURE_PATH.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = frame.splitlines()
        if len(lines) != 2 or not lines[0].startswith("event: "):
            raise AssertionError("Invalid SSE fixture frame.")
        if not lines[1].startswith("data: "):
            raise AssertionError("Invalid SSE fixture data line.")
        event_type = lines[0].removeprefix("event: ")
        event = json.loads(lines[1].removeprefix("data: "))
        if event.get("type") != event_type:
            raise AssertionError("SSE event and payload types differ.")
        events.append(event)
    return events


class ResponseStreamContractTests(unittest.TestCase):
    def test_golden_stream_satisfies_rocky_and_current_openai_sdk_contracts(self):
        events = load_fixture_events()

        validate_text_stream_events(events)
        parsed = [SDK_EVENT_TYPES[event["type"]].model_validate(event) for event in events]

        self.assertEqual(parsed[0].type, "response.created")
        self.assertEqual(parsed[-1].response.output_text, "Hello Rocky!")
        self.assertEqual(
            "".join(
                event.delta
                for event in parsed
                if isinstance(event, ResponseTextDeltaEvent)
            ),
            "Hello Rocky!",
        )

    def test_encoder_reproduces_every_golden_sse_frame(self):
        events = load_fixture_events()
        encoded = "".join(encode_sse_event(event) for event in events)

        self.assertEqual(encoded, FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_contract_rejects_noncontiguous_sequence_numbers(self):
        events = load_fixture_events()
        events[4]["sequence_number"] = 99

        with self.assertRaisesRegex(ValueError, "sequence numbers"):
            validate_text_stream_events(events)

    def test_contract_rejects_final_text_that_differs_from_deltas(self):
        events = load_fixture_events()
        events[-4]["text"] = "different"

        with self.assertRaisesRegex(ValueError, "text-done"):
            validate_text_stream_events(events)

    def test_contract_rejects_mismatched_response_and_item_ids(self):
        response_mismatch = load_fixture_events()
        response_mismatch[-1]["response"]["id"] = "resp_other"
        with self.assertRaisesRegex(ValueError, "same response id"):
            validate_text_stream_events(response_mismatch)

        item_mismatch = copy.deepcopy(load_fixture_events())
        item_mismatch[4]["item_id"] = "msg_other"
        with self.assertRaisesRegex(ValueError, "same item id"):
            validate_text_stream_events(item_mismatch)

    def test_encoder_rejects_events_outside_the_text_stream_subset(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            encode_sse_event({"type": "response.function_call_arguments.delta"})

    def test_terminal_error_event_is_sdk_compatible(self):
        event = build_stream_error_event(
            "Model request timed out.",
            "model_timeout",
            7,
        )

        parsed = ResponseErrorEvent.model_validate(event)

        self.assertEqual(parsed.type, "error")
        self.assertEqual(parsed.code, "model_timeout")
        self.assertEqual(
            encode_sse_event(event),
            "event: error\n"
            "data: {\"type\":\"error\",\"sequence_number\":7,"
            "\"code\":\"model_timeout\",\"message\":"
            "\"Model request timed out.\",\"param\":null}\n\n",
        )

    def test_image_fixture_uses_the_planned_openai_responses_shape(self):
        request_body = json.loads(IMAGE_FIXTURE_PATH.read_text(encoding="utf-8"))
        content = request_body["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_text")

        image = TypeAdapter(ResponseInputImageParam).validate_python(content[1])
        self.assertEqual(image["type"], "input_image")
        self.assertEqual(image["detail"], "auto")
        prefix, encoded = image["image_url"].split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        self.assertEqual(
            base64.b64decode(encoded, validate=True)[:8],
            b"\x89PNG\r\n\x1a\n",
        )


if __name__ == "__main__":
    unittest.main()
