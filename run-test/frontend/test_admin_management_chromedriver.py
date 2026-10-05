from __future__ import annotations

import tempfile
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class AdminManagementE2ETests(FrontendBrowserTestCase):
    def _open_roster_as(self, email):
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            f"//article[contains(@class,'preview-user-card')][.//p[normalize-space()='{email}']]//button",
        )
        self._wait_for_post_login_navigation()
        self.driver.get(f"{BASE_URL}/?frame=courses&course=1")
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Edit Roster']")

    def test_canvas_roster_import_uses_emails_and_can_retry_invalid_files(self):
        self._open_roster_as("admin.local@kent.edu")
        upload_selector = "input[aria-label='Import course roster from Canvas CSV']"
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, upload_selector)))

        # Inspect the saved roster through the same authenticated API the UI uses.
        def saved_members():
            return self.driver.execute_async_script(
                "const done = arguments[arguments.length - 1];"
                "fetch('/api/backend/courses/1').then(r => r.json())"
                ".then(course => done(course.members)).catch(() => done(null));"
            )

        before = saved_members()
        self.assertIsInstance(before, list)
        with tempfile.TemporaryDirectory(prefix="rocky-canvas-roster-") as directory:
            csv_path = Path(directory) / "roster.csv"
            csv_path.write_text(
                "Student Name,Student ID,Student SIS ID,Email,Section Name\n"
                "New Student,155843,,canvas.new@kent.edu,Section A\n"
                "Invalid Student,174726,,,Section A\n",
                encoding="utf-8",
            )
            self.driver.find_element(By.CSS_SELECTOR, upload_selector).send_keys(str(csv_path))
            self.wait.until(EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".feedback-error"), "missing or invalid email"
            ))
            self.assertEqual(saved_members(), before)
            self.assertEqual(self.driver.find_element(By.CSS_SELECTOR, upload_selector).get_attribute("value"), "")

            # Same filename, now valid: a new student, an existing student,
            # a duplicate from another section, and an excluded admin account.
            csv_path.write_text(
                '\ufeffStudent Name,Student ID,Student SIS ID,Email,Section Name\r\n'
                '"Student, New",155843,,CANVAS.NEW@kent.edu,"Section A, morning"\r\n'
                'Existing Student,174726,,student.local@kent.edu,Section A\r\n'
                'New Student,155843,,canvas.new@kent.edu,Section B\r\n'
                'Admin,201028,,admin.local@kent.edu,Section A\r\n',
                encoding="utf-8",
            )
            self.driver.find_element(By.CSS_SELECTOR, upload_selector).send_keys(str(csv_path))
            self.wait.until(EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".feedback-success"), "Imported 2 unique email addresses"
            ))
            self.assertIn("Excluded 1 admin account", self.driver.find_element(By.CSS_SELECTOR, ".feedback-success").text)
            self.wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//table[contains(@class,'course-people-table')]//tr[.//td[normalize-space()='canvas.new@kent.edu']]")
            ))
            after = saved_members()
            emails = [member["email"] for member in after]
            self.assertEqual(len(after), len(before) + 1)
            self.assertEqual(emails.count("canvas.new@kent.edu"), 1)
            self.assertEqual(emails.count("student.local@kent.edu"), 1)
            self.assertNotIn("admin.local@kent.edu", emails)
            self.assertIsNone(next(member for member in after if member["email"] == "canvas.new@kent.edu")["id"])
            self._assert_no_framework_error_overlay()
            # The browser harness runs the backend, but not the chat service
            # used for the dashboard's recent conversations during login.
            self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))
            self.driver.save_screenshot(str(self._process_log_dir / "canvas-roster-import.png"))

            # Instructors do not have access to the admin user directory.
            # Reimporting by email must still work and keep existing members.
            self._open_roster_as("instructor.local@kent.edu")
            csv_path.write_text("Email\ncanvas.new@kent.edu\nstudent.local@kent.edu\n", encoding="utf-8")
            self.driver.find_element(By.CSS_SELECTOR, upload_selector).send_keys(str(csv_path))
            self.wait.until(EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".feedback-success"), "Imported 2 unique email addresses"
            ))
            self.assertEqual(saved_members(), after)
            self._assert_no_framework_error_overlay()
            self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))

        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))

    def test_whitelist_creation_and_audit_visibility(self):
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')][.//span[contains(@class,'preview-role') and normalize-space()='admin']]//button",
        )
        self._wait_for_post_login_navigation()

        self._click_sidebar_destination("Users")
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

        self._click_sidebar_destination("Admin Panel")
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
