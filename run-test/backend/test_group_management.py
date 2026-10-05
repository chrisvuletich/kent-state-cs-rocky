from copy import deepcopy
from unittest.mock import patch

from backend.course_actions import save_course_changes
from backend.route_handlers import audit, courses as handlers
from test_api_rocky_auth import api_rocky
from test_support import BackendTestCase, main


class GroupManagementTests(BackendTestCase):
    path = "/courses/1/groups/group-se3010-a"

    def setUp(self):
        super().setUp()
        for name, value in (("api_keys_col", main.api_keys), ("courses_col", main.courses),
                            ("users_col", main.users), ("MONGITA_KEY_READ_REFRESH_ENABLED", False)):
            p = patch.object(api_rocky, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _course(self):
        return main.courses.find_one({"id": 1})

    def _patch(self, data, headers=None):
        return self.client.patch(self.path, json=data, headers=self.instructor_headers if headers is None else headers)

    def _key(self):
        response = self.client.post("/courses/1/api-key/regenerate", json={
            "ownerType": "group", "groupId": "group-se3010-a", "slotIndex": 1,
        }, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def _access(self, key, allowed):
        self.assertEqual(api_rocky.get_key_doc(key["api_key"]) is not None, allowed)
        summary = self.client.get("/courses/1/api-keys", headers=self.admin_headers)
        self.assertEqual(next(k for k in summary.json if k["key_id"] == key["key_id"])["is_active"], allowed)

    def test_settings_are_atomic_and_rename_preserves_identity_members_and_keys(self):
        key = self._key()
        before = self._course()["groups"][0]
        keys = list(main.api_keys.find())
        response = self._patch({"name": "  Renamed team  ", "self_join_enabled": True, "max_members": 5, "key_limit": 2})
        self.assertEqual(response.status_code, 200, response.json)
        group = response.json["group"]
        self.assertEqual(group["id"], before["id"])
        self.assertEqual(group["memberIds"], before["memberIds"])
        self.assertEqual(group["name"], "Renamed team")
        self.assertEqual(group["key_limit"], 2)
        self.assertEqual(list(main.api_keys.find()), keys)
        self._access(key, True)
        self.assertTrue(main.api_history.find_one({"event_type": "course-group-updated"}))
        saved = self._course()
        self.assertEqual(self._patch({"name": "Bad save", "max_members": 1}).status_code, 400)
        self.assertEqual(self._course(), saved)

    def test_pause_blocks_keys_and_new_joins_but_staff_can_manage(self):
        key = self._key()
        keys = list(main.api_keys.find())
        self.assertEqual(self._patch({"is_active": False, "self_join_enabled": True}).status_code, 200)
        self._access(key, False)
        self.assertEqual(list(main.api_keys.find()), keys)
        course = self._course()
        course["groups"][0]["memberIds"] = []
        main.courses.replace_one({"_id": course["_id"]}, course)
        joined = self.client.post(self.path + "/join", json={}, headers=self.student_headers)
        self.assertEqual(joined.status_code, 403)
        self.assertIn("paused", joined.json["error"])
        assigned = self.client.post(self.path + "/members", json={"memberIds": ["student.local@kent.edu"]}, headers=self.instructor_headers)
        self.assertEqual(assigned.status_code, 200, assigned.json)
        self.assertEqual(self._patch({"name": "Still editable"}).status_code, 200)
        self.assertEqual(self._patch({"is_active": True}).status_code, 200)
        self._access(key, True)

    def test_close_joining_does_not_disable_keys_or_remove_members(self):
        key = self._key()
        members = self._course()["groups"][0]["memberIds"]
        self.assertEqual(self._patch({"self_join_enabled": False}).status_code, 200)
        self._access(key, True)
        self.assertEqual(self._course()["groups"][0]["memberIds"], members)

    def test_resume_preserves_manual_disable_revocation_and_course_limit(self):
        key = self._key()
        for flags in ({"is_active": False, "disabled_reason": "manual"},
                      {"is_active": False, "disabled_reason": "membership", "deleted_at": "2026-10-05"}):
            main.api_keys.update_one({"key_id": key["key_id"]}, {"$set": flags})
            self.assertEqual(self._patch({"is_active": False}).status_code, 200)
            self.assertEqual(self._patch({"is_active": True}).status_code, 200)
            self._access(key, False)
        main.api_keys.update_one({"key_id": key["key_id"]}, {"$set": {"is_active": True, "deleted_at": None}})
        self.assertEqual(self._patch({"is_active": False, "key_limit": 0}).status_code, 200)
        self.assertEqual(self._patch({"is_active": True}).status_code, 200)
        self._access(key, False)

    def test_pause_does_not_affect_personal_keys(self):
        result = self.client.post("/courses/1/api-key/regenerate", json={}, headers=self.student_headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self._patch({"is_active": False}).status_code, 200)
        self.assertIsNotNone(api_rocky.get_key_doc(result.json["api_key"]))

    def test_paused_group_cannot_generate_or_enable_shared_keys(self):
        key = self._key()
        self.assertEqual(self._patch({"is_active": False}).status_code, 200)
        owner = {"ownerType": "group", "ownerId": "group-se3010-a", "slotIndex": 1}
        for method, endpoint, body in (("post", "regenerate", owner), ("patch", "status", {**owner, "isActive": True})):
            response = getattr(self.client, method)(f"/courses/1/api-key/{endpoint}", json=body, headers=self.instructor_headers)
            self.assertEqual(response.status_code, 403, response.json)
        self._access(key, False)

    def test_delete_with_members_preserves_enrollment_history_and_unrelated_keys(self):
        key = self._key()
        before = self._course()
        main.api_history.insert_one({"event_type": "chat-response", "course_id": 1, "group_id": "group-se3010-a"})
        unrelated = [k for k in main.api_keys.find() if k.get("key_id") != key["key_id"]]
        response = self.client.delete(self.path, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self._course()["members"], before["members"])
        self.assertEqual(self._course()["groups"], before["groups"][1:])
        self._access(key, False)
        self.assertEqual(main.api_keys.find_one({"key_id": key["key_id"]})["hash"], "")
        self.assertEqual([k for k in main.api_keys.find() if k.get("key_id") != key["key_id"]], unrelated)
        self.assertTrue(main.api_history.find_one({"event_type": "chat-response", "group_id": "group-se3010-a"}))
        self.assertTrue(main.api_history.find_one({"event_type": "course-group-deleted"}))
        recreated = self.client.post("/courses/1/groups", json={"name": before["groups"][0]["name"]}, headers=self.instructor_headers)
        self.assertEqual(recreated.status_code, 200)
        self.assertNotEqual(recreated.json["groups"][-1]["id"], "group-se3010-a")
        self._access(key, False)

    def test_missing_group_policy_denies_even_when_hash_cleanup_fails(self):
        key = self._key()
        with patch.object(handlers, "_revoke_course_owner_keys", side_effect=RuntimeError("storage down")):
            self.assertEqual(self.client.delete(self.path, headers=self.instructor_headers).status_code, 200)
        self._access(key, False)

    def test_permissions_closed_course_missing_group_and_invalid_input(self):
        before = self._course()
        for headers, status in (({}, 401), (self.student_headers, 403), ({"X-Rocky-User-Email": "instructor.alt@kent.edu"}, 403)):
            self.assertEqual(self._patch({"name": "No"}, headers).status_code, status)
            self.assertEqual(self.client.delete(self.path, headers=headers).status_code, status)
        for data in ({}, [], {"name": ""}, {"name": 2}, {"name": "a" * 121}, {"is_active": 0},
                     {"key_limit": True}, {"key_limit": -1}, {"key_limit": 3}, {"key_limit": 1.5},
                     {"self_join_enabled": "true"}, {"max_members": 0}, {"max_members": True}, {"id": "changed"}, {"memberIds": []}):
            with self.subTest(data=data):
                self.assertEqual(self._patch(data).status_code, 400)
                self.assertEqual(self._course(), before)
        main.courses.update_one({"id": 1}, {"$set": {"is_active": False}})
        self.assertEqual(self._patch({"name": "No"}).status_code, 403)
        self.assertEqual(self.client.delete(self.path, headers=self.admin_headers).status_code, 403)
        main.courses.update_one({"id": 1}, {"$set": {"is_active": True, "groups": []}})
        self.assertEqual(self._patch({"name": "No"}).status_code, 404)
        self.assertEqual(self.client.delete(self.path, headers=self.admin_headers).status_code, 404)

    def test_teaching_assistants_and_admins_can_manage(self):
        main.courses.update_one({"id": 1}, {"$set": {"ta_emails": ["instructor.alt@kent.edu"]}})
        self.assertEqual(self._patch({"name": "TA renamed"}, {"X-Rocky-User-Email": "instructor.alt@kent.edu"}).status_code, 200)
        self.assertEqual(self._patch({"is_active": False}, self.admin_headers).status_code, 200)

    def test_concurrent_join_prevents_stale_edit_or_delete(self):
        for deleting in (False, True):
            before = self._course()
            def competing(collection, old, new):
                changed = deepcopy(old)
                changed["groups"][0]["memberIds"].append(f"concurrent-{deleting}@kent.edu")
                self.assertTrue(save_course_changes(collection, old, changed))
                return save_course_changes(collection, old, new)
            with patch.object(handlers, "save_course_changes", side_effect=competing):
                response = self.client.delete(self.path, headers=self.instructor_headers) if deleting else self._patch({"name": "Stale"})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self._course()["groups"][0]["name"], before["groups"][0]["name"])
            self.assertIn(f"concurrent-{deleting}@kent.edu", self._course()["groups"][0]["memberIds"])

    def test_join_retry_observes_new_pause_or_deletion(self):
        for deleting in (False, True):
            original = self._course()
            original["groups"][0].update(memberIds=[], self_join_enabled=True, is_active=True)
            main.courses.replace_one({"_id": original["_id"]}, original)
            def competing(collection, old, new):
                changed = deepcopy(old)
                if deleting:
                    changed["groups"] = changed["groups"][1:]
                else:
                    changed["groups"][0]["is_active"] = False
                self.assertTrue(save_course_changes(collection, old, changed))
                return save_course_changes(collection, old, new)
            with patch.object(handlers, "save_course_changes", side_effect=competing):
                response = self.client.post(self.path + "/join", json={}, headers=self.student_headers)
            self.assertEqual(response.status_code, 404 if deleting else 403)

    def test_audit_outage_retries_original_group_event_without_exposing_pending_data(self):
        with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit offline")):
            response = self._patch({"name": "Audited name"})
        self.assertEqual(response.status_code, 200)
        pending = self._course()[audit.PENDING_COURSE_AUDIT]
        self.assertEqual(len(pending), 1)
        self.assertNotIn(audit.PENDING_COURSE_AUDIT, str(response.json))
        self.assertEqual(self._patch({"is_active": False}).status_code, 200)
        self.assertEqual(self._course().get(audit.PENDING_COURSE_AUDIT), [])
        self.assertEqual(main.api_history.count_documents({"event_type": "course-group-updated"}), 2)

    def test_new_groups_respect_zero_course_key_allowance(self):
        main.courses.update_one({"id": 1}, {"$set": {"instructor_handout_limit": 0}})
        response = self.client.post("/courses/1/groups", json={"name": "No keys"}, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["groups"][-1]["key_limit"], 0)

    def test_key_generated_during_group_deletion_is_never_delivered_or_authorized(self):
        original_generate = main.regenerate_course_api_key
        generated = []
        def delete_before_insert(course, *args):
            current = self._course()
            current["groups"] = current["groups"][1:]
            main.courses.replace_one({"_id": current["_id"]}, current)
            result = original_generate(course, *args)
            generated.append(result)
            return result
        with patch.object(main, "regenerate_course_api_key", side_effect=delete_before_insert):
            response = self.client.post("/courses/1/api-key/regenerate", json={
                "ownerType": "group", "groupId": "group-se3010-a", "slotIndex": 1,
            }, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("api_key", response.json)
        self.assertIsNone(api_rocky.get_key_doc(generated[0]["api_key"]))

    def test_removal_resolves_both_account_id_and_email_aliases(self):
        key = self._key()
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        course = self._course()
        course["groups"][0]["memberIds"] = [student_id, "student.local@kent.edu"]
        main.courses.replace_one({"_id": course["_id"]}, course)
        response = self.client.delete(self.path + "/members", json={"id": student_id}, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self._course()["groups"][0]["memberIds"], [])
        self._access(key, False)
