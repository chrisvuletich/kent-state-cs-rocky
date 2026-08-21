from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from test_support import BackendTestCase, main
from rocky_tools.retention import RequestRetention, parse_before_date


class RequestRetentionTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        main.telemetry_interactions.delete_many({})
        main.api_history.delete_many({})
        self.cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        main.telemetry_interactions.insert_many([
            {"_id": "old", "received_at": self.cutoff - timedelta(days=1)},
            {"_id": "new", "received_at": self.cutoff + timedelta(days=1)},
        ])

    def retention(self):
        return RequestRetention(
            main.telemetry_interactions,
            main.api_history,
        )

    def test_dry_run_reports_without_deleting_or_auditing(self):
        result = self.retention().run(self.cutoff)
        self.assertEqual(result.matched, 1)
        self.assertEqual(result.deleted, 0)
        self.assertFalse(result.applied)
        self.assertEqual(len(list(main.telemetry_interactions.find({}))), 2)
        self.assertEqual(len(list(main.api_history.find({}))), 0)

    def test_apply_deletes_only_matching_rows_and_records_audit_event(self):
        result = self.retention().run(self.cutoff, apply=True)
        self.assertEqual(result.deleted, 1)
        self.assertEqual(
            [row["_id"] for row in main.telemetry_interactions.find({})],
            ["new"],
        )
        audit = main.api_history.find_one({"event_type": "telemetry-purge"})
        self.assertIsNotNone(audit)
        self.assertEqual(audit["meta"]["matched"], 1)
        self.assertEqual(audit["meta"]["deleted"], 1)

    def test_cutoff_requires_valid_nonfuture_calendar_date(self):
        self.assertEqual(
            parse_before_date("2025-08-01"),
            datetime(2025, 8, 1, tzinfo=timezone.utc),
        )
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            parse_before_date("August 1")
        future = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
        with self.assertRaisesRegex(ValueError, "future"):
            parse_before_date(future)


if __name__ == "__main__":
    unittest.main()
