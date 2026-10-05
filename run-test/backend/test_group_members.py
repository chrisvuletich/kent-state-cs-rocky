from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from test_support import BackendTestCase, main


class GroupMembersTests(BackendTestCase):
    path = "/courses/1/groups/group-se3010-a/members"

    def setUp(self):
        super().setUp()
        course = main.courses.find_one({"id": 1})
        course["members"].append({"id": None, "name": None, "email": "pending.group@kent.edu", "key_limit": 1})
        main.courses.replace_one({"_id": course["_id"]}, course)

    def _course(self):
        return main.courses.find_one({"id": 1})

    def _events(self):
        return list(main.api_history.find({"event_type": "course-group-members-added"}))

    def _add(self, ids, headers=None):
        return self.client.post(self.path, json={"memberIds": ids}, headers=headers if headers is not None else self.instructor_headers)

    def test_batch_adds_pending_and_existing_accounts_and_deduplicates_aliases(self):
        before = self._course()
        ids = [" pending.group@KENT.edu ", "instructor.alt@kent.edu", "student.local@kent.edu", self.seeded_user_ids["student.local@kent.edu"], "pending.group@kent.edu"]
        result = self._add(ids)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["added_count"], 2)
        self.assertEqual(result.json["already_member_count"], 1)
        after = self._course()
        group = next(group for group in after["groups"] if group["id"] == "group-se3010-a")
        self.assertEqual(group["memberIds"].count("pending.group@kent.edu"), 1)
        self.assertEqual(group["memberIds"].count("student.local@kent.edu"), 1)
        self.assertEqual(group, result.json["group"])
        self.assertEqual(group["key_limit"], before["groups"][0]["key_limit"])
        self.assertEqual(after["members"], before["members"])
        self.assertEqual(after["groups"][1:], before["groups"][1:])
        self.assertEqual(self._events()[0]["meta"]["changes"]["member_ids"], ["pending.group@kent.edu", "instructor.alt@kent.edu"])
        repeated = self._add(ids)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json["added_count"], 0)
        self.assertEqual(repeated.json["already_member_count"], 3)
        self.assertEqual(self._course(), after)
        self.assertEqual(len(self._events()), 1)

    def test_invalid_batch_is_all_or_nothing(self):
        before = self._course()
        for ids in (None, [], "pending.group@kent.edu", [None], [123], [True], [{}], [""], ["  "], ["pending.group@kent.edu", "outsider@kent.edu"]):
            with self.subTest(ids=ids):
                result = self._add(ids)
                self.assertEqual(result.status_code, 400, result.json)
                self.assertEqual(self._course(), before)
                self.assertEqual(self._events(), [])

    def test_admin_instructor_and_course_ta_can_add(self):
        main.courses.update_one({"id": 1}, {"$set": {"ta_ids": [self.seeded_user_ids["student.local@kent.edu"]], "ta_emails": ["student.local@kent.edu"]}})
        for headers in (self.admin_headers, self.instructor_headers, self.student_headers):
            with self.subTest(headers=headers):
                self.assertEqual(self._add(["pending.group@kent.edu"], headers).status_code, 200)

    def test_unauthorized_and_unrelated_users_cannot_add(self):
        before = self._course()
        for headers, expected in (({}, 401), (self.student_headers, 403), ({"X-Rocky-User-Email": "instructor.alt@kent.edu", "X-Rocky-User-Is-Admin": "false"}, 403)):
            with self.subTest(headers=headers):
                self.assertEqual(self._add(["pending.group@kent.edu"], headers).status_code, expected)
                self.assertEqual(self._course(), before)
                self.assertEqual(self._events(), [])

    def test_course_staff_are_not_selectable_as_students(self):
        course = self._course()
        course["members"].append({"id": course["instructor_id"], "email": course["instructor_email"]})
        course["ta_emails"] = ["pending.group@kent.edu"]
        main.courses.replace_one({"_id": course["_id"]}, course)
        for identifier in (course["instructor_id"], course["instructor_email"], "pending.group@kent.edu"):
            with self.subTest(identifier=identifier):
                self.assertEqual(self._add([identifier]).status_code, 400)
                self.assertEqual(self._course(), course)

    def test_closed_or_missing_course_and_missing_group(self):
        self.assertEqual(self.client.post("/courses/1/groups/missing/members", json={"memberIds": ["pending.group@kent.edu"]}, headers=self.instructor_headers).status_code, 404)
        self.assertEqual(self.client.post("/courses/999/groups/missing/members", json={"memberIds": ["pending.group@kent.edu"]}, headers=self.admin_headers).status_code, 404)
        main.courses.update_one({"id": 1}, {"$set": {"is_active": False}})
        before = self._course()
        self.assertEqual(self._add(["pending.group@kent.edu"]).status_code, 403)
        self.assertEqual(self._course(), before)
        self.assertEqual(self._events(), [])

    def test_non_object_body_is_rejected(self):
        for body in ([], "student.local@kent.edu"):
            self.assertEqual(self.client.post(self.path, json=body, headers=self.instructor_headers).status_code, 400)

    def test_concurrent_roster_group_or_permission_changes_are_not_overwritten(self):
        original_add = main.add_group_members
        original_course = self._course()
        changed_groups = deepcopy(original_course["groups"])
        changed_groups[0]["memberIds"].append("instructor.alt@kent.edu")
        for changes in (
            {"members": original_course["members"][:-1]},
            {"groups": changed_groups},
            {"groups": []},
            {"is_active": False},
            {"instructor_id": "someone-else"},
            {"ta_emails": ["pending.group@kent.edu"]},
        ):
            with self.subTest(changes=changes):
                main.courses.replace_one({"_id": original_course["_id"]}, original_course)

                def concurrent_change(*args):
                    result = original_add(*args)
                    main.courses.update_one({"id": 1}, {"$set": changes})
                    return result

                with patch.object(main, "add_group_members", side_effect=concurrent_change):
                    response = self._add(["pending.group@kent.edu"])
                self.assertEqual(response.status_code, 409, response.json)
                self.assertEqual(self._course(), {**original_course, **changes})
                self.assertEqual(self._events(), [])

    def test_unrelated_concurrent_metadata_edit_is_preserved(self):
        original_add = main.add_group_members

        def concurrent_change(*args):
            result = original_add(*args)
            main.courses.update_one({"id": 1}, {"$set": {"name": "Updated course name"}})
            return result

        with patch.object(main, "add_group_members", side_effect=concurrent_change):
            self.assertEqual(self._add(["pending.group@kent.edu"]).status_code, 200)
        self.assertEqual(self._course()["name"], "Updated course name")

    def test_large_batch_audits_every_new_student(self):
        course = self._course()
        emails = [f"group.student{index}@kent.edu" for index in range(125)]
        course["members"].extend({"id": None, "email": email} for email in emails)
        main.courses.replace_one({"_id": course["_id"]}, course)
        result = self._add(emails)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["added_count"], len(emails))
        events = self._events()
        self.assertEqual(len(events), 2)
        self.assertEqual([email for event in events for email in event["meta"]["changes"]["member_ids"]], emails)
