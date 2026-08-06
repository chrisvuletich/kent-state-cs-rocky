from __future__ import annotations

from collections import Counter

from backend.test_support import BackendTestCase, main, seed_backend


class SeedDataShapeTests(BackendTestCase):
    def test_backend_seed_distribution_is_even(self):
        self._log("Seeding balanced backend fixture data and checking admin/course spread.")
        summary = seed_backend.seed_from_backend()
        self._log(f"Seed summary: {summary}")

        self.assertEqual(summary["users_inserted"], 7)
        self.assertEqual(summary["courses_inserted"], 6)
        self.assertEqual(summary["api_keys_inserted"], 6)
        self.assertEqual(summary["api_history_inserted"], 5)

        admin_counts = Counter(bool(user.get("is_admin")) for user in main.users.find())
        self.assertEqual(admin_counts[True], 1)
        self.assertEqual(admin_counts[False], 6)

        roles_by_email = {user.get("email"): user.get("role") for user in main.users.find()}
        self.assertEqual(roles_by_email["admin.local@kent.edu"], "admin")
        self.assertEqual(roles_by_email["instructor.local@kent.edu"], "instructor")
        self.assertEqual(roles_by_email["student.local@kent.edu"], "student")

        self.assertEqual(main.users.count_documents({}), 7)
        self.assertEqual(main.courses.count_documents({}), 6)
        self.assertEqual(main.api_history.count_documents({}), 5)

    def test_each_seeded_user_has_own_widgets(self):
        self._log("Checking that widgets are embedded per user record.")
        seed_backend.seed_from_backend()

        admin = main.users.find_one({"email": "admin.local@kent.edu"})
        student = main.users.find_one({"email": "student.local@kent.edu"})
        instructor = main.users.find_one({"email": "instructor.local@kent.edu"})

        self.assertIsNotNone(admin)
        self.assertIsNotNone(student)
        self.assertIsNotNone(instructor)

        admin_widgets = (admin.get("settings") or {}).get("widgets", [])
        student_widgets = (student.get("settings") or {}).get("widgets", [])
        instructor_widgets = (instructor.get("settings") or {}).get("widgets", [])

        available_ids = {widget["id"] for widget in main.widgets_default.find()}
        self.assertTrue(all(widget in available_ids for widget in admin_widgets))
        self.assertTrue(all(widget in available_ids for widget in student_widgets))
        self.assertTrue(all(widget in available_ids for widget in instructor_widgets))

        self.assertNotEqual(admin_widgets, student_widgets)
        self.assertNotEqual(student_widgets, instructor_widgets)


if __name__ == "__main__":
    import unittest

    unittest.main()
