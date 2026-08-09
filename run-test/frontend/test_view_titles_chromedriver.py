from selenium.webdriver.common.by import By
from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class ViewTitleE2ETests(FrontendBrowserTestCase):
    def _assert_document_title(self, expected: str):
        self.wait.until(
            lambda driver: driver.title == expected,
            message=f"Expected document title: {expected}",
        )

    def test_each_view_displays_expected_title(self):
        self._log("Opening login preview page.")
        self.driver.get(f"{BASE_URL}/login/preview")

        self._log("Authenticating through preview login.")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')][.//span[contains(@class,'preview-role') and normalize-space()='admin']]//button",
        )
        self._wait_for_post_login_navigation()

        self._assert_title("Dashboard")
        self._assert_document_title("Dashboard | Rocky")
        self._log("Verified default dashboard title after login.")

        view_expectations = [
            ("Users", "User Management", "Users | Rocky"),
            ("Courses", "Courses", "Courses | Rocky"),
            ("Analytics", "Analytics", "Analytics | Rocky"),
            ("Account", "Account Profile", "Account | Rocky"),
            ("Help", "Help Center", "Help Center | Rocky"),
            ("Chat", "Rocky AI", "Chat | Rocky"),
            ("Dashboard", "Dashboard", "Dashboard | Rocky"),
        ]

        for nav_text, expected_title, expected_document_title in view_expectations:
            self._log(f"Navigating to view: {nav_text}")
            class_filter = " and not(contains(@class,'mobile-help-link'))" if nav_text == "Help" else ""
            self._click_element(
                By.XPATH,
                f"//nav[contains(@class,'sidebar')]//button[normalize-space()='{nav_text}'{class_filter}]",
            )

            if nav_text == "Courses":
                self._log("Selecting first course from Courses popout.")
                self._click_element(By.CSS_SELECTOR, ".course-popout-item")

            if nav_text == "Chat":
                self.wait.until(
                    lambda driver: driver.find_element(
                        By.CSS_SELECTOR, ".chat-workspace-header h1"
                    ).text.strip()
                    == expected_title,
                    message="Expected the Chat workspace heading.",
                )
            else:
                self._assert_title(expected_title)
            self._assert_document_title(expected_document_title)
            self._log(f"Verified view title: {expected_title}")


if __name__ == "__main__":
    import unittest

    unittest.main()
