from __future__ import annotations

from test_support import BackendTestCase, main, seed_backend


class CourseApiHistoryTests(BackendTestCase):
    def test_api_history_write_endpoint_is_not_public(self):
        self._log("Attempting to forge course API history as a student. Expecting HTTP 405.")

        response = self.client.post(
            "/courses/1/api-history",
            json={"eventType": "request", "ownerId": "someone-else", "meta": {"forged": True}},
            headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(any(
            isinstance(entry.get("meta"), dict) and entry["meta"].get("forged")
            for entry in main.api_history.find({})
        ))

    def test_course_api_history_can_be_read_back(self):
        self._log("Reading seeded API history for course 1.")
        seed_backend.seed_from_backend()

        response = self.client.get("/courses/1/api-history", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertGreaterEqual(len(payload), 1)
        self.assertTrue(any(entry.get("group_id") for entry in payload))

    def test_instructor_generate_person_key_logs_actor_and_target_owner(self):
        self._log("Instructor generates a student key and history keeps actor and owner attribution.")

        response = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "person",
                "ownerId": self.seeded_user_ids["student.local@kent.edu"],
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.instructor_headers,
        )
        self.assertEqual(response.status_code, 200)

        matching_entries = [
            entry
            for entry in main.api_history.find({"course_id": 1})
            if entry.get("event_type") == "generate-key"
            and isinstance(entry.get("meta"), dict)
            and (entry["meta"].get("owner_type") or "").lower() == "person"
            and (entry["meta"].get("owner_id") or "") == self.seeded_user_ids["student.local@kent.edu"]
            and entry["meta"].get("path") == "/courses/1/api-key/regenerate"
        ]
        self.assertTrue(matching_entries)

        history_entry = matching_entries[-1]
        history_meta = history_entry.get("meta") or {}

        self.assertEqual((history_entry.get("u_id") or ""), self.seeded_user_ids["instructor.local@kent.edu"])
        self.assertEqual((history_meta.get("actor_id") or ""), self.seeded_user_ids["instructor.local@kent.edu"])
        self.assertEqual(history_meta.get("actor_email"), "instructor.local@kent.edu")
        self.assertEqual((history_meta.get("owner_type") or "").lower(), "person")
        self.assertEqual((history_meta.get("owner_id") or ""), self.seeded_user_ids["student.local@kent.edu"])
        self.assertFalse(history_entry.get("is_group_member"))
        self.assertIsNone(history_entry.get("group_id"))

    def test_instructor_delete_group_key_logs_actor_and_group_target(self):
        self._log("Instructor deletes a group key and history keeps actor and group context.")

        create_response = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "group",
                "groupId": "group-se3010-a",
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.instructor_headers,
        )
        self.assertEqual(create_response.status_code, 200)

        delete_response = self.client.delete(
            "/courses/1/api-key",
            json={
                "ownerType": "group",
                "groupId": "group-se3010-a",
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.instructor_headers,
        )
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertNotIn("hash", (delete_payload or {}).get("key", {}))
        self.assertEqual((delete_payload or {}).get("key", {}).get("has_hash"), False)

        matching_entries = [
            entry
            for entry in main.api_history.find({"course_id": 1})
            if entry.get("event_type") == "delete-key"
            and isinstance(entry.get("meta"), dict)
            and (entry["meta"].get("owner_type") or "").lower() == "group"
            and (entry["meta"].get("owner_id") or "").lower() == "group-se3010-a"
            and entry["meta"].get("path") == "/courses/1/api-key"
        ]
        self.assertTrue(matching_entries)

        history_entry = matching_entries[-1]
        history_meta = history_entry.get("meta") or {}

        self.assertEqual((history_entry.get("u_id") or ""), self.seeded_user_ids["instructor.local@kent.edu"])
        self.assertEqual((history_meta.get("actor_id") or ""), self.seeded_user_ids["instructor.local@kent.edu"])
        self.assertEqual(history_meta.get("actor_email"), "instructor.local@kent.edu")
        self.assertEqual((history_meta.get("owner_type") or "").lower(), "group")
        self.assertEqual((history_meta.get("owner_id") or "").lower(), "group-se3010-a")
        self.assertEqual((history_entry.get("group_id") or "").lower(), "group-se3010-a")
        self.assertTrue(history_entry.get("is_group_member"))

if __name__ == "__main__":
    import unittest

    unittest.main()
