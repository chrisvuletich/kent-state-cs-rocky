from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class AdminManagementE2ETests(FrontendBrowserTestCase):
    def test_whitelist_creation_and_audit_visibility(self):
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')][.//span[contains(@class,'preview-role') and normalize-space()='admin']]//button",
        )
        self._wait_for_post_login_navigation()

        self._click_element(By.XPATH, "//nav[contains(@class,'sidebar')]//button[normalize-space()='Users']")
        self._assert_title("User Management")
        self._click_element(By.XPATH, "//button[normalize-space()='Whitelist accounts']")

        self.driver.find_element(By.CSS_SELECTOR, "input[aria-label='Whitelist first name']").send_keys("Browser")
        self.driver.find_element(By.CSS_SELECTOR, "input[aria-label='Whitelist last name']").send_keys("Instructor")
        self.driver.find_element(By.CSS_SELECTOR, "input[aria-label='Whitelist email']").send_keys("browser.instructor@example.com")
        Select(self.driver.find_element(By.CSS_SELECTOR, "select[aria-label='Whitelist role']")).select_by_value("instructor")
        self._click_element(By.XPATH, "//button[normalize-space()='Add account']")

        created_row = self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//tr[.//td[contains(normalize-space(),'browser.instructor@example.com')]]")
            ),
            message="Expected the newly created whitelist account row.",
        )
        self.assertIn("instructor", created_row.text.lower())

        self._click_element(By.XPATH, "//nav[contains(@class,'sidebar')]//button[normalize-space()='Admin Panel']")
        self.wait.until(
            EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".admin-panel h1"), "Admin Dashboard"),
            message="Expected Admin Dashboard to render.",
        )
        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".audit-section"),
                "whitelist added",
            ),
            message="Expected the whitelist mutation in Recent Audit Logs.",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
