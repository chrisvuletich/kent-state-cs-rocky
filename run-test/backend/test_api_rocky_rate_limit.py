from __future__ import annotations

import logging
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mongita import MongitaClientMemory
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
sys.path.insert(0, str(API_ROCKY_DIR))

from rate_limit import (  # noqa: E402
    FixedWindowRateLimiter,
    MONGITA_CLEANUP_INTERVAL_SECONDS,
    RATE_LIMIT_COUNTER_RETENTION_SECONDS,
    RATE_LIMIT_TTL_INDEX_NAME,
    RATE_LIMIT_WINDOW_SECONDS,
    RateLimitStoreUnavailable,
    ensure_rate_limit_ttl_index,
)


class MutableClock:
    def __init__(self, value: float):
        self.value = value

    def __call__(self) -> float:
        return self.value


class RecordingCollection:
    def __init__(self, delegate, *, cleanup_fails=False):
        self.delegate = delegate
        self.cleanup_fails = cleanup_fails
        self.cleanup_calls = 0

    def insert_one(self, document):
        return self.delegate.insert_one(document)

    def update_one(self, query, update):
        return self.delegate.update_one(query, update)

    def find_one(self, query):
        return self.delegate.find_one(query)

    def delete_many(self, query):
        self.cleanup_calls += 1
        if self.cleanup_fails:
            raise RuntimeError("synthetic cleanup failure")
        return self.delegate.delete_many(query)


class FailingCollection:
    def __init__(self, failure_stage):
        self.failure_stage = failure_stage

    def insert_one(self, _document):
        if self.failure_stage == "insert":
            raise RuntimeError("synthetic insert failure")

    def update_one(self, _query, _update):
        if self.failure_stage == "update":
            raise RuntimeError("synthetic update failure")
        return type("UpdateResult", (), {"modified_count": 1})()

    def find_one(self, _query):
        if self.failure_stage == "read":
            raise RuntimeError("synthetic read failure")
        return {"count": 1}


class InvalidUpdateCollection(FailingCollection):
    def __init__(self):
        super().__init__(failure_stage=None)

    def update_one(self, _query, _update):
        return object()


class PyMongoDuplicateInsertCollection(FailingCollection):
    def __init__(self):
        super().__init__(failure_stage=None)

    def insert_one(self, _document):
        raise PyMongoDuplicateKeyError("synthetic duplicate")


class IndexRecordingCollection:
    def __init__(self):
        self.calls = []

    def create_index(self, keys, **options):
        self.calls.append((keys, options))
        return "synthetic-index"


