from __future__ import annotations

import hashlib

from backend.test_support import BackendTestCase, main, seed_backend


class BackendValidationTests(BackendTestCase):

    def test_seed_database_rejects_invalid_records(self):
        self._log("Seeding in-memory database with mixed valid/invalid fixture data.")
        summary = seed_backend.seed_backend_from_fixture()
        self._log(f"Seed summary: {summary}")

        self.assertEqual(summary["users_inserted"], 2)
        self.assertEqual(summary["users_rejected"], 2)
        self.assertEqual(summary["courses_inserted"], 1)
        self.assertEqual(summary["courses_rejected"], 2)
        self.assertEqual(summary["api_keys_inserted"], 1)
        self.assertEqual(summary["api_keys_rejected"], 2)

        self.assertEqual(main.users.count_documents({}), 2)
        self.assertEqual(main.courses.count_documents({}), 1)
        self.assertEqual(main.api_keys.count_documents({}), 1)

        self.assertEqual(main.users.find_one({"email": "bad.role@kent.edu"}), None)
        self.assertEqual(main.courses.find_one({"name": "Invalid Course Term"}), None)
        self.assertEqual(main.api_keys.find_one({"owner_id": ""}), None)

        seeded_key = main.api_keys.find_one({"course_id": 1})
        self.assertIsNotNone(seeded_key)
        self.assertTrue(isinstance(seeded_key.get("hash"), str) and len(seeded_key.get("hash")) == 64)
        self.assertEqual(seeded_key.get("owner_type"), "person")

    def test_create_user_rejects_bad_payload(self):
        self._log("Posting invalid user payload. Expecting HTTP 400.")
        response = self.client.post(
            "/users",
            json={"first_name": "X", "last_name": "User", "email": "not-an-email", "id": "x1", "is_admin": False},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_user_accepts_valid_payload(self):
        self._log("Posting valid user payload. Expecting HTTP 200.")
        response = self.client.post(
            "/users",
            json={
                "first_name": "Good",
                "last_name": "User",
                "email": "good.user@kent.edu",
                "id": "KSUID000000100",
                "is_admin": False,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_create_user_accepts_local_api_shape(self):
        self._log("Posting backend-style user payload without id. Expecting HTTP 200.")
        response = self.client.post(
            "/users",
            json={
                "first_name": "Local",
                "last_name": "Api User",
                "email": "local.api.user@kent.edu",
                "is_admin": False,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        saved = main.users.find_one({"email": "local.api.user@kent.edu"})
        self.assertIsNotNone(saved)
        self.assertTrue(saved.get("id"))

    def test_update_user_validates_status_and_protects_current_admin(self):
        self._log("Updating user status through /users/<id>. Expecting validation and self-lockout protection.")

        seeded_admin = main.users.find_one({"email": "admin.local@kent.edu"})
        self.assertIsNotNone(seeded_admin)
        admin_id = seeded_admin.get("id")
        user_id = self.seeded_user_ids["student.local@kent.edu"]
        self.assertTrue(isinstance(user_id, str) and user_id)

        invalid_payload_response = self.client.put(
            f"/users/{user_id}",
            json={"first_name": "Nope"},
            headers=self.admin_headers,
        )
        self.assertEqual(invalid_payload_response.status_code, 400)

        invalid_type_response = self.client.put(
            f"/users/{user_id}",
            json={"is_active": "false"},
            headers=self.admin_headers,
        )
        self.assertEqual(invalid_type_response.status_code, 400)

        valid_response = self.client.put(
            f"/users/{user_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(valid_response.status_code, 200)

        updated = main.users.find_one({"id": user_id})
        self.assertIsNotNone(updated)
        self.assertEqual(updated.get("is_active"), False)

        self_deactivate_response = self.client.put(
            f"/users/{admin_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(self_deactivate_response.status_code, 409)

        self_demote_response = self.client.put(
            f"/users/{admin_id}",
            json={"role": "student"},
            headers=self.admin_headers,
        )
        self.assertEqual(self_demote_response.status_code, 409)

        unchanged_admin = main.users.find_one({"id": admin_id})
        self.assertIsNotNone(unchanged_admin)
        self.assertTrue(unchanged_admin.get("is_active"))
        self.assertTrue(unchanged_admin.get("is_admin"))

    def test_bulk_status_rejects_current_admin_deactivation(self):
        admin_id = self.seeded_user_ids["admin.local@kent.edu"]
        student_id = self.seeded_user_ids["student.local@kent.edu"]

        response = self.client.patch(
            "/users/bulk-status",
            json={"user_ids": [admin_id, student_id], "is_active": False},
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(main.users.find_one({"id": admin_id}).get("is_active"))
        self.assertTrue(main.users.find_one({"id": student_id}).get("is_active"))

    def test_create_course_rejects_bad_payload(self):
        self._log("Posting invalid course term payload. Expecting HTTP 400.")
        response = self.client.post(
            "/courses",
            json={
                "name": "Broken",
                "instructor_ids": ["KSUID000000100"],
                "student_ids": ["KSUID000000100"],
                "semester": {"year": 2026, "term": "autumn"},
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_course_accepts_local_api_shape(self):
        self._log("Posting backend-style course payload. Expecting HTTP 201 and normalized storage.")
        response = self.client.post(
            "/courses",
            json={
                "id": 101,
                "code": "CS 4550",
                "name": "Cloud Computing",
                "instructor": "Dr. Priya Narayanan",
                "instructor_id": self.seeded_user_ids["instructor.local@kent.edu"],
                "semester": "Summer 2027",
                "color": "#1d4ed8",
                "members": [
                    {"id": self.seeded_user_ids["instructor.local@kent.edu"], "role": "instructor"},
                    {"id": self.seeded_user_ids["instructor.alt@kent.edu"], "role": "student"},
                ],
                "groups": [
                    {
                        "id": "group-cs4550-cloud",
                        "name": "Cloud Ops",
                        "memberIds": [self.seeded_user_ids["instructor.alt@kent.edu"]],
                    }
                ],
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 201)

        saved = main.courses.find_one({"id": 101})
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("semester"), "Summer 2027")
        self.assertEqual(saved.get("semester_obj", {}).get("term"), "summer")
        self.assertEqual(saved.get("is_active"), True)
        self.assertEqual(len(saved.get("members", [])), 2)
        self.assertEqual(len(saved.get("groups", [])), 1)

    def test_legacy_api_key_endpoint_removed(self):
        self._log("Posting to removed legacy /api_keys endpoint. Expecting HTTP 404.")
        response = self.client.post(
            "/api_keys",
            json={"u_id": "good.user@kent.edu", "c_id": "course-1", "expire": "not-iso"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_regenerate_api_key_returns_plaintext_once_and_stores_hash(self):
        self._log("Regenerating a course API key. Expecting plaintext response and hash-only storage.")
        response = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)

        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        plaintext_key = (payload or {}).get("api_key")
        self.assertTrue(isinstance(plaintext_key, str) and plaintext_key.startswith("sk_kent_"))
        self.assertNotIn("hash", payload or {})
        self.assertNotIn("u_id", payload or {})
        self.assertNotIn("created_by", payload or {})
        self.assertNotIn("c_id", payload or {})

        stored = main.api_keys.find_one({"course_id": 1, "owner_type": "person", "key_name": "key-1"})
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("hash"), hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest())
        self.assertEqual(stored.get("owner_type"), "person")
        self.assertTrue(stored.get("owner_id"))
        self.assertEqual(stored.get("course_id"), 1)
        self.assertEqual(stored.get("is_active"), True)
        self.assertNotIn("created_by", stored)

    def test_regenerate_group_api_key_tracks_group_and_creator(self):
        self._log("Regenerating a group-owned API key. Expecting group metadata and creator tracking.")
        response = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "group",
                "groupId": "group-se3010-a",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)

        payload = response.get_json() or {}
        self.assertEqual(payload.get("owner_type"), "group")
        self.assertTrue(payload.get("group_created_by"))

        stored = main.api_keys.find_one({"course_id": 1, "owner_type": "group", "owner_id": "group-se3010-a", "key_name": "key-1"})
        self.assertIsNotNone(stored)
        self.assertEqual(stored.get("owner_type"), "group")
        self.assertEqual(stored.get("owner_id"), "group-se3010-a")
        self.assertTrue(stored.get("group_created_by"))

    def test_student_can_generate_own_key_once_then_hits_cooldown(self):
        self._log("Generating a self-service API key as a student and verifying the cooldown blocks a second request.")
        first_response = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.student_headers,
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.student_headers,
        )
        self.assertEqual(second_response.status_code, 429)

        payload = second_response.get_json() or {}
        self.assertIn("wait", (payload.get("error") or "").lower())

    def test_api_key_cooldown_is_per_key_not_per_user(self):
        self._log("Generating a key as student and verifying same key owner/name cannot be overridden within cooldown window.")
        first_response = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.student_headers,
        )
        self.assertEqual(first_response.status_code, 200)

        student_second = self.client.post(
            "/courses/1/api-key/regenerate",
            headers=self.student_headers,
        )
        self.assertEqual(student_second.status_code, 429)

        payload = student_second.get_json() or {}
        self.assertIn("wait", (payload.get("error") or "").lower())

    def test_courses_include_has_api_key_state(self):
        self._log("Fetching course list and checking has_api_key toggles with delete/regenerate operations.")
        before = self.client.get("/courses", headers=self.admin_headers)
        self.assertEqual(before.status_code, 200)
        before_payload = before.get_json()
        self.assertIsInstance(before_payload, list)
        course_before = next((course for course in before_payload if course.get("id") == 1), None)
        self.assertIsNotNone(course_before)
        self.assertEqual(course_before.get("has_api_key"), True)

        delete_response = self.client.delete("/courses/1/api-key", headers=self.admin_headers)
        self.assertEqual(delete_response.status_code, 200)

        after_delete = self.client.get("/courses", headers=self.admin_headers)
        after_delete_payload = after_delete.get_json()
        self.assertIsInstance(after_delete_payload, list)
        course_after_delete = next((course for course in after_delete_payload if course.get("id") == 1), None)
        self.assertIsNotNone(course_after_delete)
        self.assertEqual(course_after_delete.get("has_api_key"), False)

        regenerate_response = self.client.post("/courses/1/api-key/regenerate", headers=self.admin_headers)
        self.assertEqual(regenerate_response.status_code, 200)

        after_regenerate = self.client.get("/courses", headers=self.admin_headers)
        after_regenerate_payload = after_regenerate.get_json()
        self.assertIsInstance(after_regenerate_payload, list)
        course_after_regenerate = next((course for course in after_regenerate_payload if course.get("id") == 1), None)
        self.assertIsNotNone(course_after_regenerate)
        self.assertEqual(course_after_regenerate.get("has_api_key"), True)

    def test_instructor_cannot_update_instructor_member_key_limit(self):
        self._log("Instructor tries to change another instructor key limit. Expecting HTTP 400.")
        response = self.client.patch(
            f"/courses/1/members/{self.seeded_user_ids['instructor.alt@kent.edu']}/key-limit",
            json={"keyLimit": 3},
            headers=self.instructor_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_cannot_set_member_key_limit_above_course_limit(self):
        self._log("Admin attempts to set member key limit above course key limit. Expecting HTTP 400.")
        response = self.client.patch(
            "/courses/2/members/student.alt2@kent.edu/key-limit",
            json={"keyLimit": 3},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json() or {}
        self.assertIn("cannot exceed", payload.get("error", ""))

    def test_admin_can_update_instructor_handout_limit(self):
        self._log("Admin updates course instructor handout limit and value persists on the course.")
        response = self.client.patch(
            "/courses/1/instructor-handout-limit",
            json={"instructorHandoutLimit": 2},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json() or {}
        self.assertEqual(payload.get("message"), "Instructor handout limit updated successfully.")

        updated_course = main.courses.find_one({"id": 1})
        self.assertIsNotNone(updated_course)
        self.assertEqual(updated_course.get("instructor_handout_limit"), 2)

    def test_non_admin_cannot_update_instructor_handout_limit(self):
        self._log("Instructor attempts to update instructor handout limit. Expecting HTTP 403.")
        response = self.client.patch(
            "/courses/1/instructor-handout-limit",
            json={"instructorHandoutLimit": 4},
            headers=self.instructor_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_handout_generation_ignores_handout_display_limit(self):
        self._log("Admin handouts are not blocked by the course-wide handout display limit.")

        set_limit_response = self.client.patch(
            "/courses/1/instructor-handout-limit",
            json={"instructorHandoutLimit": 2},
            headers=self.admin_headers,
        )
        self.assertEqual(set_limit_response.status_code, 200)

        first = self.client.post(
            "/courses/1/api-key/regenerate",
            json={"ownerType": "group", "groupId": "group-se3010-a", "keyName": "key-1", "slotIndex": 1},
            headers=self.admin_headers,
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/courses/1/api-key/regenerate",
            json={"ownerType": "person", "ownerId": "KSUID000000003", "keyName": "key-1", "slotIndex": 1},
            headers=self.admin_headers,
        )
        self.assertEqual(second.status_code, 200)

        third = self.client.post(
            "/courses/1/api-key/regenerate",
            json={"ownerType": "person", "ownerId": "KSUID000000004", "keyName": "key-1", "slotIndex": 1},
            headers=self.admin_headers,
        )
        self.assertEqual(third.status_code, 200)

    def test_admin_can_close_and_reopen_course_and_all_keys_follow_status(self):
        self._log("Admin closes and reopens a course. Expecting course and all keys to mirror is_active state.")

        close_response = self.client.patch(
            "/courses/1/status",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(close_response.status_code, 200)
        close_payload = close_response.get_json() or {}
        self.assertEqual(close_payload.get("is_active"), False)

        closed_keys = list(main.api_keys.find({"course_id": 1}))
        self.assertGreater(len(closed_keys), 0)
        self.assertTrue(all(key.get("is_active") is False for key in closed_keys))

        reopen_response = self.client.patch(
            "/courses/1/status",
            json={"is_active": True},
            headers=self.admin_headers,
        )
        self.assertEqual(reopen_response.status_code, 200)
        reopen_payload = reopen_response.get_json() or {}
        self.assertEqual(reopen_payload.get("is_active"), True)

        reopened_keys = list(main.api_keys.find({"course_id": 1}))
        self.assertGreater(len(reopened_keys), 0)
        self.assertTrue(all(key.get("is_active") is True for key in reopened_keys))

    def test_closed_course_rejects_mutating_endpoints(self):
        self._log("Closing a course and verifying write endpoints are rejected with HTTP 403.")

        close_response = self.client.patch(
            "/courses/1/status",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(close_response.status_code, 200)

        add_member_response = self.client.post(
            "/courses/1/members",
            json={"members": [{"email": "student.alt2@kent.edu"}]},
            headers=self.admin_headers,
        )
        self.assertEqual(add_member_response.status_code, 403)
        payload = add_member_response.get_json() or {}
        self.assertIn("closed", (payload.get("error") or "").lower())

    def test_non_admin_cannot_change_course_status(self):
        self._log("Instructor attempts to close a course. Expecting HTTP 403.")

        response = self.client.patch(
            "/courses/1/status",
            json={"is_active": False},
            headers=self.instructor_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_toggle_key_active_status_without_changing_hash(self):
        self._log("Toggling a key's active state should preserve its stored hash.")

        generate_response = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "person",
                "ownerId": "KSUID000000003",
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(generate_response.status_code, 200)

        before_toggle = main.api_keys.find_one(
            {
                "course_id": 1,
                "owner_type": "person",
                "owner_id": "ksuid000000003",
                "slot_index": 1,
            }
        )
        self.assertIsNotNone(before_toggle)
        original_hash = before_toggle.get("hash")
        self.assertTrue(isinstance(original_hash, str) and len(original_hash) == 64)

        deactivate_response = self.client.patch(
            "/courses/1/api-key/status",
            json={
                "ownerType": "person",
                "ownerId": "KSUID000000003",
                "keyName": "key-1",
                "slotIndex": 1,
                "isActive": False,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(deactivate_response.status_code, 200)

        deactivated_key = main.api_keys.find_one(
            {
                "course_id": 1,
                "owner_type": "person",
                "owner_id": "ksuid000000003",
                "slot_index": 1,
            }
        )
        self.assertIsNotNone(deactivated_key)
        self.assertEqual(deactivated_key.get("hash"), original_hash)
        self.assertEqual(deactivated_key.get("is_active"), False)

        activate_response = self.client.patch(
            "/courses/1/api-key/status",
            json={
                "ownerType": "person",
                "ownerId": "KSUID000000003",
                "keyName": "key-1",
                "slotIndex": 1,
                "isActive": True,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(activate_response.status_code, 200)

        activated_key = main.api_keys.find_one(
            {
                "course_id": 1,
                "owner_type": "person",
                "owner_id": "ksuid000000003",
                "slot_index": 1,
            }
        )
        self.assertIsNotNone(activated_key)
        self.assertEqual(activated_key.get("hash"), original_hash)
        self.assertEqual(activated_key.get("is_active"), True)


if __name__ == "__main__":
    import unittest

    unittest.main()
