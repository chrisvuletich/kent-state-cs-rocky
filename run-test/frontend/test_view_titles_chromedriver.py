from urllib.parse import parse_qs, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class ViewTitleE2ETests(FrontendBrowserTestCase):
    def _assert_document_title(self, expected: str):
        self.wait.until(
            lambda driver: driver.title == expected,
            message=f"Expected document title: {expected}",
        )

    def _query_value(self, name: str) -> str | None:
        return parse_qs(urlparse(self.driver.current_url).query).get(name, [None])[0]

    def test_each_view_displays_expected_title(self):
        self._login_as_preview_role("admin")

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
            self._click_sidebar_destination(nav_text)

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

    def test_course_deep_link_survives_reload_and_browser_history(self):
        self._login_as_preview_role("admin")
        course_link = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.course-card")),
            message="Expected an addressable Dashboard course.",
        )
        course_name = course_link.find_element(By.CSS_SELECTOR, ".course-name").text.strip()
        course_link.click()

        self._assert_title("Courses")
        self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//section[contains(@class,'course-workspace')]"
                    f"//h2[normalize-space()='{course_name}']",
                )
            ),
            message="Expected the linked course workspace.",
        )
        self.assertEqual(self._query_value("frame"), "courses")
        self.assertIsNotNone(self._query_value("course"))
        course_url = self.driver.current_url

        self.driver.refresh()
        self._assert_title("Courses")
        self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//section[contains(@class,'course-workspace')]"
                    f"//h2[normalize-space()='{course_name}']",
                )
            )
        )

        self._click_sidebar_destination("Dashboard")
        self._assert_title("Dashboard")
        self.assertEqual(self._query_value("frame"), "dashboard")

        self.driver.back()
        self.wait.until(lambda driver: driver.current_url == course_url)
        self._assert_title("Courses")
        self.driver.forward()
        self._assert_title("Dashboard")

    def test_invalid_and_unauthorized_deep_links_fail_safely(self):
        self._login_as_preview_role("student")
        self.driver.get(f"{BASE_URL}/?frame=audit")
        self._assert_title("Dashboard")
        self.assertEqual(self._query_value("frame"), "dashboard")

        self.driver.get(f"{BASE_URL}/?course=999999999&frame=courses")
        self._assert_title("Courses")
        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//h2[normalize-space()='Course Unavailable']")
            )
        )
        self.assertIn("not available to your account", self.driver.find_element(By.TAG_NAME, "body").text)

    def test_secondary_navigation_links_use_canonical_urls(self):
        self._login_as_preview_role("admin")
        self._click_sidebar_destination("Admin Panel")
        self._click_element(By.XPATH, "//a[normalize-space()='View All Logs']")
        self._assert_title("Audit Logs")
        self.assertEqual(self._query_value("frame"), "audit")

        self._click_sidebar_destination("Help")
        self._assert_title("Help Center")
        self._click_element(
            By.XPATH,
            "//a[contains(@class,'help-resource-card')]"
            "[.//p[normalize-space()='Ready to go?']]",
        )
        self._assert_title("Dashboard")
        self.assertEqual(self._query_value("frame"), "dashboard")

        self._login_as_preview_role("student")
        self._click_sidebar_destination("Account")
        self._assert_title("Account Profile")
        self.wait.until(lambda _driver: self._query_value("frame") == "account")
        self.driver.get(f"{BASE_URL}/")
        self._assert_title("Account Profile")
        self.assertIsNone(self._query_value("frame"))
        account_course = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.account-course-row")),
            message="Expected the student's Account course link.",
        )
        account_course.click()
        self._assert_title("Courses")
        self.assertEqual(self._query_value("frame"), "courses")
        self.assertIsNotNone(self._query_value("course"))


if __name__ == "__main__":
    import unittest

    unittest.main()