class FixedWindowRateLimiterTests(unittest.TestCase):
    def setUp(self):
        database = MongitaClientMemory()[uuid4().hex]
        self.collection = database["rate_limit_windows"]
        self.clock = MutableClock(120.0)
        self.limiter = FixedWindowRateLimiter(
            self.collection,
            clock=self.clock,
        )

    def consume(self, *, key_id="akid_student_one", operation="responses.create", limit=3):
        return self.limiter.consume(
            key_id=key_id,
            operation=operation,
            limit=limit,
        )

    def test_first_n_requests_are_allowed_and_the_next_is_limited(self):
        decisions = [self.consume() for _ in range(4)]

        self.assertEqual([decision.allowed for decision in decisions], [True, True, True, False])
        self.assertTrue(all(decision.limit == 3 for decision in decisions))
        self.assertEqual(
            [decision.remaining_requests for decision in decisions],
            [2, 1, 0, 0],
        )
        self.assertTrue(all(decision.retry_after_seconds == 60 for decision in decisions))

        documents = list(self.collection.find({}))
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["count"], 3)
        self.assertEqual(documents[0]["key_id"], "akid_student_one")
        self.assertEqual(documents[0]["operation"], "responses.create")
        self.assertEqual(
            (
                documents[0]["expires_at"] - documents[0]["window_ends_at"]
            ).total_seconds(),
            RATE_LIMIT_COUNTER_RETENTION_SECONDS,
        )
        serialized = repr(documents[0]).lower()
        self.assertNotIn("authorization", serialized)
        self.assertNotIn("api-key", serialized)
        self.assertNotIn("hash", serialized)

    def test_keys_and_operations_use_independent_buckets(self):
        first = self.consume(limit=1)
        other_key = self.consume(key_id="akid_student_two", limit=1)
        other_operation = self.consume(operation="models.list", limit=1)
        repeated = self.consume(limit=1)

        self.assertTrue(first.allowed)
        self.assertTrue(other_key.allowed)
        self.assertTrue(other_operation.allowed)
        self.assertFalse(repeated.allowed)
        self.assertEqual(len(list(self.collection.find({}))), 3)

    def test_new_minute_creates_a_fresh_bucket(self):
        self.assertTrue(self.consume(limit=1).allowed)
        self.assertFalse(self.consume(limit=1).allowed)

        self.clock.value = 180.0
        reset = self.consume(limit=1)

        self.assertTrue(reset.allowed)
        self.assertEqual(reset.remaining_requests, 0)
        self.assertEqual(reset.retry_after_seconds, RATE_LIMIT_WINDOW_SECONDS)
        self.assertEqual(len(list(self.collection.find({}))), 2)

    def test_lowered_limit_treats_an_existing_higher_count_as_exhausted(self):
        for _ in range(5):
            self.assertTrue(self.consume(limit=5).allowed)

        lowered = self.consume(limit=3)

        self.assertFalse(lowered.allowed)
        self.assertEqual(lowered.limit, 3)
        self.assertEqual(lowered.remaining_requests, 0)

    def test_retry_after_rounds_up_and_never_falls_below_one(self):
        self.clock.value = 179.01
        decision = self.consume(limit=1)
        self.assertEqual(decision.retry_after_seconds, 1)

        self.clock.value = 121.01
        decision = self.consume(key_id="akid_student_two", limit=1)
        self.assertEqual(decision.retry_after_seconds, 59)

    def test_invalid_inputs_fail_before_storage(self):
        invalid_calls = (
            {"key_id": "", "operation": "responses.create", "limit": 1},
            {"key_id": "akid_one", "operation": "", "limit": 1},
            {"key_id": "akid_one", "operation": "responses.create", "limit": 0},
            {"key_id": "akid_one", "operation": "responses.create", "limit": True},
        )
        for arguments in invalid_calls:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.limiter.consume(**arguments)

        self.clock.value = float("nan")
        with self.assertRaises(ValueError):
            self.consume()
        self.assertEqual(len(list(self.collection.find({}))), 0)

    def test_store_failures_are_wrapped_without_exposing_details(self):
        for failure_stage in ("insert", "update", "read"):
            with self.subTest(failure_stage=failure_stage):
                limiter = FixedWindowRateLimiter(
                    FailingCollection(failure_stage),
                    clock=self.clock,
                )
                with self.assertRaises(RateLimitStoreUnavailable) as raised:
                    limiter.consume(
                        key_id="akid_one",
                        operation="responses.create",
                        limit=1,
                    )
                self.assertNotIn("synthetic", str(raised.exception).lower())

        limiter = FixedWindowRateLimiter(
            InvalidUpdateCollection(),
            clock=self.clock,
        )
        with self.assertRaises(RateLimitStoreUnavailable):
            limiter.consume(
                key_id="akid_one",
                operation="responses.create",
                limit=1,
            )

    def test_pymongo_duplicate_bucket_creation_is_a_normal_race(self):
        limiter = FixedWindowRateLimiter(
            PyMongoDuplicateInsertCollection(),
            clock=self.clock,
        )

        decision = limiter.consume(
            key_id="akid_one",
            operation="responses.create",
            limit=1,
        )

        self.assertTrue(decision.allowed)

    def test_mongita_cleanup_is_bounded_and_removes_expired_windows(self):
        expired_at = datetime.fromtimestamp(100, tz=timezone.utc)
        self.collection.insert_one({"_id": "expired", "expires_at": expired_at})
        recording = RecordingCollection(self.collection)
        limiter = FixedWindowRateLimiter(
            recording,
            clock=self.clock,
            cleanup_expired=True,
        )

        limiter.consume(key_id="akid_one", operation="models.list", limit=5)
        self.assertIsNone(self.collection.find_one({"_id": "expired"}))
        self.assertEqual(recording.cleanup_calls, 1)

        self.clock.value += 1
        limiter.consume(key_id="akid_two", operation="models.list", limit=5)
        self.assertEqual(recording.cleanup_calls, 1)

        self.clock.value += MONGITA_CLEANUP_INTERVAL_SECONDS
        limiter.consume(key_id="akid_three", operation="models.list", limit=5)
        self.assertEqual(recording.cleanup_calls, 2)

    def test_cleanup_failure_does_not_change_the_enforcement_decision(self):
        recording = RecordingCollection(self.collection, cleanup_fails=True)
        logger = logging.getLogger(f"rate-limit-test-{uuid4().hex}")
        limiter = FixedWindowRateLimiter(
            recording,
            clock=self.clock,
            cleanup_expired=True,
            logger=logger,
        )

        with self.assertLogs(logger, level="WARNING") as captured:
            decision = limiter.consume(
                key_id="akid_one",
                operation="responses.create",
                limit=1,
            )

        self.assertTrue(decision.allowed)
        self.assertEqual(recording.cleanup_calls, 1)
        self.assertIn("rate_limit.cleanup_failed", " ".join(captured.output))

    def test_conditional_increment_never_allows_more_than_the_limit(self):
        limit = 10

        def consume_once(_index):
            return self.consume(limit=limit)

        with ThreadPoolExecutor(max_workers=20) as executor:
            decisions = list(executor.map(consume_once, range(50)))

        self.assertEqual(sum(decision.allowed for decision in decisions), limit)
        self.assertTrue(
            all(0 <= decision.remaining_requests < limit for decision in decisions)
        )
        document = self.collection.find_one({})
        self.assertEqual(document["count"], limit)


class RateLimitIndexTests(unittest.TestCase):
    def test_ttl_index_contract_is_explicit(self):
        collection = IndexRecordingCollection()

        result = ensure_rate_limit_ttl_index(collection)

        self.assertEqual(result, "synthetic-index")
        self.assertEqual(
            collection.calls,
            [
                (
                    [("expires_at", 1)],
                    {
                        "expireAfterSeconds": 0,
                        "name": RATE_LIMIT_TTL_INDEX_NAME,
                    },
                )
            ],
        )

    def test_ttl_index_requires_a_collection(self):
        with self.assertRaises(ValueError):
            ensure_rate_limit_ttl_index(None)


if __name__ == "__main__":
    unittest.main()
