from copy import deepcopy
from unittest.mock import patch

from test_support import BackendTestCase, main
from test_api_rocky_auth import api_rocky
from backend.route_handlers import audit, courses as handlers
from rocky_common.course_keys import key_is_active


class CourseKeyPolicyTests(BackendTestCase):
    group_path = "/courses/1/groups/group-se3010-a"

    def setUp(self):
        super().setUp()
        for name, value in (("api_keys_col", main.api_keys), ("courses_col", main.courses),
                            ("users_col", main.users), ("MONGITA_KEY_READ_REFRESH_ENABLED", False)):
            p = patch.object(api_rocky, name, value)
            p.start()
            self.addCleanup(p.stop)
        result = self.client.post("/courses/1/api-key/regenerate", json={
            "ownerType": "group", "groupId": "group-se3010-a", "slotIndex": 1,
        }, headers=self.instructor_headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.key = result.json["api_key"]
        self.key_id = result.json["key_id"]

    def _patch(self, path, payload):
        response = self.client.patch(path, json=payload, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.json)
        return response

    def _assert_access(self, allowed):
        self.assertEqual(api_rocky.get_key_doc(self.key) is not None, allowed)
        summary = self.client.get("/courses/1/api-keys", headers=self.admin_headers)
        self.assertEqual(summary.status_code, 200)
        key = next(k for k in summary.json if k["key_id"] == self.key_id)
        self.assertEqual(key["is_active"], allowed)

    def _interleave_after_save(self, nested):
        original = handlers.save_course_changes
        raced = False

        def save(*args):
            nonlocal raced
            result = original(*args)
            if result and not raced:
                raced = True
                nested()
            return result
        return patch.object(handlers, "save_course_changes", side_effect=save)

    def test_overlapping_reopen_and_close_cannot_reenable_a_closed_course_key(self):
        self._patch("/courses/1/status", {"is_active": False})
        before = list(main.api_keys.find())
        with self._interleave_after_save(lambda: self._patch("/courses/1/status", {"is_active": False})):
            self._patch("/courses/1/status", {"is_active": True})
        self.assertFalse(main.courses.find_one({"id": 1})["is_active"])
        self._assert_access(False)
        self.assertEqual(list(main.api_keys.find()), before)
        self._patch("/courses/1/status", {"is_active": True})
        self._assert_access(True)

    def test_overlapping_limit_updates_cannot_enable_a_key_above_final_limit(self):
        path = self.group_path + "/key-limit"
        self._patch(path, {"keyLimit": 0})
        before = list(main.api_keys.find())
        with self._interleave_after_save(lambda: self._patch(path, {"keyLimit": 0})):
            self._patch(path, {"keyLimit": 1})
        self.assertEqual(main.courses.find_one({"id": 1})["groups"][0]["key_limit"], 0)
        self._assert_access(False)
        self.assertEqual(list(main.api_keys.find()), before)

    def test_existing_automatic_disable_flags_use_current_policy(self):
        for reason in ("course", "limit"):
            with self.subTest(reason=reason):
                main.api_keys.update_one({"key_id": self.key_id}, {"$set": {"is_active": False, "disabled_reason": reason}})
                self._assert_access(True)
                self._patch(self.group_path + "/key-limit", {"keyLimit": 0})
                self._assert_access(False)
                self._patch(self.group_path + "/key-limit", {"keyLimit": 1})
                self._assert_access(True)

    def test_manual_disabling_and_revocation_are_never_undone_by_policy(self):
        for reason in ("manual", "account-inactive", "membership"):
            with self.subTest(reason=reason):
                main.api_keys.update_one({"key_id": self.key_id}, {"$set": {"is_active": False, "disabled_reason": reason}})
                self._patch("/courses/1/status", {"is_active": False})
                self._patch("/courses/1/status", {"is_active": True})
                self._assert_access(False)
        main.api_keys.update_one({"key_id": self.key_id}, {"$set": {
            "is_active": True, "deleted_at": "2026-01-01T00:00:00Z",
        }})
        self._assert_access(False)

    def test_missing_course_group_or_policy_store_never_grants_access(self):
        original = main.courses.find_one({"id": 1})
        main.courses.update_one({"id": 1}, {"$set": {"groups": []}})
        self._assert_access(False)
        main.courses.replace_one({"_id": original["_id"]}, original)
        with patch.object(api_rocky, "courses_col", None):
            self.assertIsNone(api_rocky.get_key_doc(self.key))
        main.courses.delete_one({"id": 1})
        self.assertIsNone(api_rocky.get_key_doc(self.key))

    def test_account_suspension_overrides_old_automatic_flags_after_reactivation(self):
        generated = self.client.post("/courses/1/api-key/regenerate", json={}, headers=self.student_headers)
        self.assertEqual(generated.status_code, 200)
        key_id = generated.json["key_id"]
        main.api_keys.update_one({"key_id": key_id}, {"$set": {"is_active": False, "disabled_reason": "course"}})
        user_id = self.seeded_user_ids["student.local@kent.edu"]
        for active in (False, True):
            self.assertEqual(self.client.put(f"/users/{user_id}", json={"is_active": active}, headers=self.admin_headers).status_code, 200)
            self.assertIsNone(api_rocky.get_key_doc(generated.json["api_key"]))
        self.assertEqual(main.api_keys.find_one({"key_id": key_id})["disabled_reason"], "account-inactive")

    def test_person_and_staff_limits_use_same_policy_as_group_limits(self):
        for headers, owner, path, field in (
            (self.student_headers, self.seeded_user_ids["student.local@kent.edu"],
             f'/courses/1/members/{self.seeded_user_ids["student.local@kent.edu"]}/key-limit', "keyLimit"),
            (self.instructor_headers, self.seeded_user_ids["instructor.local@kent.edu"],
             "/courses/1/instructor-key-limit", "instructorKeyLimit"),
        ):
            with self.subTest(owner=owner):
                response = self.client.post("/courses/1/api-key/regenerate", json={"ownerId": owner}, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertIsNotNone(api_rocky.get_key_doc(response.json["api_key"]))
                self._patch(path, {field: 0})
                self.assertIsNone(api_rocky.get_key_doc(response.json["api_key"]))
                self._patch(path, {field: 1})
                self.assertIsNotNone(api_rocky.get_key_doc(response.json["api_key"]))

    def test_handout_limit_admin_self_key_and_non_course_keys(self):
        response = self.client.post("/courses/1/api-key/regenerate", json={}, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(api_rocky.get_key_doc(response.json["api_key"]))
        self._patch("/courses/1/instructor-handout-limit", {"instructorHandoutLimit": 0})
        self._assert_access(False)
        self.assertIsNotNone(api_rocky.get_key_doc(response.json["api_key"]))
        for scope in ("service", "user-default"):
            self.assertTrue(key_is_active({"key_scope": scope, "is_active": True}))
            self.assertFalse(key_is_active({"key_scope": scope, "is_active": False}))


class MembershipAuditRecoveryTests(BackendTestCase):
    group_path = "/courses/1/groups/group-se3010-a"

    def setUp(self):
        super().setUp()
        course = self._course()
        course["groups"][0].update(memberIds=[], self_join_enabled=True)
        main.courses.replace_one({"_id": course["_id"]}, course)

    def _course(self):
        return main.courses.find_one({"id": 1})

    def _join(self, email="student.local@kent.edu"):
        return self.client.post(self.group_path + "/join", json={}, headers={"X-Rocky-User-Email": email})

    def _events(self, event="course-group-self-joined"):
        return list(main.api_history.find({"event_type": event}))

    def test_join_and_bulk_add_survive_audit_write_failure_and_retry(self):
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                self.setUp()
                event = "course-group-members-added" if bulk else "course-group-self-joined"
                def submit():
                    return self.client.post(self.group_path + "/members", json={"memberIds": ["student.local@kent.edu"]}, headers=self.instructor_headers) if bulk else self._join()
                with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
                    response = submit()
                self.assertEqual(response.status_code, 200, response.json)
                self.assertNotIn(audit.PENDING_COURSE_AUDIT, response.json)
                pending = self._course()[audit.PENDING_COURSE_AUDIT]
                self.assertEqual(len(pending), 1)
                self.assertEqual(self._events(event), [])
                self.assertEqual(submit().status_code, 200)
                self.assertEqual(self._events(event), pending)
                self.assertEqual(self._course()[audit.PENDING_COURSE_AUDIT], [])
                self.assertEqual(submit().status_code, 200)
                self.assertEqual(len(self._events(event)), 1)

    def test_lost_insert_acknowledgement_does_not_duplicate_event(self):
        original = main.api_history.insert_one
        def uncertain(event):
            original(event)
            raise RuntimeError("ack lost")
        with patch.object(main.api_history, "insert_one", side_effect=uncertain):
            self.assertEqual(self._join().status_code, 200)
        self.assertEqual(len(self._events()), 1)
        self.assertTrue(self._course()[audit.PENDING_COURSE_AUDIT])
        self.assertEqual(self._join().status_code, 200)
        self.assertEqual(len(self._events()), 1)
        self.assertEqual(self._course()[audit.PENDING_COURSE_AUDIT], [])

    def test_audit_read_recovers_original_actor_and_timestamp_after_restart(self):
        with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
            self.assertEqual(self._join().status_code, 200)
        event = deepcopy(self._course()[audit.PENDING_COURSE_AUDIT][0])
        self.assertNotIn(audit.PENDING_COURSE_AUDIT, self.client.get("/courses/1", headers=self.student_headers).json)
        response = self.client.get("/audit-logs", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._events(), [event])
        self.assertEqual(event["meta"]["actor_email"], "student.local@kent.edu")

    def test_join_settings_recover_through_course_history(self):
        with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
            response = self.client.patch(self.group_path + "/join-settings", json={
                "self_join_enabled": False, "max_members": 3,
            }, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200)
        event = deepcopy(self._course()[audit.PENDING_COURSE_AUDIT][0])
        self.assertEqual(self.client.get("/courses/1/api-history", headers=self.admin_headers).status_code, 200)
        self.assertEqual(self._events("course-group-join-settings-updated"), [event])

    def test_partially_delivered_large_batch_retries_without_loss_or_duplicates(self):
        emails = [f"audit-student-{index}@kent.edu" for index in range(125)]
        added = self.client.post("/courses/1/members", json={"members": [{"email": email} for email in emails]}, headers=self.instructor_headers)
        self.assertEqual(added.status_code, 200)
        original = main.api_history.insert_one
        calls = 0
        def insert(event):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second chunk failed")
            return original(event)
        with patch.object(main.api_history, "insert_one", side_effect=insert):
            response = self.client.post(self.group_path + "/members", json={"memberIds": emails}, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._events("course-group-members-added")), 1)
        self.assertEqual(len(self._course()[audit.PENDING_COURSE_AUDIT]), 2)
        retry = self.client.post(self.group_path + "/members", json={"memberIds": emails}, headers=self.instructor_headers)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json["added_count"], 0)
        events = self._events("course-group-members-added")
        self.assertEqual(len(events), 2)
        recorded = [email for event in events for email in event["meta"]["changes"]["member_ids"]]
        self.assertEqual(recorded, emails)

    def test_concurrent_join_during_cleanup_does_not_lose_new_event(self):
        original = main.courses.update_one
        raced = False
        def update(query, change, *args, **kwargs):
            nonlocal raced
            if change.get("$set") == {audit.PENDING_COURSE_AUDIT: []} and not raced:
                raced = True
                self.assertEqual(self._join("student.alt1@kent.edu").status_code, 200)
            return original(query, change, *args, **kwargs)
        with patch.object(main.courses, "update_one", side_effect=update):
            self.assertEqual(self._join().status_code, 200)
        self.assertEqual(len(self._events()), 2)
        self.assertEqual(len(self._course()["groups"][0]["memberIds"]), 2)
        self.assertEqual(self._course()[audit.PENDING_COURSE_AUDIT], [])

    def test_full_backlog_blocks_more_changes_but_recovers_without_manual_cleanup(self):
        with patch.object(audit, "MAX_PENDING_COURSE_EVENTS", 1):
            with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
                self.assertEqual(self._join().status_code, 200)
                self.assertEqual(self._join("student.alt1@kent.edu").status_code, 503)
                self.assertEqual(self._course()["groups"][0]["memberIds"], ["student.local@kent.edu"])
            self.assertEqual(self._join("student.alt1@kent.edu").status_code, 200)
        self.assertEqual(len(self._events()), 2)

    def test_course_cannot_be_deleted_with_undelivered_membership_events(self):
        with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
            self.assertEqual(self._join().status_code, 200)
            self.assertEqual(self.client.delete("/courses/1", headers=self.admin_headers).status_code, 503)
        self.assertIsNotNone(self._course())
        self.assertEqual(self.client.delete("/courses/1", headers=self.admin_headers).status_code, 200)
        self.assertEqual(len(self._events()), 1)
        self.assertIsNone(self._course())

    def test_conflicted_join_never_creates_a_false_audit_event(self):
        with patch.object(handlers, "save_course_changes", return_value=False):
            self.assertEqual(self._join().status_code, 409)
        self.assertEqual(self._events(), [])
        self.assertFalse(self._course().get(audit.PENDING_COURSE_AUDIT))

    def test_join_after_delete_precheck_preserves_the_course_and_its_event(self):
        original = main.courses.delete_many
        def delete(query):
            with patch.object(main.api_history, "insert_one", side_effect=RuntimeError("audit down")):
                self.assertEqual(self._join().status_code, 200)
            return original(query)
        with patch.object(main.courses, "delete_many", side_effect=delete):
            response = self.client.delete("/courses/1", headers=self.admin_headers)
        self.assertEqual(response.status_code, 409)
        self.assertIsNotNone(self._course())
        self.assertTrue(self._course()[audit.PENDING_COURSE_AUDIT])
        self.assertEqual(self.client.get("/audit-logs", headers=self.admin_headers).status_code, 200)
        self.assertEqual(len(self._events()), 1)
