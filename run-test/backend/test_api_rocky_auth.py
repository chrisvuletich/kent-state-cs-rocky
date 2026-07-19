from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "api-rocky" / "api.py"

spec = importlib.util.spec_from_file_location("api_rocky_api", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load api-rocky module from {MODULE_PATH}")

api_rocky = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_rocky)


class FakeCollection:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(row) for row in rows or []]

    def find_one(self, query: dict):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return row
        return None

    def find(self, query: dict | None = None):
        query = query or {}
        return [
            row
            for row in self.rows
            if all(row.get(key) == value for key, value in query.items())
        ]

    def insert_one(self, doc: dict):
        self.rows.append(dict(doc))

    def update_one(self, query: dict, update: dict):
        for row in self.rows:
            if not all(row.get(key) == value for key, value in query.items()):
                continue
            for key, value in update.get("$set", {}).items():
                row[key] = value
            return


class ApiRockyAuthTests(unittest.TestCase):
    def setUp(self):
        self.original_bypass = os.environ.get("ROCKY_DEV_AUTH_BYPASS")
        os.environ["ROCKY_DEV_AUTH_BYPASS"] = "false"
        api_rocky.api_keys_col = FakeCollection()
        api_rocky.conversations_col = FakeCollection()
        api_rocky.messages_col = FakeCollection()

    def tearDown(self):
        if self.original_bypass is None:
            os.environ.pop("ROCKY_DEV_AUTH_BYPASS", None)
        else:
            os.environ["ROCKY_DEV_AUTH_BYPASS"] = self.original_bypass

    def test_get_key_doc_accepts_hashed_course_key(self):
        plaintext = "sk_kent_test_hashed_course_key"
        expected_hash = api_rocky.hash_api_key(plaintext)
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": expected_hash,
                    "owner_id": "student.local@kent.edu",
                    "is_active": True,
                }
            ]
        )

        key_doc = api_rocky.get_key_doc(plaintext)

        self.assertIsNotNone(key_doc)
        self.assertEqual(key_doc.get("owner_id"), "student.local@kent.edu")

    def test_get_key_doc_rejects_inactive_or_deleted_hashed_course_key(self):
        inactive_key = "sk_kent_inactive"
        deleted_key = "sk_kent_deleted"
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": api_rocky.hash_api_key(inactive_key),
                    "owner_id": "student.local@kent.edu",
                    "is_active": False,
                },
                {
                    "hash": api_rocky.hash_api_key(deleted_key),
                    "owner_id": "student.local@kent.edu",
                    "deleted_at": "2026-07-07T00:00:00+00:00",
                },
            ]
        )

        self.assertIsNone(api_rocky.get_key_doc(inactive_key))
        self.assertIsNone(api_rocky.get_key_doc(deleted_key))

    def test_get_key_doc_rejects_plaintext_only_documents(self):
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "api-key": "plaintext-local-key",
                    "owner_id": "plaintext.local@kent.edu",
                    "is_active": True,
                }
            ]
        )

        self.assertIsNone(api_rocky.get_key_doc("plaintext-local-key"))

    def test_get_key_doc_accepts_hashed_service_key(self):
        plaintext = "service-key"
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": api_rocky.hash_api_key(plaintext),
                    "owner_id": "rocky-chat-service@kent.edu",
                    "owner_type": "service",
                    "is_active": True,
                }
            ]
        )

        key_doc = api_rocky.get_key_doc(plaintext)

        self.assertIsNotNone(key_doc)
        self.assertEqual(key_doc.get("owner_id"), "rocky-chat-service@kent.edu")

    def test_service_key_conversation_list_requires_forwarded_user_context(self):
        plaintext = "service-key"
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": api_rocky.hash_api_key(plaintext),
                    "owner_id": "rocky-chat-service@kent.edu",
                    "owner_type": "service",
                    "key_scope": "service",
                    "is_active": True,
                }
            ]
        )
        api_rocky.conversations_col = FakeCollection(
            [
                {
                    "conversation_id": "conversation-one",
                    "user_id": "user-one",
                    "title": "User One",
                    "created_at": "2026-07-07T00:00:00+00:00",
                    "updated_at": "2026-07-07T00:00:00+00:00",
                }
            ]
        )

        response = api_rocky.app.test_client().post(
            "/conversations/list",
            json={"api-key": plaintext},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json().get("error"), "Missing chat user context.")

    def test_service_key_conversation_list_is_scoped_to_forwarded_user(self):
        plaintext = "service-key"
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": api_rocky.hash_api_key(plaintext),
                    "owner_id": "rocky-chat-service@kent.edu",
                    "owner_type": "service",
                    "key_scope": "service",
                    "is_active": True,
                }
            ]
        )
        api_rocky.conversations_col = FakeCollection(
            [
                {
                    "conversation_id": "conversation-one",
                    "user_id": "user-one",
                    "title": "User One",
                    "created_at": "2026-07-07T00:00:00+00:00",
                    "updated_at": "2026-07-07T00:00:00+00:00",
                },
                {
                    "conversation_id": "conversation-two",
                    "user_id": "user-two",
                    "title": "User Two",
                    "created_at": "2026-07-07T00:00:00+00:00",
                    "updated_at": "2026-07-07T00:01:00+00:00",
                },
            ]
        )

        response = api_rocky.app.test_client().post(
            "/conversations/list",
            json={"api-key": plaintext},
            headers={
                "X-Rocky-User-Id": "user-one",
                "X-Rocky-User-Email": "one@kent.edu",
            },
        )

        self.assertEqual(response.status_code, 200)
        conversations = response.get_json().get("conversations")
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0].get("conversation_id"), "conversation-one")

    def test_person_key_ignores_spoofed_forwarded_user_context(self):
        plaintext = "person-key"
        api_rocky.api_keys_col = FakeCollection(
            [
                {
                    "hash": api_rocky.hash_api_key(plaintext),
                    "owner_id": "real-user",
                    "owner_type": "person",
                    "is_active": True,
                }
            ]
        )
        api_rocky.conversations_col = FakeCollection(
            [
                {
                    "conversation_id": "real-conversation",
                    "user_id": "real-user",
                    "title": "Real User",
                    "created_at": "2026-07-07T00:00:00+00:00",
                    "updated_at": "2026-07-07T00:00:00+00:00",
                },
                {
                    "conversation_id": "spoofed-conversation",
                    "user_id": "spoofed-user",
                    "title": "Spoofed User",
                    "created_at": "2026-07-07T00:00:00+00:00",
                    "updated_at": "2026-07-07T00:01:00+00:00",
                },
            ]
        )

        response = api_rocky.app.test_client().post(
            "/conversations/list",
            json={"api-key": plaintext},
            headers={"X-Rocky-User-Id": "spoofed-user"},
        )

        self.assertEqual(response.status_code, 200)
        conversations = response.get_json().get("conversations")
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0].get("conversation_id"), "real-conversation")

    def test_recent_message_history_is_scoped_by_user_id(self):
        api_rocky.messages_col = FakeCollection(
            [
                {
                    "conversation_id": "shared-id",
                    "user_id": "user-one",
                    "role": "user",
                    "content": "one",
                    "created_at": "2026-07-07T00:00:00+00:00",
                },
                {
                    "conversation_id": "shared-id",
                    "user_id": "user-two",
                    "role": "user",
                    "content": "two",
                    "created_at": "2026-07-07T00:00:01+00:00",
                },
            ]
        )

        messages = api_rocky.load_recent_messages("shared-id", "user-one")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].get("content"), "one")


if __name__ == "__main__":
    unittest.main()
