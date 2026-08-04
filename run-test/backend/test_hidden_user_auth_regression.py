from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
API_ROCKY_DIR = ROOT / "api-rocky"
BACKEND_DIR = ROOT / "rocky-backend"
sys.path.insert(0, str(API_ROCKY_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from backend.api_key_generator import derive_hidden_api_key
from backend.route_handlers.auth import ensure_default_api_key_for_user


API_SPEC = importlib.util.spec_from_file_location(
    "api_rocky_auth_regression", API_ROCKY_DIR / "api.py"
)
if API_SPEC is None or API_SPEC.loader is None:
    raise RuntimeError("Unable to load api-rocky for isolated authentication tests.")

api_rocky = importlib.util.module_from_spec(API_SPEC)
with patch.dict(
    os.environ,
    {
        "ROCKY_APP_ENV": "test",
        "ROCKY_TEST_SKIP_DATABASE_INIT": "true",
    },
):
    API_SPEC.loader.exec_module(api_rocky)


SYNTHETIC_OWNER_INPUT = " Synthetic-Owner "
SYNTHETIC_OWNER_NORMALIZED = "synthetic-owner"
SYNTHETIC_SECRET_A = "phase-one-synthetic-secret-a"
SYNTHETIC_SECRET_B = "phase-one-synthetic-secret-b"
INVALID_API_KEY_RESPONSE = {"error": "Invalid API key"}


class FakeCollection:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(row) for row in rows or []]

    @staticmethod
    def _matches(row: dict, query: dict):
        return all(row.get(key) == value for key, value in query.items())

    def find_one(self, query: dict):
        return next(
            (row for row in self.rows if self._matches(row, query)),
            None,
        )

    def find(self, query: dict | None = None):
        query = query or {}
        return [row for row in self.rows if self._matches(row, query)]

    def insert_one(self, document: dict):
        inserted = dict(document)
        inserted.setdefault("_id", f"synthetic-record-{len(self.rows) + 1}")
        self.rows.append(inserted)
        return SimpleNamespace(inserted_id=inserted["_id"])

    def replace_one(self, query: dict, document: dict):
        replacement = dict(document)
        for index, row in enumerate(self.rows):
            if self._matches(row, query):
                replacement.setdefault("_id", row.get("_id"))
                self.rows[index] = replacement
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    def update_one(self, query: dict, update: dict):
        for row in self.rows:
            if not self._matches(row, query):
                continue
            row.update(update.get("$set", {}))
            return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class HiddenUserAuthRegressionTests(unittest.TestCase):
    def setUp(self):
        self.original_bypass = os.environ.get("ROCKY_DEV_AUTH_BYPASS")
        os.environ["ROCKY_DEV_AUTH_BYPASS"] = "false"
        self.original_telemetry_store = api_rocky.telemetry_store
        api_rocky.api_keys_col = FakeCollection()
        api_rocky.conversations_col = FakeCollection()
        api_rocky.messages_col = FakeCollection()
        api_rocky.telemetry_store = None
        api_rocky.app.config["TESTING"] = True
        self.client = api_rocky.app.test_client()

    def tearDown(self):
        api_rocky.telemetry_store = self.original_telemetry_store
        if self.original_bypass is None:
            os.environ.pop("ROCKY_DEV_AUTH_BYPASS", None)
        else:
            os.environ["ROCKY_DEV_AUTH_BYPASS"] = self.original_bypass

    def _create_backend_default_key(
        self,
        database: FakeCollection,
        secret: str = SYNTHETIC_SECRET_A,
    ) -> str:
        with patch.dict(os.environ, {"ROCKY_HIDDEN_API_KEY_SECRET": secret}):
            ensure_default_api_key_for_user(
                {"api_keys": database},
                {"_id": SYNTHETIC_OWNER_INPUT},
            )
        return derive_hidden_api_key(SYNTHETIC_OWNER_NORMALIZED, secret)

    def _post_conversation_list(self, key):
        return self.client.post(
            "/conversations/list",
            json={"api-key": key},
        )

    def _assert_invalid(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), INVALID_API_KEY_RESPONSE)

    def _matching_key_document(self, key: str, **overrides):
        document = {
            "hash": api_rocky.hash_api_key(key),
            "owner_id": SYNTHETIC_OWNER_NORMALIZED,
            "owner_type": "person",
            "key_scope": "user-default",
            "is_active": True,
        }
        document.update(overrides)
        return document

    def test_same_normalized_owner_secret_and_database_succeeds(self):
        shared_database = FakeCollection()
        key = self._create_backend_default_key(shared_database)
        api_rocky.api_keys_col = shared_database

        response = self._post_conversation_list(key)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"conversations": []})

    def test_same_owner_with_different_secret_returns_exact_401(self):
        shared_database = FakeCollection()
        self._create_backend_default_key(shared_database, SYNTHETIC_SECRET_A)
        api_rocky.api_keys_col = shared_database
        mismatched_key = derive_hidden_api_key(
            SYNTHETIC_OWNER_NORMALIZED,
            SYNTHETIC_SECRET_B,
        )

        self._assert_invalid(self._post_conversation_list(mismatched_key))

    def test_backend_database_a_and_api_database_b_returns_exact_401(self):
        backend_database_a = FakeCollection()
        key = self._create_backend_default_key(backend_database_a)
        api_rocky.api_keys_col = FakeCollection()

        self._assert_invalid(self._post_conversation_list(key))
        self.assertEqual(len(backend_database_a.rows), 1)

    def test_inactive_key_returns_exact_401(self):
        key = derive_hidden_api_key(
            SYNTHETIC_OWNER_NORMALIZED,
            SYNTHETIC_SECRET_A,
        )
        api_rocky.api_keys_col = FakeCollection(
            [self._matching_key_document(key, is_active=False)]
        )

        self._assert_invalid(self._post_conversation_list(key))

    def test_expired_key_returns_exact_401(self):
        key = derive_hidden_api_key(
            SYNTHETIC_OWNER_NORMALIZED,
            SYNTHETIC_SECRET_A,
        )
        expired_at = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        api_rocky.api_keys_col = FakeCollection(
            [self._matching_key_document(key, expire=expired_at)]
        )

        self._assert_invalid(self._post_conversation_list(key))

    def test_revoked_key_returns_exact_401(self):
        key = derive_hidden_api_key(
            SYNTHETIC_OWNER_NORMALIZED,
            SYNTHETIC_SECRET_A,
        )
        api_rocky.api_keys_col = FakeCollection(
            [self._matching_key_document(key, revoked_at="synthetic-revocation")]
        )

        self._assert_invalid(self._post_conversation_list(key))

    def test_deleted_key_returns_exact_401(self):
        key = derive_hidden_api_key(
            SYNTHETIC_OWNER_NORMALIZED,
            SYNTHETIC_SECRET_A,
        )
        api_rocky.api_keys_col = FakeCollection(
            [self._matching_key_document(key, deleted_at="synthetic-deletion")]
        )

        self._assert_invalid(self._post_conversation_list(key))

    def test_missing_and_malformed_key_inputs_fail_closed(self):
        malformed_records = [
            [],
            [{"owner_type": "person", "is_active": True}],
            [{"hash": None, "owner_type": "person", "is_active": True}],
            [{"hash": 123, "owner_type": "person", "is_active": True}],
        ]
        malformed_inputs = [None, {}, [], "", "   "]

        for rows in malformed_records:
            api_rocky.api_keys_col = FakeCollection(rows)
            self._assert_invalid(
                self._post_conversation_list("synthetic-invalid-candidate")
            )

        api_rocky.api_keys_col = FakeCollection()
        for malformed_input in malformed_inputs:
            self._assert_invalid(self._post_conversation_list(malformed_input))

    def test_invalid_auth_never_calls_granite_or_accepts_telemetry(self):
        telemetry_store = Mock()
        api_rocky.telemetry_store = telemetry_store

        with patch.object(api_rocky, "request_ai") as request_ai:
            response = self.client.post(
                "/v1/responses",
                json={
                    "api-key": "synthetic-unknown-key",
                    "message": "synthetic prompt",
                    "store": False,
                },
            )

        self._assert_invalid(response)
        request_ai.assert_not_called()
        telemetry_store.record_accepted.assert_not_called()

    def test_reinitializing_same_owner_secret_and_database_still_succeeds(self):
        persistent_database = FakeCollection()
        first_key = self._create_backend_default_key(persistent_database)
        second_key = self._create_backend_default_key(persistent_database)
        api_rocky.api_keys_col = persistent_database

        self.assertTrue(first_key == second_key)
        self.assertEqual(len(persistent_database.rows), 1)
        self.assertEqual(self._post_conversation_list(second_key).status_code, 200)


if __name__ == "__main__":
    unittest.main()
