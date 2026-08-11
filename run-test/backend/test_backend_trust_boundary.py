from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.test_support import BackendTestCase


class BackendTrustBoundaryTests(BackendTestCase):
    def _get(
        self,
        path: str,
        *,
        remote_address: str,
        headers: dict[str, str] | None = None,
    ):
        return self.client.get(
            path,
            headers=headers or {},
            environ_overrides={"REMOTE_ADDR": remote_address},
        )

    def test_secretless_development_trusts_direct_loopback_peers(self):
        values = {
            "ROCKY_APP_ENV": "development",
            "ROCKY_INTERNAL_PROXY_SECRET": "",
        }
        for remote_address in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            with self.subTest(remote_address=remote_address):
                with patch.dict(os.environ, values, clear=False):
                    response = self._get(
                        "/courses",
                        remote_address=remote_address,
                        headers=self.student_headers,
                    )
                self.assertEqual(response.status_code, 200)

    def test_secretless_development_rejects_non_loopback_identity_headers(self):
        values = {
            "ROCKY_APP_ENV": "development",
            "ROCKY_INTERNAL_PROXY_SECRET": "",
        }
        spoofed_headers = {
            **self.admin_headers,
            "X-Forwarded-For": "127.0.0.1",
        }
        with patch.dict(os.environ, values, clear=False):
            response = self._get(
                "/users",
                remote_address="192.0.2.25",
                headers=spoofed_headers,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Admin access is required."})

    def test_configured_secret_allows_a_non_loopback_proxy(self):
        configured_secret = "synthetic-shared-proxy-secret"
        values = {
            "ROCKY_APP_ENV": "development",
            "ROCKY_INTERNAL_PROXY_SECRET": configured_secret,
        }
        with patch.dict(os.environ, values, clear=False):
            missing = self._get(
                "/courses",
                remote_address="192.0.2.25",
                headers=self.student_headers,
            )
            wrong = self._get(
                "/courses",
                remote_address="192.0.2.25",
                headers={
                    **self.student_headers,
                    "X-Rocky-Internal-Secret": "wrong-secret",
                },
            )
            trusted = self._get(
                "/courses",
                remote_address="192.0.2.25",
                headers={
                    **self.student_headers,
                    "X-Rocky-Internal-Secret": configured_secret,
                },
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(trusted.status_code, 200)

    def test_production_never_uses_the_secretless_loopback_fallback(self):
        values = {
            "ROCKY_APP_ENV": "production",
            "ROCKY_INTERNAL_PROXY_SECRET": "",
        }
        with patch.dict(os.environ, values, clear=False):
            response = self._get(
                "/courses",
                remote_address="127.0.0.1",
                headers=self.student_headers,
            )

        self.assertEqual(response.status_code, 401)

    def test_production_accepts_only_the_matching_proxy_secret(self):
        configured_secret = "synthetic-production-proxy-secret"
        values = {
            "ROCKY_APP_ENV": "production",
            "ROCKY_INTERNAL_PROXY_SECRET": configured_secret,
        }
        with patch.dict(os.environ, values, clear=False):
            invalid_admin_flag = self._get(
                "/users",
                remote_address="127.0.0.1",
                headers={
                    "X-Rocky-User-Email": "admin.local@kent.edu",
                    "X-Rocky-User-Is-Admin": "yes",
                    "X-Rocky-Internal-Secret": configured_secret,
                },
            )
            trusted = self._get(
                "/users",
                remote_address="127.0.0.1",
                headers={
                    **self.admin_headers,
                    "X-Rocky-Internal-Secret": configured_secret,
                },
            )

        self.assertEqual(invalid_admin_flag.status_code, 403)
        self.assertEqual(trusted.status_code, 200)

    def test_preview_user_directory_is_limited_to_the_trusted_boundary(self):
        values = {
            "ROCKY_APP_ENV": "development",
            "ROCKY_INTERNAL_PROXY_SECRET": "",
        }
        with patch.dict(os.environ, values, clear=False):
            local = self._get(
                "/auth/preview-users",
                remote_address="127.0.0.1",
            )
            remote = self._get(
                "/auth/preview-users",
                remote_address="192.0.2.25",
            )
            health = self._get("/health", remote_address="192.0.2.25")

        self.assertEqual(local.status_code, 200)
        self.assertEqual(remote.status_code, 403)
        self.assertEqual(health.status_code, 200)

    def test_management_api_does_not_enable_browser_cors(self):
        response = self.client.options(
            "/courses",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Rocky-User-Email",
            },
        )

        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertNotIn("Access-Control-Allow-Headers", response.headers)


class NginxTrustBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.nginx_config = (root / "deploy/nginx/rocky.cs.kent.edu.conf").read_text(
            encoding="utf-8"
        )

    def _location_block(self, path: str) -> str:
        marker = f"    location = {path} {{"
        start = self.nginx_config.index(marker)
        next_location = self.nginx_config.find("\n    location ", start + len(marker))
        return self.nginx_config[start : next_location if next_location >= 0 else None]

    def test_public_api_locations_strip_internal_identity_headers(self):
        internal_headers = (
            "X-Rocky-Internal-Secret",
            "X-Rocky-User-Id",
            "X-Rocky-User-Email",
            "X-Rocky-User-Name",
            "X-Rocky-User-Is-Admin",
        )
        for path in ("/v1/responses", "/v1/models"):
            with self.subTest(path=path):
                block = self._location_block(path)
                for header in internal_headers:
                    self.assertIn(f'proxy_set_header {header} "";', block)

    def test_public_api_has_coarse_ingress_rate_limiting(self):
        self.assertIn(
            "limit_req_zone $binary_remote_addr "
            "zone=rocky_public_api_per_ip:10m rate=120r/m;",
            self.nginx_config,
        )
        for path in ("/v1/responses", "/v1/models"):
            with self.subTest(path=path):
                block = self._location_block(path)
                self.assertIn(
                    "limit_req zone=rocky_public_api_per_ip burst=120 nodelay;",
                    block,
                )
                self.assertIn("limit_req_status 429;", block)
        self.assertIn(
            "error_page 429 = @rocky_ingress_rate_limited;",
            self.nginx_config,
        )
        gateway_block = self.nginx_config[
            self.nginx_config.index("    location @rocky_ingress_rate_limited {") :
        ]
        self.assertIn("add_header Retry-After \"1\" always;", gateway_block)
        self.assertIn('"code":"ingress_rate_limit_exceeded"', gateway_block)

    def test_public_generation_body_limit_matches_the_application(self):
        block = self._location_block("/v1/responses")
        self.assertIn("client_max_body_size 256k;", block)


if __name__ == "__main__":
    unittest.main()
