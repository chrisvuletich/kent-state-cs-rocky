from __future__ import annotations

from unittest.mock import patch

from backend.api_key_generator import generate_hidden_api_key_pair

try:
    from backend.test_support import BackendTestCase, main
except ModuleNotFoundError:
    from test_support import BackendTestCase, main


class MicrosoftOAuthTests(BackendTestCase):
    def setUp(self):
        super().setUp()
        object.__setattr__(main.settings, "enable_microsoft_oauth", True)

    def _default_key_for_user(self, user):
        return main.api_keys.find_one(
            {
                "owner_type": "person",
                "owner_id": str(user.get("_id")).lower(),
                "key_scope": "user-default",
                "key_name": "default",
            }
        )

    def _expected_default_key_hash(self, user):
        _, expected_hash = generate_hidden_api_key_pair(str(user.get("_id")).lower())
        return expected_hash

    def test_whitelist_add_assigns_database_id(self):
        self._log("Adding whitelist entry. Expecting a database-generated id and persisted entry.")

        response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Taylor",
                "lastName": "Outside",
                "email": "taylor.outside@example.com",
            },
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        entry = payload["entry"]
        self.assertTrue(entry["id"])
        self.assertEqual(entry["email"], "taylor.outside@example.com")
        self.assertEqual(entry["role"], "student")

    def test_whitelist_role_is_applied_at_first_login(self):
        self._log("Adding an instructor whitelist entry. Expecting first login to preserve the role.")
        add_response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Taylor",
                "lastName": "Instructor",
                "email": "taylor.instructor@example.com",
                "role": "instructor",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(add_response.get_json()["entry"]["role"], "instructor")

        login_response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Taylor",
                "lastName": "Instructor",
                "email": "taylor.instructor@example.com",
            },
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.get_json()["user"]["role"], "instructor")
        saved = main.users.find_one({"email": "taylor.instructor@example.com"})
        self.assertEqual(saved.get("role"), "instructor")
        self.assertFalse(saved.get("is_admin"))

    def test_whitelist_rejects_invalid_role(self):
        response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Taylor",
                "lastName": "Invalid",
                "email": "taylor.invalid@example.com",
                "role": "owner",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(main.whitelist_users.find_one({"email": "taylor.invalid@example.com"}))

    def test_microsoft_login_denies_non_whitelisted_external_email(self):
        self._log("Posting OAuth login for non-Kent non-whitelisted email. Expecting HTTP 403.")
        response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Ari",
                "lastName": "Guest",
                "email": "ari.guest@example.com",
            },
        )

        self.assertEqual(response.status_code, 403)
        saved = main.users.find_one({"email": "ari.guest@example.com"})
        self.assertIsNone(saved)

    def test_microsoft_login_allows_whitelisted_external_email(self):
        self._log("Adding whitelist entry then posting OAuth login for external email. Expecting created user.")

        add_response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Ari",
                "lastName": "Guest",
                "email": "ari.guest@example.com",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(add_response.status_code, 201)
        whitelist_id = add_response.get_json()["entry"]["id"]

        login_response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Ari",
                "lastName": "Guest",
                "email": "ari.guest@example.com",
            },
        )
        self.assertEqual(login_response.status_code, 200)

        saved = main.users.find_one({"email": "ari.guest@example.com"})
        self.assertIsNotNone(saved)
        self.assertTrue(saved.get("id"))
        self.assertEqual(saved.get("is_admin"), False)
        default_key = self._default_key_for_user(saved)
        self.assertIsNotNone(default_key)
        self.assertEqual(default_key.get("owner_id"), str(saved.get("_id")).lower())
        self.assertNotEqual(default_key.get("owner_id"), saved.get("email"))
        self.assertTrue((default_key.get("key_id") or "").startswith("akid_"))
        self.assertNotIn("api_key_id", default_key)
        self.assertEqual(default_key.get("key_name"), "default")
        self.assertEqual(default_key.get("key_scope"), "user-default")
        self.assertEqual(default_key.get("slot_index"), 0)
        self.assertEqual(default_key.get("hash"), self._expected_default_key_hash(saved))
        self.assertTrue(isinstance(default_key.get("hash"), str) and len(default_key.get("hash")) == 64)
        self.assertNotIn("api_key", default_key)

    def test_whitelist_patch_updates_active_flag_and_syncs_existing_user(self):
        self._log("Disabling then re-enabling whitelist user. Expecting whitelist and user docs to sync is_active.")

        add_response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Ari",
                "lastName": "Guest",
                "email": "ari.sync@example.com",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(add_response.status_code, 201)
        whitelist_id = add_response.get_json()["entry"]["id"]

        self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Ari",
                "lastName": "Guest",
                "email": "ari.sync@example.com",
            },
        )

        disable_response = self.client.patch(
            f"/auth/microsoft/whitelist/{whitelist_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(disable_response.status_code, 200)
        self.assertEqual(main.whitelist_users.find_one({"id": whitelist_id}).get("is_active"), False)
        self.assertEqual(main.users.find_one({"email": "ari.sync@example.com"}).get("is_active"), False)

        enable_response = self.client.patch(
            f"/auth/microsoft/whitelist/{whitelist_id}",
            json={"is_active": True},
            headers=self.admin_headers,
        )
        self.assertEqual(enable_response.status_code, 200)
        self.assertEqual(main.whitelist_users.find_one({"id": whitelist_id}).get("is_active"), True)
        self.assertEqual(main.users.find_one({"email": "ari.sync@example.com"}).get("is_active"), True)

        role_response = self.client.patch(
            f"/auth/microsoft/whitelist/{whitelist_id}",
            json={"role": "instructor"},
            headers=self.admin_headers,
        )
        self.assertEqual(role_response.status_code, 200)
        self.assertEqual(main.whitelist_users.find_one({"id": whitelist_id}).get("role"), "instructor")
        linked_user = main.users.find_one({"email": "ari.sync@example.com"})
        self.assertEqual(linked_user.get("role"), "instructor")
        self.assertFalse(linked_user.get("is_admin"))

    def test_microsoft_login_preserves_deactivated_whitelist_status(self):
        self._log("Logging in with deactivated whitelisted email. Expecting created user to remain inactive.")

        add_response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Casey",
                "lastName": "Dormant",
                "email": "casey.dormant@example.com",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(add_response.status_code, 201)
        whitelist_id = add_response.get_json()["entry"]["id"]

        patch_response = self.client.patch(
            f"/auth/microsoft/whitelist/{whitelist_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(patch_response.status_code, 200)

        login_response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Casey",
                "lastName": "Dormant",
                "email": "casey.dormant@example.com",
            },
        )
        self.assertEqual(login_response.status_code, 200)

        payload = login_response.get_json()
        self.assertEqual(payload["user"]["is_active"], False)

        saved = main.users.find_one({"email": "casey.dormant@example.com"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("is_active"), False)
        default_key = self._default_key_for_user(saved)
        self.assertIsNotNone(default_key)
        self.assertFalse(default_key.get("is_active"))
        self.assertEqual(default_key.get("disabled_reason"), "account-inactive")

    def test_whitelist_removal_retains_and_deactivates_linked_user_and_keys(self):
        self._log("Removing a whitelist entry. Expecting linked identity history to remain while access is revoked.")
        add_response = self.client.post(
            "/auth/microsoft/whitelist",
            json={
                "firstName": "Ari",
                "lastName": "Retained",
                "email": "ari.retained@example.com",
                "role": "student",
            },
            headers=self.admin_headers,
        )
        whitelist_id = add_response.get_json()["entry"]["id"]
        self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Ari",
                "lastName": "Retained",
                "email": "ari.retained@example.com",
            },
        )
        user = main.users.find_one({"email": "ari.retained@example.com"})
        self.assertIsNotNone(user)

        remove_response = self.client.delete(
            f"/auth/microsoft/whitelist/{whitelist_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(remove_response.status_code, 200)
        retained = main.users.find_one({"email": "ari.retained@example.com"})
        self.assertIsNotNone(retained)
        self.assertFalse(retained.get("is_active"))
        self.assertIsNone(main.whitelist_users.find_one({"id": whitelist_id}))
        self.assertFalse(self._default_key_for_user(retained).get("is_active"))

        denied_login = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Ari",
                "lastName": "Retained",
                "email": "ari.retained@example.com",
            },
        )
        self.assertEqual(denied_login.status_code, 403)

    def test_microsoft_login_auto_creates_kent_user(self):
        self._log("Posting OAuth login for Kent email. Expecting user creation without course assignment.")

        response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Jordan",
                "lastName": "Kent",
                "email": "jordan.kent@kent.edu",
                "id": "123456789",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload.get("ok"))

        saved = main.users.find_one({"email": "jordan.kent@kent.edu"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved.get("is_admin"), False)
        self.assertTrue(saved.get("id"))
        self.assertEqual(payload["user"]["id"], saved.get("id"))
        default_key = self._default_key_for_user(saved)
        self.assertIsNotNone(default_key)
        self.assertEqual(default_key.get("owner_id"), str(saved.get("_id")).lower())
        self.assertNotEqual(default_key.get("owner_id"), saved.get("email"))
        self.assertEqual(default_key.get("hash"), self._expected_default_key_hash(saved))

    def test_microsoft_login_does_not_duplicate_existing_default_key(self):
        self._log("Logging in twice should keep a single default API key for that user.")

        payload = {
            "firstName": "Jordan",
            "lastName": "Repeat",
            "email": "jordan.repeat@kent.edu",
            "id": "123456789",
        }
        first_response = self.client.post("/auth/microsoft/login", json=payload)
        self.assertEqual(first_response.status_code, 200)
        saved = main.users.find_one({"email": "jordan.repeat@kent.edu"})
        self.assertIsNotNone(saved)
        default_key = self._default_key_for_user(saved)
        self.assertIsNotNone(default_key)
        original_hash = default_key.get("hash")

        second_response = self.client.post("/auth/microsoft/login", json=payload)
        self.assertEqual(second_response.status_code, 200)
        keys = list(
            main.api_keys.find(
                {
                    "owner_type": "person",
                    "owner_id": str(saved.get("_id")).lower(),
                    "key_name": "default",
                }
            )
        )
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0].get("hash"), original_hash)
        self.assertEqual(keys[0].get("hash"), self._expected_default_key_hash(saved))
        self.assertTrue((keys[0].get("key_id") or "").startswith("akid_"))

    def test_whitelist_requires_admin_headers(self):
        self._log("Requesting whitelist list as non-admin. Expecting HTTP 403.")
        response = self.client.get(
            "/auth/microsoft/whitelist",
            headers=self.student_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_session_user_endpoint_returns_user_by_email(self):
        self._log("Looking up session user by email. Expecting seeded user payload.")
        response = self.client.get(
            "/auth/session-user",
            query_string={"email": "admin.local@kent.edu"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload.get("email"), "admin.local@kent.edu")
        saved = main.users.find_one({"email": "admin.local@kent.edu"})
        self.assertIsNotNone(saved)
        default_key = self._default_key_for_user(saved)
        self.assertIsNotNone(default_key)
        self.assertEqual(default_key.get("owner_id"), str(saved.get("_id")).lower())
        self.assertTrue((default_key.get("key_id") or "").startswith("akid_"))

    def test_session_user_reconciles_pending_course_member(self):
        self._log("Creating pending course member by email, then resolving session user to trigger id/name reconciliation.")
        self.client.post(
            "/courses/1/members",
            json={"members": [{"email": "new.student@kent.edu", "role": "student"}]},
            headers=self.admin_headers,
        )

        create_user_response = self.client.post(
            "/users",
            json={
                "first_name": "New",
                "last_name": "Student",
                "email": "new.student@kent.edu",
                "id": "KSUID000000222",
                "is_admin": False,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(create_user_response.status_code, 200)

        session_response = self.client.get(
            "/auth/session-user",
            query_string={"email": "new.student@kent.edu"},
        )
        self.assertEqual(session_response.status_code, 200)

        course = main.courses.find_one({"id": 1})
        self.assertIsNotNone(course)
        member = next(
            (
                m
                for m in (course.get("members") or [])
                if isinstance(m, dict) and (m.get("email") or "").lower() == "new.student@kent.edu"
            ),
            None,
        )
        self.assertIsNotNone(member)
        self.assertEqual(member.get("id"), main.users.find_one({"email": "new.student@kent.edu"}).get("id"))
        self.assertEqual(member.get("name"), "New Student")

    def test_microsoft_login_reconciles_pending_member_for_kent_user(self):
        self._log("Adding pending Kent member then logging in with Microsoft OAuth to verify course member id/name reconciliation.")
        self.client.post(
            "/courses/1/members",
            json={"members": [{"email": "oauth.student@kent.edu", "role": "student"}]},
            headers=self.admin_headers,
        )

        login_response = self.client.post(
            "/auth/microsoft/login",
            json={
                "firstName": "Oauth",
                "lastName": "Student",
                "email": "oauth.student@kent.edu",
                "id": "222333444",
            },
        )
        self.assertEqual(login_response.status_code, 200)

        course = main.courses.find_one({"id": 1})
        self.assertIsNotNone(course)
        member = next(
            (
                m
                for m in (course.get("members") or [])
                if isinstance(m, dict) and (m.get("email") or "").lower() == "oauth.student@kent.edu"
            ),
            None,
        )
        self.assertIsNotNone(member)
        self.assertEqual(member.get("id"), main.users.find_one({"email": "oauth.student@kent.edu"}).get("id"))
        self.assertEqual(member.get("name"), "Oauth Student")


if __name__ == "__main__":
    import unittest

    unittest.main()
