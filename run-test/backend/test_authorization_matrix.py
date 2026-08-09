from __future__ import annotations

from dataclasses import dataclass
import unittest
from unittest.mock import patch

from backend.test_support import BackendTestCase, main, seed_backend


@dataclass(frozen=True)
class AuthorizationCase:
    name: str
    method: str
    path: str
    actor: str
    expected_status: int
    payload: dict | None = None


class BackendAuthorizationMatrixTests(BackendTestCase):
    """Readable role matrix for the web application's protected Flask routes."""

    def _headers_for(self, actor: str) -> dict[str, str]:
        headers = {
            "admin": self.admin_headers,
            "instructor": self.instructor_headers,
            "student": self.student_headers,
            "anonymous": {},
        }
        return dict(headers[actor])

    def test_management_role_matrix(self):
        cases = (
            AuthorizationCase(
                name="active student can read an enrolled course",
                method="GET",
                path="/courses/3",
                actor="student",
                expected_status=200,
            ),
            AuthorizationCase(
                name="student cannot list users",
                method="GET",
                path="/users",
                actor="student",
                expected_status=403,
            ),
            AuthorizationCase(
                name="instructor can manage their own course",
                method="POST",
                path="/courses/1/groups",
                actor="instructor",
                expected_status=200,
                payload={"name": "Authorization Matrix Group"},
            ),
            AuthorizationCase(
                name="instructor cannot manage an unrelated course",
                method="POST",
                path="/courses/2/groups",
                actor="instructor",
                expected_status=403,
                payload={"name": "Unauthorized Group"},
            ),
            AuthorizationCase(
                name="administrator can manage course status",
                method="PATCH",
                path="/courses/2/status",
                actor="admin",
                expected_status=200,
                payload={"is_active": False},
            ),
            AuthorizationCase(
                name="anonymous request cannot list courses",
                method="GET",
                path="/courses",
                actor="anonymous",
                expected_status=401,
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                # A row must never inherit a mutation made by the preceding row.
                seed_backend.seed_from_backend()
                response = self.client.open(
                    case.path,
                    method=case.method,
                    json=case.payload,
                    headers=self._headers_for(case.actor),
                )
                self.assertEqual(response.status_code, case.expected_status)

    def test_active_student_can_generate_only_their_own_course_key(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        other_student_id = self.seeded_user_ids["student.alt2@kent.edu"]

        own_key = self.client.post(
            "/courses/3/api-key/regenerate",
            json={
                "ownerType": "person",
                # Non-managers cannot redirect a key to another course member.
                # The backend must resolve this request back to the requester.
                "ownerId": other_student_id,
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.student_headers,
        )

        self.assertEqual(own_key.status_code, 200)
        payload = own_key.get_json() or {}
        self.assertTrue(payload.get("api_key", "").startswith("sk_kent_"))
        self.assertEqual(payload.get("owner_id"), student_id.lower())
        self.assertIsNone(
            main.api_keys.find_one(
                {
                    "course_id": 3,
                    "owner_type": "person",
                    "owner_id": other_student_id.lower(),
                }
            )
        )

    def test_student_cannot_generate_or_delete_a_shared_group_key(self):
        group_payload = {
            "ownerType": "group",
            "groupId": "group-se3010-a",
            "keyName": "key-1",
            "slotIndex": 1,
        }

        forbidden_generate = self.client.post(
            "/courses/1/api-key/regenerate",
            json=group_payload,
            headers=self.student_headers,
        )
        self.assertEqual(forbidden_generate.status_code, 403)

        generated = self.client.post(
            "/courses/1/api-key/regenerate",
            json=group_payload,
            headers=self.instructor_headers,
        )
        self.assertEqual(generated.status_code, 200)

        forbidden_delete = self.client.delete(
            "/courses/1/api-key",
            json=group_payload,
            headers=self.student_headers,
        )
        self.assertEqual(forbidden_delete.status_code, 403)
        stored = main.api_keys.find_one(
            {
                "course_id": 1,
                "owner_type": "group",
                "owner_id": "group-se3010-a",
                "slot_index": 1,
            }
        )
        self.assertTrue((stored or {}).get("hash"))
        self.assertTrue((stored or {}).get("is_active"))

    def test_removing_course_member_revokes_personal_and_affected_group_keys(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        personal_key = self.client.post(
            "/courses/1/api-key/regenerate",
            json={"ownerType": "person", "keyName": "key-1", "slotIndex": 1},
            headers=self.student_headers,
        )
        self.assertEqual(personal_key.status_code, 200)
        group_key = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "group",
                "groupId": "group-se3010-a",
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.instructor_headers,
        )
        self.assertEqual(group_key.status_code, 200)

        removed = self.client.delete(
            "/courses/1/members",
            json={"id": student_id},
            headers=self.instructor_headers,
        )
        self.assertEqual(removed.status_code, 200)

        personal_stored = main.api_keys.find_one(
            {"course_id": 1, "owner_type": "person", "owner_id": student_id.lower()}
        )
        group_stored = main.api_keys.find_one(
            {"course_id": 1, "owner_type": "group", "owner_id": "group-se3010-a"}
        )
        for stored in (personal_stored, group_stored):
            self.assertIsNotNone(stored)
            self.assertEqual((stored or {}).get("hash"), "")
            self.assertFalse((stored or {}).get("is_active"))
            self.assertEqual((stored or {}).get("disabled_reason"), "membership")
            self.assertTrue((stored or {}).get("deleted_at"))

    def test_removing_group_member_revokes_the_shared_group_key(self):
        group_key = self.client.post(
            "/courses/1/api-key/regenerate",
            json={
                "ownerType": "group",
                "groupId": "group-se3010-a",
                "keyName": "key-1",
                "slotIndex": 1,
            },
            headers=self.instructor_headers,
        )
        self.assertEqual(group_key.status_code, 200)

        removed = self.client.delete(
            "/courses/1/groups/group-se3010-a/members",
            json={"id": "student.local@kent.edu"},
            headers=self.instructor_headers,
        )
        self.assertEqual(removed.status_code, 200)

        stored = main.api_keys.find_one(
            {"course_id": 1, "owner_type": "group", "owner_id": "group-se3010-a"}
        )
        self.assertEqual((stored or {}).get("hash"), "")
        self.assertFalse((stored or {}).get("is_active"))
        self.assertEqual((stored or {}).get("disabled_reason"), "membership")
        self.assertTrue((stored or {}).get("deleted_at"))

    def test_inactive_user_and_closed_course_fail_closed(self):
        student_id = self.seeded_user_ids["student.local@kent.edu"]
        deactivate = self.client.put(
            f"/users/{student_id}",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(deactivate.status_code, 200)
        inactive_response = self.client.get("/courses", headers=self.student_headers)
        self.assertEqual(inactive_response.status_code, 403)

        seed_backend.seed_from_backend()
        close_course = self.client.patch(
            "/courses/3/status",
            json={"is_active": False},
            headers=self.admin_headers,
        )
        self.assertEqual(close_course.status_code, 200)
        closed_key = self.client.post(
            "/courses/3/api-key/regenerate",
            json={"ownerType": "person", "keyName": "key-1", "slotIndex": 1},
            headers=self.student_headers,
        )
        self.assertEqual(closed_key.status_code, 403)
        self.assertIn("closed", str((closed_key.get_json() or {}).get("error", "")).lower())

    def test_forwarded_identity_requires_the_configured_proxy_secret(self):
        configured_secret = "authorization-matrix-proxy-secret"
        with patch.dict(
            "os.environ",
            {"ROCKY_INTERNAL_PROXY_SECRET": configured_secret},
            clear=False,
        ):
            untrusted = self.client.get("/courses", headers=self.student_headers)
            trusted = self.client.get(
                "/courses",
                headers={
                    **self.student_headers,
                    "X-Rocky-Internal-Secret": configured_secret,
                },
            )

        self.assertEqual(untrusted.status_code, 401)
        self.assertEqual(trusted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
