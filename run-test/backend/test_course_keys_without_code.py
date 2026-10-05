from copy import deepcopy
import hashlib
from unittest.mock import patch

from backend.course_actions import delete_course_api_keys, regenerate_course_api_key
from test_api_rocky_auth import api_rocky
from test_support import BackendTestCase, main


class CourseKeysWithoutCodeTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        self.student_id = self.seeded_user_ids["student.local@kent.edu"]
        for name, value in (
            ("api_keys_col", main.api_keys), ("courses_col", main.courses),
            ("users_col", main.users), ("MONGITA_KEY_READ_REFRESH_ENABLED", False),
        ):
            replacement = patch.object(api_rocky, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self._set_code(3)

    def _set_code(self, course_id, value=None):
        course = main.courses.find_one({"id": course_id})
        course.pop("code", None)
        if value is not None:
            course["code"] = value
        main.courses.replace_one({"_id": course["_id"]}, course)

    def _generate_student_key(self):
        response = self.client.post(
            "/courses/3/api-key/regenerate",
            json={"slotIndex": 1, "keyName": "key-1"},
            headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_student_generates_and_authenticates_without_a_course_code(self):
        for code in (None, "", "   "):
            with self.subTest(code=code):
                self._set_code(3, code)
                main.api_keys.delete_many({"course_id": 3})
                key = self._generate_student_key()
                stored = main.api_keys.find_one({"key_id": key["key_id"]})
                self.assertEqual(stored["course_id"], 3)
                self.assertEqual(stored["owner_id"], self.student_id)
                self.assertEqual(stored["hash"], hashlib.sha256(key["api_key"].encode()).hexdigest())
                self.assertNotIn("api_key", stored)
                self.assertNotIn("hash", key)
                self.assertIsNotNone(api_rocky.get_key_doc(key["api_key"]))
                summary = self.client.get("/courses/3/api-keys", headers=self.student_headers)
                self.assertEqual(summary.status_code, 200)
                self.assertTrue(next(row for row in summary.json if row["key_id"] == key["key_id"])["is_active"])
                self.assertTrue(main.api_history.find_one({"course_id": 3, "event_type": "generate-key"}))

    def test_regeneration_cooldown_and_revocation_still_apply_without_code(self):
        key = self._generate_student_key()
        repeated = self.client.post("/courses/3/api-key/regenerate", headers=self.student_headers)
        self.assertEqual(repeated.status_code, 429)
        main.api_keys.update_one({"key_id": key["key_id"]}, {"$set": {"created": "2000-01-01T00:00:00Z"}})
        rotated = self._generate_student_key()
        self.assertEqual(rotated["key_id"], key["key_id"])
        self.assertIsNone(api_rocky.get_key_doc(key["api_key"]))
        key = rotated
        owner = {"ownerType": "person", "ownerId": self.student_id, "slotIndex": 1}
        for enabled in (False, True):
            toggled = self.client.patch(
                "/courses/3/api-key/status", json={**owner, "isActive": enabled}, headers=self.admin_headers,
            )
            self.assertEqual(toggled.status_code, 200, toggled.json)
            self.assertEqual(api_rocky.get_key_doc(key["api_key"]) is not None, enabled)
        removed = self.client.delete("/courses/3/api-key", json=owner, headers=self.student_headers)
        self.assertEqual(removed.status_code, 200, removed.json)
        self.assertIsNone(api_rocky.get_key_doc(key["api_key"]))

    def test_instructor_generates_group_key_without_code(self):
        self._set_code(1)
        response = self.client.post(
            "/courses/1/api-key/regenerate",
            json={"ownerType": "group", "groupId": "group-se3010-a", "slotIndex": 1},
            headers=self.instructor_headers,
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIsNotNone(api_rocky.get_key_doc(response.json["api_key"]))

    def _unrelated_keys(self):
        return [deepcopy(row) for row in main.api_keys.find() if row.get("course_id") != 3]

    def test_delete_all_keys_without_code_preserves_other_keys(self):
        self._generate_student_key()
        main.api_keys.insert_one({"c_id": "", "owner_id": "unrelated", "slot_index": 1})
        unrelated = self._unrelated_keys()
        expected_deleted = main.api_keys.count_documents({"course_id": 3})
        result = self.client.delete("/courses/3/api-key", headers=self.admin_headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["deleted"], expected_deleted)
        self.assertEqual(main.api_keys.count_documents({"course_id": 3}), 0)
        self.assertEqual(self._unrelated_keys(), unrelated)

    def test_delete_course_without_code_cleans_up_its_keys(self):
        self._generate_student_key()
        unrelated = self._unrelated_keys()
        result = self.client.delete("/courses/3", headers=self.admin_headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertIsNone(main.courses.find_one({"id": 3}))
        self.assertEqual(main.api_keys.count_documents({"course_id": 3}), 0)
        self.assertEqual(self._unrelated_keys(), unrelated)
        self.assertTrue(main.api_history.find_one({"course_id": 3, "event_type": "course-deleted"}))

    def test_course_id_takes_precedence_over_shared_code_for_key_deletion(self):
        course = main.courses.find_one({"id": 1})
        main.api_keys.insert_one({
            "course_id": 3, "c_id": course["code"], "owner_id": "unrelated", "slot_index": 1,
        })
        unrelated = deepcopy(main.api_keys.find_one({"course_id": 3, "owner_id": "unrelated"}))
        delete_course_api_keys(course, main.api_keys)
        self.assertEqual(main.api_keys.find_one({"_id": unrelated["_id"]}), unrelated)

    def test_course_history_is_scoped_by_id_even_when_codes_are_missing_or_equal(self):
        for code in ("", "SHARED"):
            with self.subTest(code=code):
                self._set_code(3, code)
                main.api_history.delete_many({})
                for course_id, actor in ((3, self.student_id), (3, "another-student"), (2, self.student_id), (None, self.student_id)):
                    main.api_history.insert_one({
                        "course_id": course_id, "c_id": code, "u_id": actor, "event_type": "generate-key",
                    })
                for headers, count in ((self.admin_headers, 2), (self.student_headers, 1)):
                    history = self.client.get("/courses/3/api-history", headers=headers)
                    self.assertEqual(history.status_code, 200)
                    self.assertEqual(len(history.json), count)
                    self.assertTrue(all(row["course_id"] == 3 for row in history.json))

    def test_missing_both_identifiers_never_creates_or_deletes_keys(self):
        before = deepcopy(list(main.api_keys.find()))
        for action in (
            lambda: regenerate_course_api_key({}, main.api_keys, self.student_id),
            lambda: delete_course_api_keys({}, main.api_keys),
        ):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(list(main.api_keys.find()), before)
