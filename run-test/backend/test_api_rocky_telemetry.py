import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import requests
from mongita import MongitaClientMemory


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api-rocky"))
sys.path.insert(0, str(ROOT / "run-test" / "integration"))
with (
    patch.dict(os.environ, {
        "ROCKY_APP_ENV": "test",
        "ROCKY_CHAT_API_KEY": "",
        "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
    }),
):
    import api as rocky

import live_telemetry_smoke
from telemetry import CURRENT_COUNTER_DEFAULTS, CURRENT_DOCUMENT_ID
from telemetry_projection import refresh_current


def evaluate(expression, document):
    if isinstance(expression, str) and expression.startswith("$"):
        return document.get(expression[1:])
    if not isinstance(expression, dict):
        return expression
    if "$ifNull" in expression:
        value, fallback = expression["$ifNull"]
        value = evaluate(value, document)
        return evaluate(fallback, document) if value is None else value
    if "$add" in expression:
        return sum(evaluate(value, document) for value in expression["$add"])
    if "$max" in expression:
        return max(evaluate(value, document) for value in expression["$max"])
    if "$lte" in expression:
        left, right = expression["$lte"]
        return evaluate(left, document) <= evaluate(right, document)
    condition, yes, no = expression["$cond"]
    return evaluate(yes if evaluate(condition, document) else no, document)


class Current:
    def __init__(self):
        self.document = {"_id": CURRENT_DOCUMENT_ID,
                         **CURRENT_COUNTER_DEFAULTS}

    def update_one(self, query, update, upsert=False):
        if isinstance(update, list):
            before = copy.deepcopy(self.document)
            self.document.update({
                field: evaluate(value, before)
                for field, value in update[0]["$set"].items()
            })
        else:
            for field, value in update.get("$inc", {}).items():
                self.document[field] = self.document.get(field, 0) + value
            self.document.update(update.get("$set", {}))
            for field, value in update.get("$max", {}).items():
                self.document[field] = max(
                    self.document.get(field, value), value
                )
        return SimpleNamespace(modified_count=1)

    def find_one(self, query):
        return copy.deepcopy(self.document)


