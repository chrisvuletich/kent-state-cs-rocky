from __future__ import annotations

import os
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class RoleJourneyE2ETests(FrontendBrowserTestCase):
    def capture_evidence(self, name: str) -> None:
        output_dir = os.getenv("ROCKY_E2E_SCREENSHOT_DIR", "").strip()
        if not output_dir:
            return
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(destination / f"{name}.png"))

    def _login_as(self, email: str) -> None:
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')]"
            f"[.//p[normalize-space()='{email}']]//button",
        )
        self._wait_for_post_login_navigation()

    def _open_course_menu(self) -> None:
        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button"
            "[.//span[contains(@class,'nav-link-label') and normalize-space()='Courses']]",
        )
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-popout[role='menu']")),
            message="Expected the course list popout.",
        )

    def _open_course_from_sidebar(self, course_name: str) -> None:
        self._open_course_menu()
        self._click_element(
            By.XPATH,
            "//div[contains(@class,'course-popout-list')]"
            f"//button[.//span[contains(@class,'course-item-name') and normalize-space()='{course_name}']]",
        )
        self._assert_title("Courses")
        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, f"//section[contains(@class,'course-workspace')]//h2[normalize-space()='{course_name}']")
            ),
            message=f"Expected the {course_name} course workspace.",
        )

    def test_1_student_key_is_disclosed_once_and_can_be_dismissed(self):
        self._login_as("student.local@kent.edu")
        self._open_course_from_sidebar("Database Systems")

        personal_panel = self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'course-panel')][.//h3[normalize-space()='Personal Key 1']]",
                )
            ),
            message="Expected the student's personal key slot.",
        )
        personal_panel.find_element(By.XPATH, ".//button[normalize-space()='Generate Key']").click()

        reveal = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-key-reveal")),
            message="Expected a newly generated key to be shown once.",
        )
        raw_key = reveal.find_element(By.TAG_NAME, "code").text.strip()
        self.assertTrue(raw_key.startswith("sk_kent_"))
        self.assertIn("will not be shown again", reveal.text.lower())

        reveal.find_element(By.XPATH, ".//button[normalize-space()='Copy API Key']").click()
        self.wait.until(
            lambda driver: any(
                message in driver.find_element(By.CSS_SELECTOR, ".course-key-copy-status").text
                for message in ("Copied to clipboard", "Select and copy the key manually")
            ),
            message="Expected accessible feedback after the copy action.",
        )
        reveal.find_element(By.XPATH, ".//button[normalize-space()='Dismiss']").click()
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".course-key-reveal")),
            message="Expected dismissing the key to remove its plaintext value.",
        )

        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button[normalize-space()='Dashboard']",
        )
        self._open_course_from_sidebar("Database Systems")
        self.assertEqual(len(self.driver.find_elements(By.CSS_SELECTOR, ".course-key-reveal")), 0)
        self.assertNotIn(raw_key, self.driver.page_source)
        self.capture_evidence("student-key-copy-once")

    def test_2_student_group_keys_are_read_only(self):
        self._login_as("student.local@kent.edu")
        self._open_course_from_sidebar("Software Engineering I")
        self._click_element(By.XPATH, "//button[normalize-space()='Team Alpha']")

        group_panel = self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'course-panel')][.//h3[normalize-space()='Team Alpha Key 1']]",
                )
            ),
            message="Expected the student's shared group key summary.",
        )
        self.assertIn(
            "managed by your course instructor or teaching assistant",
            group_panel.text.lower(),
        )
        self.assertEqual(
            len(
                group_panel.find_elements(
                    By.XPATH,
                    ".//button[normalize-space()='Generate Key' or normalize-space()='Regenerate Key' or normalize-space()='Remove Key']",
                )
            ),
            0,
        )
        self.assertEqual(len(group_panel.find_elements(By.TAG_NAME, "input")), 0)
        self.capture_evidence("student-group-key-read-only")

    def test_3_instructor_sees_own_student_and_group_controls_only(self):
        self._login_as("instructor.local@kent.edu")
        self._open_course_menu()
        self.assertEqual(
            len(
                self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'course-popout-list')]"
                    "//span[contains(@class,'course-item-name') and normalize-space()='Data Structures & Algorithms']",
                )
            ),
            0,
        )
        self._click_element(
            By.XPATH,
            "//div[contains(@class,'course-popout-list')]"
            "//button[.//span[contains(@class,'course-item-name') and normalize-space()='Software Engineering I']]",
        )
        self._assert_title("Courses")
        self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//section[contains(@class,'course-workspace')]"
                    "//h2[normalize-space()='Software Engineering I']",
                )
            )
        )

        self._click_element(By.XPATH, "//button[normalize-space()='Students']")
        student_select = Select(
            self.wait.until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//div[contains(@class,'course-group-create-row')]/select")
                )
            )
        )
        student_option = next(
            option for option in student_select.options if option.text.strip() == "Mila Ross"
        )
        student_select.select_by_value(student_option.get_attribute("value"))

        student_panel = self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'course-panel')][.//h3[normalize-space()='Mila Ross Key 1']]",
                )
            ),
            message="Expected the instructor's student key controls.",
        )
        student_panel.find_element(By.XPATH, ".//button[normalize-space()='Generate Key']").click()
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-key-reveal")),
            message="Expected the instructor-generated student key disclosure.",
        )

        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")
        group_panel = self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    "//div[contains(@class,'course-panel')][.//h3[normalize-space()='Team Alpha Key 1']]",
                )
            ),
            message="Expected the instructor's group key controls.",
        )
        group_panel.find_element(By.XPATH, ".//button[normalize-space()='Regenerate Key']").click()
        warning = self.wait.until(EC.alert_is_present())
        self.assertIn("immediately invalidate", warning.text.lower())
        warning.dismiss()
        self.capture_evidence("instructor-student-group-keys")

    def test_4_logout_clears_account_state_and_protects_the_app(self):
        self._login_as("admin.local@kent.edu")
        self.driver.execute_script(
            """
            localStorage.setItem('rocky.currentUser', 'phase-four-user');
            localStorage.setItem('rocky_current_frame', 'phase-four-frame');
            localStorage.setItem('rocky_selected_course', 'phase-four-course');
            """
        )
        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button[normalize-space()='Account']",
        )
        self._click_element(By.XPATH, "//button[normalize-space()='Log Out']")
        self.wait.until(EC.url_contains("/login"))
        self.wait.until(EC.title_is("Sign in | Rocky"))

        cached_values = self.driver.execute_script(
            """
            return [
              localStorage.getItem('rocky.currentUser'),
              localStorage.getItem('rocky_current_frame'),
              localStorage.getItem('rocky_selected_course')
            ];
            """
        )
        self.assertEqual(cached_values, [None, None, None])

        self.driver.get(f"{BASE_URL}/")
        self.wait.until(EC.url_contains("/login"))
        with self.assertRaises(NoSuchElementException):
            self.driver.find_element(By.CSS_SELECTOR, ".app-shell")
        self.capture_evidence("logout-clears-account-state")


if __name__ == "__main__":
    import unittest

    unittest.main()
