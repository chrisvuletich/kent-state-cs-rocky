from __future__ import annotations

import unittest

from backend.course_actions import add_course_members, can_manage_people, create_course_group, filter_visible_courses, regenerate_course_api_key


class FakeCollection:
    def __init__(self):
        self.rows: list[dict] = []

    def find_one(self, query: dict):
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items()):
                return row
        return None

    def insert_one(self, doc: dict):
        self.rows.append(dict(doc))

    def replace_one(self, query: dict, doc: dict):
        for idx, row in enumerate(self.rows):
            if all(row.get(k) == v for k, v in query.items()):
                self.rows[idx] = dict(doc)
                return

    def find(self):
        return list(self.rows)


class CourseActionsUnitTests(unittest.TestCase):
    def test_create_course_group_generates_unique_id(self):
        course = {
            "groups": [
                {"id": "team-a-1", "name": "Team A", "memberIds": [], "key_limit": 1}
            ]
        }

        updated = create_course_group(course, "Team A")

        new_group = updated["groups"][-1]
        self.assertEqual(new_group["id"], "team-a-2")
        self.assertEqual(new_group["name"], "Team A")

    def test_regenerate_course_api_key_upserts_same_owner_key(self):
        collection = FakeCollection()
        course = {"id": 1, "code": "SE 3010"}

        first = regenerate_course_api_key(course, collection, "ksuid000000001")
        second = regenerate_course_api_key(course, collection, "ksuid000000001")

        self.assertEqual(len(collection.rows), 1)
        self.assertEqual(first["owner_id"], "ksuid000000001")
        self.assertEqual(second["owner_id"], "ksuid000000001")
        self.assertNotEqual(first["api_key"], second["api_key"])

    def test_regenerate_course_api_key_assigns_unique_public_key_ids(self):
        collection = FakeCollection()
        course = {"id": 1, "code": "SE 3010"}

        first = regenerate_course_api_key(
            course,
            collection,
            "ksuid000000001",
            {"slot_index": 1},
        )
        second = regenerate_course_api_key(
            course,
            collection,
            "ksuid000000002",
            {"slot_index": 1},
        )

        self.assertTrue(first["key_id"].startswith("akid_"))
        self.assertTrue(second["key_id"].startswith("akid_"))
        self.assertNotEqual(first["key_id"], second["key_id"])

    def test_regenerate_course_api_key_preserves_public_key_id_for_same_slot(self):
        collection = FakeCollection()
        course = {"id": 1, "code": "SE 3010"}

        first = regenerate_course_api_key(course, collection, "ksuid000000001", {"slot_index": 1})
        second = regenerate_course_api_key(course, collection, "ksuid000000001", {"slot_index": 1})

        self.assertEqual(first["key_id"], second["key_id"])
        self.assertNotEqual(first["api_key"], second["api_key"])

    def test_add_course_members_allows_email_before_user_exists(self):
        users = FakeCollection()
        course = {"members": []}

        updated = add_course_members(course, users, [{"email": "future.user@example.com", "role": "student"}], False)

        self.assertEqual(len(updated["members"]), 1)
        member = updated["members"][0]
        self.assertIsNone(member["id"])
        self.assertIsNone(member["name"])
        self.assertEqual(member["email"], "future.user@example.com")

    def test_add_course_members_merges_pending_email_with_real_user(self):
        users = FakeCollection()
        users.rows.append(
            {
                "id": "KSUID000000123",
                "first_name": "Future",
                "last_name": "User",
                "email": "future.user@example.com",
            }
        )
        course = {
            "members": [
                {"id": None, "name": None, "email": "future.user@example.com", "role": "student", "key_limit": 1}
            ]
        }

        updated = add_course_members(course, users, [{"email": "future.user@example.com", "role": "student"}], False)

        self.assertEqual(len(updated["members"]), 1)
        member = updated["members"][0]
        self.assertEqual(member["id"], "KSUID000000123")
        self.assertEqual(member["name"], "Future User")
        self.assertEqual(member["email"], "future.user@example.com")

    def test_filter_visible_courses_matches_pending_member_email(self):
        courses = [
            {
                "id": 1,
                "members": [
                    {"id": None, "name": None, "email": "future.user@example.com", "role": "student", "key_limit": 1}
                ],
            }
        ]

        visible = filter_visible_courses(courses, "future.user@example.com", False)

        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["id"], 1)

    def test_filter_visible_courses_includes_teacher_assistant(self):
        courses = [
            {
                "id": 7,
                "instructor_id": "KSUID000000001",
                "instructor_email": "instructor@kent.edu",
                "ta_ids": ["KSUID000000777"],
                "ta_emails": ["ta.user@kent.edu"],
                "members": [],
            }
        ]

        visible_by_id = filter_visible_courses(courses, "ksuid000000777", False)
        visible_by_email = filter_visible_courses(courses, "ta.user@kent.edu", False)

        self.assertEqual(len(visible_by_id), 1)
        self.assertEqual(visible_by_id[0]["id"], 7)
        self.assertEqual(len(visible_by_email), 1)
        self.assertEqual(visible_by_email[0]["id"], 7)

    def test_can_manage_people_allows_teacher_assistant(self):
        course = {
            "instructor_id": "KSUID000000001",
            "instructor_email": "instructor@kent.edu",
            "ta_ids": ["KSUID000000777"],
            "ta_emails": ["ta.user@kent.edu"],
        }

        self.assertTrue(can_manage_people(course, "ksuid000000777", False))
        self.assertTrue(can_manage_people(course, "ta.user@kent.edu", False))


if __name__ == "__main__":
    unittest.main()