def granite(payload, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def success(output="Private model reply"):
    return granite({
        "model": "requested-model",
        "output_text": output,
        "telemetry": {
            "model_input_bytes": 211, "model_output_bytes": 377,
            "provider": {
                "actual_model": "actual-model", "stop_reason": "stop",
                "prompt_eval_count": 13, "eval_count": 8,
                "total_duration": 4_200_000_000,
                "load_duration": 100_000_000,
                "prompt_eval_duration": 300_000_000,
                "eval_duration": 3_700_000_000,
                "private": "must not be stored",
            },
        },
    })


class ApiTelemetryTests(unittest.TestCase):
    def setUp(self):
        database = MongitaClientMemory()[uuid4().hex]
        rocky.api_keys_col = database["keys"]
        rocky.conversations_col = database["conversations"]
        rocky.messages_col = database["messages"]
        rocky.telemetry_interactions_col = database["interactions"]
        rocky.telemetry_current_col = Current()
        rocky.telemetry_store = rocky.TelemetryStore(
            rocky.telemetry_interactions_col, rocky.telemetry_current_col)
        rocky.app.config["TESTING"] = True
        self.key = "private-test-api-key"
        rocky.api_keys_col.insert_one(
            {"hash": rocky.hash_api_key(self.key),
             "key_id": "akid_test_person",
             "owner_id": "private-user-id", "email": "private.user@kent.edu",
             "owner_type": "person", "course_id": 44001,
             "key_name": "key-1",
             "is_active": True})
        self.client = rocky.app.test_client()

    def post(self, **values):
        return self.client.post("/v1/responses", json={
            "input": "Private prompt café ☕",
            "model": "rocky",
            "store": False,
            **values,
        }, headers={"Authorization": f"Bearer {self.key}"})

    def rows(self):
        return list(rocky.telemetry_interactions_col.find({}))

    @patch.object(rocky.requests, "post")
    def test_completed_is_permanent_deduplicated_and_fully_attributed(self, post):
        post.return_value = success()
        response = self.post(metadata={
            "assignment": "lab-one",
            "token": self.key,
        })
        row = self.rows()[0]
        current = rocky.telemetry_current_col.find_one({})
        self.assertEqual((response.status_code, row["outcome"]), (200, "completed"))
        self.assertEqual(response.headers["X-Rocky-Request-Id"], row["_id"])
        expected = {
            "interactions_accepted_total": 1,
            "interactions_completed_total": 1,
            "active_requests": 0,
            "model_input_bytes_total": 211,
            "model_output_bytes_total": 377,
            "prompt_tokens_total": 13,
            "output_tokens_total": 8,
            "request_latency_samples_total": 1,
            "last_model": "actual-model",
            "last_stop_reason": "stop",
        }
        self.assertEqual({field: current.get(field) for field in expected},
                         expected)
        self.assertEqual(current["request_latency_ms_total"],
                         row["request_latency_ms"])
        self.assertEqual(row["schema_version"], 2)
        self.assertNotIn("expires_at", row)
        self.assertEqual(row["request"]["input_text"],
                         "Private prompt café ☕")
        self.assertEqual(row["response"]["output_text"],
                         "Private model reply")
        self.assertEqual(row["actor"], {
            "user_id": "private-user-id",
            "email": "private.user@kent.edu",
            "name": None,
            "attribution": "personal-key-owner",
        })
        self.assertEqual(row["credential"]["key_id"], "akid_test_person")
        self.assertEqual(row["course"]["course_id"], 44001)
        self.assertEqual(row["usage"]["total_tokens"], 21)
        self.assertEqual(
            row["request"]["body"]["metadata"],
            {"assignment": "lab-one", "token": "[REDACTED]"},
        )
        self.assertEqual(
            row["performance"]["generation_duration_ns"],
            3_700_000_000,
        )
        stored = repr(row) + repr(current)
        for secret in (self.key, rocky.hash_api_key(self.key), "must not"):
            self.assertNotIn(secret, stored)

        duplicate = {
            "request_id": row["_id"],
            "current_counted": True,
            "persisted": True,
            "started_monotonic_ns": 0,
        }
        self.assertFalse(rocky.telemetry_store.record_terminal(
            duplicate, "failed", request_latency_ms=99))
        self.assertEqual(rocky.telemetry_current_col.find_one({}), current)

    @patch.object(rocky.requests, "post")
    def test_failure_timeout_validation_and_latency(self, post):
        post.return_value = granite({
            "error": {"type": "model_error"},
            "telemetry": {"model_input_bytes": 4, "model_output_bytes": 5},
        }, 502)
        self.assertEqual(self.post().status_code, 502)
        post.side_effect = requests.Timeout("private")
        self.assertEqual(self.post().status_code, 504)
        post.side_effect = None
        post.return_value = granite({}, 504)
        post.return_value.json.side_effect = ValueError()
        self.assertEqual(self.post().status_code, 504)
        rows = self.rows()
        current = rocky.telemetry_current_col.find_one({})
        self.assertEqual([row["outcome"] for row in rows],
                         ["failed", "timed_out", "timed_out"])
        self.assertEqual(current["request_latency_samples_total"], 3)
        self.assertEqual(current["request_latency_ms_total"],
                         sum(row["request_latency_ms"] for row in rows))

        with patch.object(rocky, "get_or_create_conversation",
                          side_effect=RuntimeError("persistence failed")):
            self.assertEqual(self.post(store=True).status_code, 500)
        self.assertEqual(self.rows()[-1]["outcome"], "failed")
        invalid = {"store": True, "model": "rocky", "input": [{
                       "role": "user", "content": [{
                           "type": "input_image", "image_url": "ignored",
                       }],
                   }]}
        self.assertEqual(self.client.post(
            "/v1/responses",
            json=invalid,
            headers={"Authorization": f"Bearer {self.key}"},
        ).status_code, 400)
        self.assertEqual(self.rows()[-1]["outcome"], "rejected")
        self.assertEqual(self.rows()[-1]["error_stage"], "validation")
        post.return_value = success(output=None)
        self.assertEqual(self.post().status_code, 502)
        self.assertEqual(self.rows()[-1]["outcome"], "failed")

        post.return_value = success()
        failing = Mock()
        failing.insert_one.side_effect = RuntimeError(
            "mongodb://user:password@example prompt=private")
        rocky.telemetry_store = rocky.TelemetryStore(
            failing, failing, logger=rocky.app.logger)
        with self.assertLogs(rocky.app.logger.name, level="WARNING") as logs:
            self.assertEqual(self.post().status_code, 200)
        output = "\n".join(logs.output)
        for secret in ("password", "mongodb://", "private"):
            self.assertNotIn(secret, output)

    def test_invalid_json_and_invalid_key_are_permanent_rejections(self):
        malformed = self.client.post(
            "/v1/responses",
            data='{"model":"rocky","input":',
            content_type="application/json",
        )
        invalid_key = self.client.post(
            "/v1/responses",
            json={"model": "rocky", "input": "record this", "store": False},
            headers={
                "Authorization": "Bearer should-never-be-stored",
                "X-Forwarded-For": "203.0.113.1, 198.51.100.7",
            },
        )

        self.assertEqual((malformed.status_code, invalid_key.status_code),
                         (400, 401))
        rows = self.rows()
        self.assertEqual([row["error_type"] for row in rows],
                         ["invalid_json", "invalid_api_key"])
        self.assertTrue(all(row["outcome"] == "rejected" for row in rows))
        self.assertTrue(all(
            response.headers.get("X-Rocky-Request-Id") == row["_id"]
            for response, row in zip((malformed, invalid_key), rows)
        ))
        self.assertEqual(
            rows[1]["client"]["remote_address"],
            "198.51.100.7",
        )
        self.assertNotIn("should-never-be-stored", repr(rows))

    def test_oversized_request_records_metadata_without_reading_full_body(self):
        original_limit = rocky.app.config["MAX_CONTENT_LENGTH"]
        rocky.app.config["MAX_CONTENT_LENGTH"] = 32
        try:
            response = self.client.post(
                "/v1/responses",
                data="x" * 128,
                content_type="application/json",
            )
        finally:
            rocky.app.config["MAX_CONTENT_LENGTH"] = original_limit

        row = self.rows()[0]
        self.assertEqual(response.status_code, 413)
        self.assertEqual(row["error_type"], "request_too_large")
        self.assertEqual(row["client"]["content_length"], 128)
        self.assertNotIn("request", row)

    @patch.object(rocky.requests, "post")
    def test_web_and_group_key_attribution_is_not_guessed(self, post):
        post.return_value = success()
        service_key = "service-key"
        group_key = "group-key"
        rocky.api_keys_col.insert_many([
            {
                "hash": rocky.hash_api_key(service_key),
                "key_id": "akid_hidden_user",
                "owner_type": "person",
                "owner_id": "database-user-id",
                "key_scope": "user-default",
                "is_active": True,
            },
            {
                "hash": rocky.hash_api_key(group_key),
                "key_id": "akid_group",
                "owner_type": "group",
                "owner_id": "group-a",
                "course_id": 44001,
                "is_active": True,
            },
        ])

        service_response = self.client.post(
            "/v1/responses",
            json={"model": "rocky", "input": "web", "store": False},
            headers={
                "Authorization": f"Bearer {service_key}",
                "X-Rocky-User-Id": "student-one",
                "X-Rocky-User-Email": "one@kent.edu",
                "X-Rocky-User-Name": "Student One",
            },
        )
        group_response = self.client.post(
            "/v1/responses",
            json={"model": "rocky", "input": "group", "store": False},
            headers={
                "Authorization": f"Bearer {group_key}",
                "X-Rocky-User-Id": "spoofed-student",
            },
        )

        self.assertEqual((service_response.status_code,
                          group_response.status_code), (200, 200))
        service_row, group_row = self.rows()
        self.assertEqual(service_row["source"], "web_chat")
        self.assertEqual(service_row["actor"]["user_id"], "student-one")
        self.assertEqual(service_row["actor"]["attribution"],
                         "trusted-web-session")
        self.assertEqual(group_row["actor"]["user_id"], None)
        self.assertEqual(group_row["actor"]["attribution"],
                         "group-key-only")
        self.assertEqual(group_row["course"]["group_id"], "group-a")

    @patch.object(rocky.requests, "post")
    def test_required_logging_fails_closed_before_inference(self, post):
        failing = Mock()
        failing.insert_one.side_effect = RuntimeError("database unavailable")
        rocky.telemetry_store = rocky.TelemetryStore(
            failing, failing, logger=rocky.app.logger)
        with patch.object(rocky, "REQUIRE_REQUEST_LOGGING", True):
            response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertIn("X-Rocky-Request-Id", response.headers)
        post.assert_not_called()


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        database = MongitaClientMemory()[uuid4().hex]
        self.interactions = database["interactions"]
        self.current = database["current"]
        self.users = database["users"]
        self.now = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)

    def seed(self, **values):
        self.current.insert_one({
            "_id": CURRENT_DOCUMENT_ID, **CURRENT_COUNTER_DEFAULTS, **values,
        })

    def test_projection_is_permanent_idempotent_and_refreshes_users(self):
        self.seed(
            counter_revision=8, interactions_accepted_total=6,
            interactions_completed_total=2, interactions_failed_total=1,
            interactions_timed_out_total=1, active_requests=99,
            model_input_bytes_total=301, model_output_bytes_total=402,
            prompt_tokens_total=15, output_tokens_total=22,
            request_latency_ms_total=600, request_latency_samples_total=3,
        )
        self.users.insert_many([{"_id": "one"}, {"_id": "two"}])
        self.interactions.insert_many([
            {"_id": "active", "state": "accepted",
             "accepted_at": self.now - timedelta(seconds=10)},
            {"_id": "unresolved", "state": "accepted",
             "accepted_at": self.now - timedelta(seconds=300)},
            {"_id": "expired", "state": "terminal",
             "accepted_at": self.now - timedelta(days=8)},
        ])
        first = refresh_current(self.interactions, self.current, self.users,
                                as_of=self.now)
        self.interactions.delete_many({"state": "terminal"})
        second = refresh_current(self.interactions, self.current, self.users,
                                 as_of=self.now)
        self.assertEqual(first, second)
        expected = {
            "registered_users": 2, "active_requests": 2,
            "unresolved_interactions": 1, "average_latency_ms": 200,
            "interactions_accepted_total": 6,
            "interactions_completed_total": 2,
            "model_input_bytes_total": 301, "model_output_bytes_total": 402,
            "prompt_tokens_total": 15, "output_tokens_total": 22,
        }
        self.assertEqual({field: second.get(field) for field in expected},
                         expected)

    def test_stale_and_racing_projection_cannot_overwrite_current(self):
        prior_time = self.now - timedelta(minutes=1)
        self.seed(counter_revision=3, interactions_accepted_total=2,
                  registered_users=7, updated_at=prior_time)
        newer = refresh_current(self.interactions, self.current, self.users,
                                as_of=self.now + timedelta(seconds=10))
        self.users.insert_one({"_id": "late"})
        self.assertEqual(refresh_current(
            self.interactions, self.current, self.users, as_of=self.now
        ), newer)

        def accept():
            self.current.update_one({"_id": CURRENT_DOCUMENT_ID}, {"$inc": {
                "counter_revision": 1, "interactions_accepted_total": 1,
                "active_requests": 1,
            }})

        racing = Mock()
        racing.find.side_effect = lambda query: (
            accept(), self.interactions.find(query)
        )[1]
        result = refresh_current(racing, self.current, self.users,
                                 as_of=self.now + timedelta(seconds=20))
        self.assertEqual((result["counter_revision"], result["active_requests"]),
                         (4, 3))

