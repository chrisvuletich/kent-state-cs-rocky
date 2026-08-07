from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api-rocky"))

from migrate_telemetry_v2 import TTL_INDEX_NAME, migrate


class FakeInteractions:
    def __init__(self):
        self.rows = [
            {"_id": "legacy", "expires_at": "soon", "state": "terminal"},
            {"_id": "v2", "schema_version": 2, "state": "terminal"},
        ]
        self.indexes = {TTL_INDEX_NAME: {"expireAfterSeconds": 0}}
        self.created_indexes = []

    def count_documents(self, query):
        field = next(iter(query))
        exists = query[field].get("$exists")
        return sum((field in row) == exists for row in self.rows)

    def index_information(self):
        return dict(self.indexes)

    def update_many(self, query, update):
        field = next(iter(query))
        exists = query[field].get("$exists")
        for row in self.rows:
            if (field in row) != exists:
                continue
            for unset_field in update.get("$unset", {}):
                row.pop(unset_field, None)
            row.update(update.get("$set", {}))

    def drop_index(self, name):
        self.indexes.pop(name)

    def create_index(self, keys, **options):
        self.created_indexes.append((keys, options))


class FakeCurrent:
    def update_one(self, _query, _update, upsert=False):
        return SimpleNamespace(modified_count=1, matched_count=1)


class TelemetryMigrationTests(unittest.TestCase):
    def test_dry_run_does_not_mutate(self):
        interactions = FakeInteractions()
        before = [dict(row) for row in interactions.rows]

        result = migrate(interactions, FakeCurrent(), dry_run=True)

        self.assertEqual(result["expiring_documents"], 1)
        self.assertEqual(result["legacy_documents"], 1)
        self.assertTrue(result["ttl_index_present"])
        self.assertEqual(interactions.rows, before)
        self.assertIn(TTL_INDEX_NAME, interactions.indexes)

    def test_migration_removes_expiration_and_marks_legacy_rows(self):
        interactions = FakeInteractions()

        result = migrate(interactions, FakeCurrent())

        legacy = interactions.rows[0]
        self.assertEqual(result["expiring_documents"], 1)
        self.assertNotIn("expires_at", legacy)
        self.assertEqual(legacy["schema_version"], 1)
        self.assertFalse(legacy["content_available"])
        self.assertNotIn(TTL_INDEX_NAME, interactions.indexes)
        self.assertGreaterEqual(len(interactions.created_indexes), 1)


if __name__ == "__main__":
    unittest.main()
