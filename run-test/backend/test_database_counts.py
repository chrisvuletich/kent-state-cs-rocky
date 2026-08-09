from __future__ import annotations

import unittest
from types import SimpleNamespace

from rocky_tools.database_counts import collect_database_counts, render_database_counts


class FakeCollection:
    def __init__(self, count: int):
        self.count = count
        self.queries: list[dict] = []

    def count_documents(self, query: dict) -> int:
        self.queries.append(query)
        return self.count


class DatabaseCountTests(unittest.TestCase):
    def test_counts_are_read_only_and_render_in_stable_order(self):
        collections = SimpleNamespace(
            users=FakeCollection(7),
            whitelist_users=FakeCollection(2),
            courses=FakeCollection(6),
            api_keys=FakeCollection(9),
            api_history=FakeCollection(11),
            telemetry_interactions=FakeCollection(15),
            telemetry_current=FakeCollection(1),
            telemetry_hardware=FakeCollection(20),
            conversations=FakeCollection(4),
            messages=FakeCollection(13),
            responses=FakeCollection(3),
        )

        counts = collect_database_counts(collections)

        self.assertEqual(
            [count.collection for count in counts],
            [
                "users",
                "whitelist_users",
                "courses",
                "api_keys",
                "api_history",
                "telemetry_interactions",
                "telemetry_current",
                "telemetry_hardware",
                "conversations",
                "messages",
                "responses",
            ],
        )
        self.assertEqual(sum(count.documents for count in counts), 91)
        self.assertTrue(
            all(collection.queries == [{}] for collection in vars(collections).values())
        )
        rendered = render_database_counts(counts)
        self.assertEqual(len(rendered), 11)
        self.assertIn("telemetry_interactions", rendered[5])
        self.assertTrue(rendered[5].endswith("15"))


if __name__ == "__main__":
    unittest.main()