class LiveSmokeTests(unittest.TestCase):
    def test_smoke_requires_exact_correlated_request(self):
        request_id = str(uuid4())
        interaction = {
            "_id": request_id, "state": "terminal", "outcome": "completed",
            "schema_version": 2, "content_available": True,
            "request": {"input_text": live_telemetry_smoke.PROMPT},
            "response": {"output_text": "Rocky"},
            "model_input_bytes": 10, "model_output_bytes": 20,
            "request_latency_ms": 5,
        }
        before = dict(CURRENT_COUNTER_DEFAULTS)
        after = {
            **before, "interactions_accepted_total": 1,
            "interactions_completed_total": 1,
            "model_input_bytes_total": 10, "model_output_bytes_total": 20,
            "request_latency_ms_total": 5,
            "request_latency_samples_total": 1,
        }
        interactions = Mock()
        interactions.find_one.side_effect = lambda query: (
            interaction if query.get("_id") == request_id else None
        )
        client = MagicMock()
        client.__getitem__.return_value = {
            "telemetry_interactions": interactions,
            "telemetry_current": Mock(), "users": Mock(),
        }
        response = Mock(ok=True, headers={"X-Rocky-Request-Id": request_id})
        response.json.return_value = {"output_text": "Rocky"}
        environment = {name: "test" for name in live_telemetry_smoke.REQUIRED}
        with (
            patch.dict(os.environ, environment),
            patch.object(live_telemetry_smoke, "MongoClient",
                         return_value=client),
            patch.object(live_telemetry_smoke.requests, "post",
                         return_value=response) as post,
            patch("telemetry_projection.refresh_current",
                  side_effect=(before, after, before)),
        ):
            result = live_telemetry_smoke.run_live_smoke()
            self.assertEqual(result["interactions_completed_total"], 1)
            self.assertEqual(post.call_args.args[0], "test/v1/responses")
            self.assertEqual(
                post.call_args.kwargs["headers"],
                {"Authorization": "Bearer test"},
            )
            response.headers["X-Rocky-Request-Id"] = str(uuid4())
            with self.assertRaises(live_telemetry_smoke.SmokeFailure):
                live_telemetry_smoke.run_live_smoke()


if __name__ == "__main__":
    unittest.main()
