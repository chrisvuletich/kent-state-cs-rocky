from __future__ import annotations

from test_support import BackendTestCase, main


class UserSettingsTests(BackendTestCase):
    def test_get_user_settings_returns_seeded_values(self):
        self._log("Requesting user settings for seeded users.")

        response = self.client.get(
            "/user-settings",
            query_string={"userId": "local-admin", "email": "admin.local@kent.edu"},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["settings"]["themePreference"], "light")
        self.assertIn("profilePicture", payload["settings"])

    def test_patch_user_setting_updates_theme(self):
        self._log("Patching themePreference through key endpoint. Expecting persisted update.")
        update_response = self.client.patch(
            "/user-settings/themePreference",
            json={"userId": "local-admin", "email": "admin.local@kent.edu", "value": "dark"},
            headers=self.admin_headers,
        )
        self.assertEqual(update_response.status_code, 200)

        read_response = self.client.get(
            "/user-settings",
            query_string={"userId": "local-admin", "email": "admin.local@kent.edu"},
            headers=self.admin_headers,
        )
        self.assertEqual(read_response.status_code, 200)
        payload = read_response.get_json()
        self.assertEqual(payload["settings"]["themePreference"], "dark")

        stored_user = main.users.find_one({"email": "admin.local@kent.edu"})
        self.assertIsNotNone(stored_user)
        self.assertEqual((stored_user.get("settings") or {}).get("themePreference"), "dark")


if __name__ == "__main__":
    import unittest

    unittest.main()
