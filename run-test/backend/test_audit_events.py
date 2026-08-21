from __future__ import annotations

from test_support import BackendTestCase, main
from backend.route_handlers.audit import _audit_value


class AuditEventTests(BackendTestCase):
    def _events(self, event_type: str):
        return [row for row in main.api_history.find({}) if row.get("event_type") == event_type]

    def test_user_role_change_creates_trusted_audit_event(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        response = self.client.put(
            f"/users/{student_id}",
            json={"role": "instructor"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        events = self._events("user-updated")
        self.assertTrue(events)
        event = events[-1]
        self.assertEqual(event.get("u_id"), self.seeded_user_ids["admin.local@kent.edu"])
        self.assertEqual((event.get("meta") or {}).get("target_id"), student_id)
        self.assertEqual((event.get("meta") or {}).get("changes", {}).get("role", {}).get("after"), "instructor")

    def test_rejected_mutation_does_not_create_audit_event(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        before = len(self._events("user-updated"))
        response = self.client.put(
            f"/users/{student_id}",
            json={"role": "owner"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self._events("user-updated")), before)

    def test_course_mutations_are_audited(self):
        response = self.client.post(
            "/courses",
            json={
                "id": 404,
                "code": "CS 44004",
                "name": "Audit Systems",
                "instructor_id": self.seeded_user_ids["instructor.local@kent.edu"],
                "semester": "Fall 2027",
                "members": [],
                "groups": [],
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 201)
        event = self._events("course-created")[-1]
        self.assertEqual(event.get("course_id"), 404)
        self.assertEqual(event.get("c_id"), "CS 44004")

    def test_course_deletion_removes_its_api_keys_and_is_audited(self):
        existing_keys = list(main.api_keys.find({"course_id": 1}))
        self.assertTrue(existing_keys)
        response = self.client.delete("/courses/1", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(main.api_keys.find({"course_id": 1})), [])
        event = self._events("course-deleted")[-1]
        self.assertEqual((event.get("meta") or {}).get("changes", {}).get("deleted_keys"), len(existing_keys))

    def test_account_deactivation_suspends_owned_api_keys(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        generated = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.student_headers,
        )
        self.assertEqual(generated.status_code, 200)
        response = self.client.put(
            f"/users/{student_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        owned_keys = [
            key for key in main.api_keys.find({})
            if (key.get("owner_id") or "").lower() == student_id.lower()
        ]
        self.assertTrue(owned_keys)
        self.assertTrue(all(key.get("is_active") is False for key in owned_keys))
        self.assertTrue(all(key.get("disabled_reason") == "account-inactive" for key in owned_keys))

    def test_reactivation_does_not_restore_a_previously_disabled_key(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        key_id = main.api_keys.insert_one({
            "owner_id": student_id,
            "owner_type": "person",
            "key_scope": "user-default",
            "key_name": "default",
            "hash": "test-hash",
            "is_active": False,
            "disabled_reason": "administrator-disabled",
        }).inserted_id

        deactivate = self.client.put(
            f"/users/{student_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        reactivate = self.client.put(
            f"/users/{student_id}",
            json={"is_active": True},
            headers=self.admin_headers,
        )
        self.assertEqual(deactivate.status_code, 200)
        self.assertEqual(reactivate.status_code, 200)
        stored_key = main.api_keys.find_one({"_id": key_id})
        self.assertIs(stored_key.get("is_active"), False)
        self.assertEqual(stored_key.get("disabled_reason"), "administrator-disabled")

    def test_audit_metadata_excludes_sensitive_fields(self):
        changes = _audit_value({
            "api_key": "plaintext",
            "apiKey": "plaintext-camel",
            "key_hash": "stored-hash",
            "role": "student",
        })
        self.assertNotIn("api_key", changes)
        self.assertNotIn("apiKey", changes)
        self.assertNotIn("key_hash", changes)
        self.assertEqual(changes.get("role"), "student")

    def test_audit_exports_are_admin_only_csv_safe_and_audited(self):
        main.api_history.insert_one({
            "u_id": self.seeded_user_ids["admin.local@kent.edu"],
            "c_id": "=COURSE",
            "event_type": "user-updated",
            "created": "2026-08-08T12:00:00+00:00",
            "meta": {"changes": {"name": "+formula"}},
        })
        denied = self.client.get("/audit/export?format=csv", headers=self.student_headers)
        self.assertEqual(denied.status_code, 403)

        exported = self.client.get(
            "/audit/export?format=csv&course=%3DCOURSE",
            headers=self.admin_headers,
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        self.assertIn("'=COURSE", exported.get_data(as_text=True))
        self.assertTrue(self._events("audit-export"))


if __name__ == "__main__":
    import unittest

    unittest.main()
