from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from test_support import BackendTestCase, main
from backend.course_actions import save_course_changes
from backend import course_actions
from backend.route_handlers import courses as course_handlers


class GroupSelfJoinTests(BackendTestCase):
    path = "/courses/1/groups/group-se3010-a"

    def _course(self):
        return main.courses.find_one({"id": 1})

    def _group(self):
        return self._course()["groups"][0]

    def _events(self, name="course-group-self-joined"):
        return list(main.api_history.find({"event_type": name}))

    def _prepare(self, limit=None, enabled=True):
        course = self._course()
        course["groups"][0].update({"memberIds": [], "self_join_enabled": enabled, "max_members": limit})
        main.courses.replace_one({"_id": course["_id"]}, course)

    def _join(self, headers=None, body=None):
        return self.client.post(self.path + "/join", json={} if body is None else body,
                                headers=self.student_headers if headers is None else headers)

    def _settings(self, enabled, limit, headers=None):
        return self.client.patch(self.path + "/join-settings",
                                 json={"self_join_enabled": enabled, "max_members": limit},
                                 headers=self.instructor_headers if headers is None else headers)

    def test_defaults_are_closed_and_staff_can_enable(self):
        self._prepare(enabled=False)
        self.assertEqual(self._join().status_code, 403)
        enabled = self._settings(True, 4)
        self.assertEqual(enabled.status_code, 200, enabled.json)
        self.assertTrue(enabled.json["group"]["self_join_enabled"])
        self.assertEqual(self._events("course-group-join-settings-updated")[0]["meta"]["changes"]["max_members"], 4)
        self.assertEqual(self._join().status_code, 200)
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])

    def test_old_and_new_groups_default_to_instructor_assignment(self):
        old_course = self._course()
        old_course["groups"][0]["memberIds"] = []
        main.courses.replace_one({"_id": old_course["_id"]}, old_course)
        self.assertEqual(self._join().status_code, 403)
        created = self.client.post("/courses/1/groups", json={"name": "New group"}, headers=self.instructor_headers)
        self.assertEqual(created.status_code, 200)
        self.assertIs(created.json["groups"][-1]["self_join_enabled"], False)
        self.assertIsNone(created.json["groups"][-1]["max_members"])

    def test_repeat_join_is_idempotent_and_does_not_touch_keys(self):
        self._prepare(limit=1)
        before_keys = list(main.api_keys.find())
        first = self._join()
        self.assertEqual(first.status_code, 200, first.json)
        self.assertFalse(first.json["already_member"])
        self.assertEqual(self._settings(False, 1).status_code, 200)
        repeat = self._join()
        self.assertEqual(repeat.status_code, 200)
        self.assertTrue(repeat.json["already_member"])
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])
        self.assertEqual(len(self._events()), 1)
        self.assertEqual(self._events()[0]["meta"]["changes"]["member_id"], "student.local@kent.edu")
        self.assertEqual(list(main.api_keys.find()), before_keys)

    def test_cannot_join_on_behalf_of_another_student_or_change_settings(self):
        self._prepare()
        before = self._course()
        for body in ({"id": "student.alt1@kent.edu"}, {"email": "student.alt1@kent.edu"}, {"memberIds": []}, [], "", {"self_join_enabled": True}):
            with self.subTest(body=body):
                self.assertEqual(self._join(body=body).status_code, 400)
                self.assertEqual(self._course(), before)
        self.assertEqual(self._settings(True, 3, self.student_headers).status_code, 403)
        self.assertEqual(self.client.post(self.path + "/members", json={"memberIds": ["student.local@kent.edu"]}, headers=self.student_headers).status_code, 403)
        self.assertEqual(self.client.delete(self.path + "/members", json={"id": "student.local@kent.edu"}, headers=self.student_headers).status_code, 403)

    def test_only_active_enrolled_students_may_join(self):
        self._prepare()
        for headers, expected in (({}, 401), (self.admin_headers, 403), (self.instructor_headers, 403),
                                  ({"X-Rocky-User-Email": "nobody@kent.edu"}, 403)):
            with self.subTest(headers=headers):
                self.assertEqual(self._join(headers).status_code, expected)
        main.courses.update_one({"id": 1}, {"$set": {"ta_emails": ["student.local@kent.edu"]}})
        self.assertEqual(self._join().status_code, 403)
        main.courses.update_one({"id": 1}, {"$set": {"ta_emails": []}})
        main.users.update_one({"email": "student.local@kent.edu"}, {"$set": {"is_active": False}})
        self.assertEqual(self._join().status_code, 403)
        main.users.update_one({"email": "student.local@kent.edu"}, {"$set": {"is_active": True}})
        course = self._course()
        course["members"] = [member for member in course["members"] if member["email"] != "student.local@kent.edu"]
        main.courses.replace_one({"_id": course["_id"]}, course)
        self.assertEqual(self._join().status_code, 403)
        self.assertEqual(self._events(), [])

    def test_course_closed_or_missing_group_rejects_join_and_settings(self):
        self._prepare()
        main.courses.update_one({"id": 1}, {"$set": {"is_active": False}})
        self.assertEqual(self._join().status_code, 403)
        self.assertEqual(self._settings(True, 2).status_code, 403)
        main.courses.update_one({"id": 1}, {"$set": {"is_active": True, "groups": []}})
        self.assertEqual(self._join().status_code, 404)
        self.assertEqual(self._settings(True, 2).status_code, 404)
        main.courses.delete_one({"id": 1})
        self.assertEqual(self._join().status_code, 404)

    def test_pending_roster_entry_matches_the_authenticated_email(self):
        self._prepare()
        course = self._course()
        for member in course["members"]:
            if member["email"] == "student.local@kent.edu":
                member["id"] = None
                member["name"] = None
        main.courses.replace_one({"_id": course["_id"]}, course)
        self.assertEqual(self._join().status_code, 200)
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])

    def test_settings_validate_types_capacity_and_permissions(self):
        before = self._course()
        for enabled, limit in (("true", 4), (1, 4), (None, 4), (True, 0), (True, -1), (True, 1.5), (True, True), (True, "3"), (True, 1), (True, 2**64)):
            with self.subTest(enabled=enabled, limit=limit):
                self.assertEqual(self._settings(enabled, limit).status_code, 400)
                self.assertEqual(self._course(), before)
        self.assertEqual(self._settings(True, None, self.admin_headers).status_code, 200)
        main.courses.update_one({"id": 1}, {"$set": {"ta_ids": [self.seeded_user_ids["instructor.alt@kent.edu"]]}})
        ta_headers = {"X-Rocky-User-Email": "instructor.alt@kent.edu", "X-Rocky-User-Is-Admin": "false"}
        self.assertEqual(self._settings(False, None, ta_headers).status_code, 200)
        self.assertEqual(self._group()["memberIds"], before["groups"][0]["memberIds"])

    def test_size_limit_applies_to_staff_batches_without_partial_addition(self):
        self._prepare(limit=1)
        response = self.client.post(self.path + "/members", json={"memberIds": ["student.local@kent.edu", "student.alt1@kent.edu"]}, headers=self.instructor_headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._group()["memberIds"], [])

    def test_multiple_group_memberships_are_preserved(self):
        course = self._course()
        course["groups"].append({"id": "other", "name": "Other", "memberIds": [], "key_limit": 1, "self_join_enabled": True})
        main.courses.replace_one({"_id": course["_id"]}, course)
        response = self.client.post("/courses/1/groups/other/join", json={}, headers=self.student_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("student.local@kent.edu", self._group()["memberIds"])
        self.assertEqual(self._course()["groups"][-1]["memberIds"], ["student.local@kent.edu"])

    def test_competing_join_cannot_take_the_last_seat_twice(self):
        self._prepare(limit=1)
        raced = False

        def competing_save(collection, before, after):
            nonlocal raced
            if not raced:
                raced = True
                other = deepcopy(before)
                other["groups"][0]["memberIds"] = ["student.alt1@kent.edu"]
                self.assertTrue(save_course_changes(collection, before, other))
            return save_course_changes(collection, before, after)

        with patch.object(course_handlers, "save_course_changes", side_effect=competing_save):
            response = self._join()
        self.assertEqual(response.status_code, 409)
        self.assertIn("full", response.json["error"])
        self.assertEqual(self._group()["memberIds"], ["student.alt1@kent.edu"])
        self.assertEqual(self._events(), [])

    def test_join_retries_after_another_join_when_space_remains(self):
        self._prepare(limit=3)
        raced = False

        def competing_save(collection, before, after):
            nonlocal raced
            if not raced:
                raced = True
                other = deepcopy(before)
                other["groups"][0]["memberIds"] = ["student.alt1@kent.edu"]
                self.assertTrue(save_course_changes(collection, before, other))
            return save_course_changes(collection, before, after)

        with patch.object(course_handlers, "save_course_changes", side_effect=competing_save):
            response = self._join()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._group()["memberIds"], ["student.alt1@kent.edu", "student.local@kent.edu"])
        self.assertEqual(len(self._events()), 1)

    def test_join_rechecks_policy_enrollment_and_closed_state_after_conflict(self):
        for change, expected in (("policy", 403), ("roster", 403), ("closed", 403), ("deleted", 404)):
            with self.subTest(change=change):
                self._prepare()

                def conflicting_save(collection, before, after):
                    other = deepcopy(before)
                    if change == "policy":
                        other["groups"][0]["self_join_enabled"] = False
                    elif change == "roster":
                        other["members"] = []
                    elif change == "closed":
                        other["is_active"] = False
                    else:
                        other["groups"] = []
                    self.assertTrue(save_course_changes(collection, before, other))
                    return save_course_changes(collection, before, after)

                original = self._course()
                with patch.object(course_handlers, "save_course_changes", side_effect=conflicting_save):
                    self.assertEqual(self._join().status_code, expected)
                self.assertEqual(self._events(), [])
                main.courses.replace_one({"_id": original["_id"]}, original)

    def test_retries_are_bounded(self):
        self._prepare()
        with patch.object(course_handlers, "save_course_changes", return_value=False) as save:
            self.assertEqual(self._join().status_code, 409)
            self.assertEqual(save.call_count, 3)
        self.assertEqual(self._events(), [])

    def test_staff_settings_do_not_overwrite_concurrent_join(self):
        self._prepare()
        original_settings = course_handlers.update_group_join_settings

        def racing_settings(*args):
            result = original_settings(*args)
            self.assertEqual(self._join().status_code, 200)
            return result

        with patch.object(course_handlers, "update_group_join_settings", side_effect=racing_settings):
            response = self._settings(False, 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])
        self.assertTrue(self._group()["self_join_enabled"])
        self.assertEqual(self._events("course-group-join-settings-updated"), [])

    def test_membership_removal_remains_staff_only_and_revokes_shared_keys(self):
        self._prepare()
        self.assertEqual(self._join().status_code, 200)
        generated = self.client.post("/courses/1/api-key/regenerate", json={
            "ownerType": "group", "groupId": "group-se3010-a", "keyName": "key-1", "slotIndex": 1,
        }, headers=self.instructor_headers)
        self.assertEqual(generated.status_code, 200)
        removed = self.client.delete(self.path + "/members", json={"id": "student.local@kent.edu"}, headers=self.instructor_headers)
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self._group()["memberIds"], [])
        keys = list(main.api_keys.find({"course_id": 1, "owner_type": "group", "owner_id": "group-se3010-a"}))
        self.assertTrue(keys)
        self.assertTrue(all(not key["hash"] for key in keys))

    def test_existing_course_writers_reject_stale_snapshots_before_key_side_effects(self):
        cases = (
            ("apply_course_metadata_patch", "PATCH", "/courses/1/metadata", {"name": "Changed"}),
            ("add_course_members", "POST", "/courses/1/members", {"members": [{"email": "new@kent.edu"}]}),
            ("remove_course_member", "DELETE", "/courses/1/members", {"id": "student.alt1@kent.edu"}),
            ("create_course_group", "POST", "/courses/1/groups", {"name": "Concurrent"}),
            ("remove_group_member", "DELETE", self.path + "/members", {"id": "student.alt1@kent.edu"}),
            ("update_course_member_key_limit", "PATCH", "/courses/1/members/student.alt1@kent.edu/key-limit", {"keyLimit": 0}),
            ("update_course_instructor_handout_limit", "PATCH", "/courses/1/instructor-handout-limit", {"instructorHandoutLimit": 0}),
            ("update_course_instructor_key_limit", "PATCH", "/courses/1/instructor-key-limit", {"instructorKeyLimit": 0}),
            ("update_course_group_key_limit", "PATCH", self.path + "/key-limit", {"keyLimit": 0}),
        )
        for action, method, path, body in cases:
            with self.subTest(action=action):
                self._prepare()
                before = self._course()
                before["groups"][0]["memberIds"] = ["student.alt1@kent.edu"]
                main.courses.replace_one({"_id": before["_id"]}, before)
                keys_before = list(main.api_keys.find())
                original = getattr(main, action)

                def race(*args):
                    updated = original(*args)
                    self.assertEqual(self._join().status_code, 200)
                    return updated

                with patch.object(main, action, side_effect=race):
                    response = self.client.open(path, method=method, json=body, headers=self.admin_headers)
                self.assertEqual(response.status_code, 409, response.json)
                before["groups"][0]["memberIds"].append("student.local@kent.edu")
                before["_pending_audit_events"] = []
                self.assertEqual(self._course(), before)
                self.assertEqual(list(main.api_keys.find()), keys_before)

    def test_identity_reconciliation_cannot_erase_a_join(self):
        self._prepare()
        course = self._course()
        for member in course["members"]:
            if member["email"] == "student.local@kent.edu":
                member["id"] = None
                member["name"] = None
        main.courses.replace_one({"_id": course["_id"]}, course)
        user = main.users.find_one({"email": "student.local@kent.edu"})

        def race(collection, before, after):
            self.assertEqual(self._join().status_code, 200)
            return save_course_changes(collection, before, after)

        with patch.object(course_actions, "save_course_changes", side_effect=race):
            course_actions.reconcile_course_members_for_user(main.courses, user)
        pending = next(member for member in self._course()["members"] if member["email"] == "student.local@kent.edu")
        self.assertIsNone(pending["id"])
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])
        self.assertEqual(course_actions.reconcile_course_members_for_user(main.courses, user), 1)
        self.assertEqual(self._group()["memberIds"], ["student.local@kent.edu"])
