from __future__ import annotations

from frontend.test_support import BASE_URL, FrontendBrowserTestCase, UI_VIEWPORTS


class PreviewLoginSmokeTests(FrontendBrowserTestCase):
    def test_preview_login_reaches_dashboard(self):
        self._log("Opening login preview page.")
        self._log("Authenticating through preview login.")
        self._login_as_preview_role("admin")

        self._assert_title("Dashboard")

    def test_dashboard_renders_cleanly_at_reference_viewports(self):
        self._login_as_preview_role("admin")

        # Drain login-page messages so each subtest reports only errors from
        # the dashboard load at the viewport being checked.
        self._read_browser_console()

        for viewport_name in UI_VIEWPORTS:
            with self.subTest(viewport=viewport_name):
                self._set_viewport(viewport_name)
                self.driver.get(f"{BASE_URL}/?frame=dashboard")
                self._assert_title("Dashboard")
                self.assertEqual(self.driver.title, "Dashboard | Rocky")
                body_text = self.driver.find_element("tag name", "body").text.strip()
                self.assertGreater(len(body_text), 0)
                self._assert_no_framework_error_overlay()
                self._assert_no_document_horizontal_overflow()
                self._assert_no_browser_console_errors(
                    # The frontend-only suite deliberately does not start the
                    # separate chat upstream. Dashboard renders a handled
                    # "Recent chats are unavailable" state for this response.
                    allowed_message_fragments=(
                        f"{BASE_URL}/api/chat/conversations - Failed to load resource: "
                        "the server responded with a status of 502",
                    ),
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
