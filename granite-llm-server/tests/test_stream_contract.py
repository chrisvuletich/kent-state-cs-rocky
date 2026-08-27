from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.stream_contract import encode_stream_event, validate_stream, validate_stream_event


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "run-test" / "fixtures" / "granite_text_stream.ndjson"


def load_fixture_events() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line
    ]


class GraniteStreamContractTests(unittest.TestCase):
    def test_golden_internal_stream_is_valid_and_deterministically_encoded(self):
        events = load_fixture_events()

        validate_stream(events)
        encoded = "".join(encode_stream_event(event) for event in events)

        self.assertEqual(encoded, FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_error_and_cancelled_are_valid_terminal_events(self):
        validate_stream([{
            "type": "error",
            "error": {"type": "model_busy", "message": "Model busy."},
        }])
        validate_stream([{"type": "cancelled"}])
        validate_stream([{
            "type": "error",
            "error": {"type": "model_busy", "message": "Model busy."},
            "telemetry": {"queue": {"status": "timed_out"}},
        }])
        validate_stream([{
            "type": "cancelled",
            "telemetry": {"queue": {"status": "cancelled"}},
        }])
        validate_stream([
            {"type": "started", "model": "gemma4:latest"},
            {
                "type": "error",
                "error": {"type": "model_timeout", "message": "Timed out."},
            },
        ])
        validate_stream([
            {"type": "started", "model": "gemma4:latest"},
            {"type": "delta", "text": "Partial"},
            {"type": "cancelled"},
        ])

    def test_event_validation_is_strict(self):
        invalid_events = (
            {"type": "unknown"},
            {"type": "delta", "text": ""},
            {"type": "delta", "text": "ok", "provider": "ollama"},
            {"type": "completed", "telemetry": {}, "metadata": [],},
            {"type": "error", "error": {"type": "model_error"}},
            {
                "type": "error",
                "error": {"type": "model_error", "message": "Failed."},
                "telemetry": [],
            },
            {"type": "cancelled", "telemetry": []},
        )
        for event in invalid_events:
            with self.subTest(event=event), self.assertRaises(ValueError):
                validate_stream_event(event)

    def test_stream_validation_rejects_invalid_ordering(self):
        invalid_streams = (
            [],
            [{"type": "delta", "text": "missing start"}],
            [{"type": "delta", "text": "missing start"}, {"type": "cancelled"}],
            [{"type": "started", "model": "model"}, {"type": "delta", "text": "open"}],
            [
                {"type": "started", "model": "model"},
                {"type": "cancelled"},
                {"type": "delta", "text": "too late"},
            ],
            [
                {"type": "started", "model": "model"},
                {"type": "completed", "telemetry": {}, "metadata": {}},
            ],
        )
        for stream in invalid_streams:
            with self.subTest(stream=stream), self.assertRaises(ValueError):
                validate_stream(stream)


if __name__ == "__main__":
    unittest.main()
