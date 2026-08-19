from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class FormSemanticsE2ETests(FrontendBrowserTestCase):
    def _assert_field_error(self, field):
        self.assertEqual(field.get_attribute("aria-invalid"), "true")
        description_id = field.get_attribute("aria-describedby")
        self.assertTrue(description_id, "Expected the invalid field to reference its error.")
        error = self.driver.find_element(By.ID, description_id)
        self.assertTrue(error.is_displayed())
        self.assertTrue(error.text.strip())

    def _assert_visible_controls_are_labelled(self, scope_selector: str = "main"):
        unlabelled = self.driver.execute_script(
            """
            const scope = document.querySelector(arguments[0]);
            if (!scope) return [`Missing scope: ${arguments[0]}`];
            return [...scope.querySelectorAll('input:not([type="hidden"]), select, textarea')]
              .filter((control) => {
                const visible = control.getClientRects().length > 0;
                const hasLabel = Boolean(
                  control.labels?.length
                  || control.getAttribute('aria-label')?.trim()
                  || control.getAttribute('aria-labelledby')?.trim()
                );
                return visible && !hasLabel;
              })
              .map((control) => control.outerHTML.slice(0, 240));
            """,
            scope_selector,
        )
        self.assertEqual(
            unlabelled,
            [],
            f"Expected every visible form control in {scope_selector} to have a label.",
        )

    def test_form_errors_are_associated_with_their_fields(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        self._click_element(By.XPATH, "//button[normalize-space()='Create Course']")
        dialog = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout"))
        )
        self._assert_visible_controls_are_labelled(".course-composer-popout")
        dialog.find_element(
            By.XPATH, ".//button[normalize-space()='Create Course']"
        ).click()

        course_name = dialog.find_element(By.ID, "global-create-course-name-input")
        self._assert_field_error(course_name)
        self.assertEqual(
            self.driver.find_element(By.ID, "global-create-course-semester-year-input")
            .get_attribute("aria-label"),
            "Semester year",
        )

        course_name.send_keys("Accessible Systems")
        self.wait.until(lambda _driver: course_name.get_attribute("aria-invalid") is None)

        color_input = dialog.find_element(By.CSS_SELECTOR, ".color-code-input")
        color_input.send_keys(Keys.CONTROL, "a")
        color_input.send_keys("invalid")
        self._assert_field_error(color_input)

        dialog.find_element(By.XPATH, ".//button[normalize-space()='Close']").click()
        self._click_sidebar_destination("Users")
        self._assert_title("User Management")
        self._click_element(By.XPATH, "//button[normalize-space()='Whitelist accounts']")
        self._click_element(By.XPATH, "//button[normalize-space()='Add account']")

        for field_id in (
            "whitelist-first-name",
            "whitelist-last-name",
            "whitelist-email",
        ):
            self._assert_field_error(self.driver.find_element(By.ID, field_id))

        self._assert_visible_controls_are_labelled("#user-account-panel")

    def test_primary_route_forms_have_accessible_labels(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        route_titles = (
            ("analytics", "Analytics"),
            ("users", "User Management"),
            ("audit", "Audit Logs"),
            ("api-keys", "API Keys"),
            ("account", "Account Profile"),
            ("chat", "Rocky AI"),
        )
        for frame, title in route_titles:
            with self.subTest(frame=frame):
                self.driver.get(f"{BASE_URL}/?frame={frame}")
                if frame == "chat":
                    self.wait.until(
                        EC.text_to_be_present_in_element(
                            (By.CSS_SELECTOR, ".chat-workspace-header h1"), title
                        )
                    )
                else:
                    self._assert_title(title)
                self._assert_visible_controls_are_labelled()

        self.driver.get(f"{BASE_URL}/?course=1&frame=courses")
        self._assert_title("Courses")
        for tab_id in (
            "course-tab-home",
            "course-tab-students",
            "course-tab-groups",
            "course-tab-edit-roster",
            "course-tab-edit-groups",
            "course-tab-course-settings",
        ):
            with self.subTest(tab=tab_id):
                self._click_element(By.ID, tab_id)
                self._assert_visible_controls_are_labelled("#course-tab-panel")

    def test_tabs_support_roving_focus_and_arrow_keys(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        self._click_sidebar_destination("Users")
        self._assert_title("User Management")
        kent_tab = self.wait.until(
            EC.element_to_be_clickable((By.ID, "kent-accounts-tab")),
            message="Expected user-source tabs after account data finished loading.",
        )
        kent_tab.click()
        kent_tab.send_keys(Keys.ARROW_RIGHT)
        whitelist_tab = self.driver.find_element(By.ID, "whitelist-accounts-tab")
        self.wait.until(lambda _driver: whitelist_tab.get_attribute("aria-selected") == "true")
        self.assertEqual(self.driver.switch_to.active_element, whitelist_tab)
        self.assertEqual(whitelist_tab.get_attribute("tabindex"), "0")
        self.assertEqual(
            self.driver.find_element(By.ID, "user-account-panel").get_attribute(
                "aria-labelledby"
            ),
            "whitelist-accounts-tab",
        )

        self.driver.get(f"{BASE_URL}/?course=1&frame=courses")
        self._assert_title("Courses")
        home_tab = self.wait.until(EC.element_to_be_clickable((By.ID, "course-tab-home")))
        home_tab.click()
        home_tab.send_keys(Keys.END)
        settings_tab = self.driver.find_element(By.ID, "course-tab-course-settings")
        self.wait.until(lambda _driver: settings_tab.get_attribute("aria-selected") == "true")
        self.assertEqual(self.driver.switch_to.active_element, settings_tab)
        self.assertEqual(
            self.driver.find_element(By.ID, "course-tab-panel").get_attribute(
                "aria-labelledby"
            ),
            "course-tab-course-settings",
        )

        self._set_viewport("phone")
        self.driver.get(f"{BASE_URL}/?frame=analytics")
        self._assert_title("Analytics")
        breakdown_tab = self.wait.until(
            EC.element_to_be_clickable((By.ID, "analytics-breakdown-tab"))
        )
        breakdown_tab.click()
        breakdown_tab.send_keys(Keys.ARROW_RIGHT)
        requests_tab = self.driver.find_element(By.ID, "analytics-requests-tab")
        self.wait.until(lambda _driver: requests_tab.get_attribute("aria-selected") == "true")
        self.assertEqual(self.driver.switch_to.active_element, requests_tab)

    def test_sort_headers_are_buttons_and_announce_direction(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        self.driver.get(f"{BASE_URL}/?frame=api-keys")
        self._assert_title("API Keys")
        semester_sort = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.api-key-sort"))
        )
        semester_header = semester_sort.find_element(By.XPATH, "..")
        self.assertEqual(semester_sort.tag_name, "button")
        self.assertEqual(semester_header.get_attribute("aria-sort"), "descending")
        semester_sort.click()
        self.wait.until(
            lambda driver: driver.find_element(
                By.XPATH,
                "//button[contains(@class,'api-key-sort') and starts-with(normalize-space(),'Semester')]/parent::th",
            ).get_attribute("aria-sort")
            == "ascending"
        )

        self.driver.get(f"{BASE_URL}/?course=1&frame=courses")
        self._assert_title("Courses")
        self._click_element(By.ID, "course-tab-edit-roster")
        roster_sort = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.course-table-sort"))
        )
        roster_header = roster_sort.find_element(By.XPATH, "..")
        self.assertEqual(roster_sort.tag_name, "button")
        self.assertEqual(roster_header.get_attribute("aria-sort"), "ascending")
        roster_sort.click()
        self.wait.until(
            lambda driver: driver.find_element(
                By.XPATH, "//button[contains(@class,'course-table-sort')]/parent::th"
            ).get_attribute("aria-sort")
            == "descending"
        )

    def test_active_navigation_has_one_current_page(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        current = self.wait.until(
            lambda driver: driver.find_elements(
                By.CSS_SELECTOR, "nav.sidebar [aria-current='page']"
            )
        )
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].text.strip(), "Dashboard")

        self._click_sidebar_destination("Users")
        self._assert_title("User Management")
        current = self.driver.find_elements(By.CSS_SELECTOR, "nav.sidebar [aria-current='page']")
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].text.strip(), "Users")

        self.driver.get(f"{BASE_URL}/?course=1&frame=courses")
        self._assert_title("Courses")
        course_button = self.driver.find_element(
            By.CSS_SELECTOR, "button[aria-controls='rocky-course-menu']"
        )
        course_button.click()
        self.wait.until(lambda _driver: course_button.get_attribute("aria-expanded") == "true")
        current = self.wait.until(
            lambda driver: driver.find_elements(
                By.CSS_SELECTOR, "nav.sidebar [aria-current='page']"
            )
        )
        self.assertEqual(len(current), 1)
        self.assertIn("Software Engineering I", current[0].text)


if __name__ == "__main__":
    import unittest

    unittest.main()
