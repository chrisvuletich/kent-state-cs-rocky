from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class DialogAccessibilityE2ETests(FrontendBrowserTestCase):
    def _active_element_is_inside(self, selector: str) -> bool:
        return bool(
            self.driver.execute_script(
                "return document.querySelector(arguments[0])?.contains(document.activeElement) || false;",
                selector,
            )
        )

    def _element_is_inert(self, selector: str) -> bool:
        return bool(
            self.driver.execute_script(
                """
                const element = document.querySelector(arguments[0]);
                return Boolean(element?.inert || element?.hasAttribute('inert'));
                """,
                selector,
            )
        )

    def _assert_tab_wraps_inside(self, selector: str):
        last_focusable = self.driver.execute_script(
            """
            const scope = document.querySelector(arguments[0]);
            const elements = [...scope.querySelectorAll(
              'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), '
              + 'textarea:not(:disabled), details > summary:first-of-type, '
              + '[tabindex]:not([tabindex="-1"])'
            )].filter((element) =>
              element.offsetWidth > 0 || element.offsetHeight > 0 || element.getClientRects().length > 0
            );
            const last = elements.at(-1);
            last.focus();
            return last;
            """,
            selector,
        )
        last_focusable.send_keys(Keys.TAB)
        self.wait.until(
            lambda _driver: self._active_element_is_inside(selector),
            message=f"Expected Tab focus to remain inside {selector}.",
        )

    def _press_escape(self):
        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)

    def test_course_modals_trap_focus_and_restore_their_openers(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")

        create_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Create Course']"))
        )
        create_button.click()
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout")))
        self.wait.until(
            lambda driver: driver.switch_to.active_element.get_attribute("id")
            == "global-create-course-name-input"
        )
        self.assertTrue(self._element_is_inert("nav.sidebar"))
        self._assert_tab_wraps_inside(".course-composer-popout")
        self._press_escape()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout")))
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", create_button
            )
        )

        course_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-controls='rocky-course-menu']")
            )
        )
        course_button.click()
        self.wait.until(lambda _driver: course_button.get_attribute("aria-expanded") == "true")
        self.assertIsNone(course_button.get_attribute("aria-haspopup"))
        course_group = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#rocky-course-menu[role='group']"))
        )
        course_group.find_element(By.XPATH, ".//button[normalize-space()='Create']").click()
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout")))
        self._press_escape()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout")))
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", course_button
            ),
            message="Expected focus to return to the persistent Courses disclosure.",
        )

        self.driver.get(f"{BASE_URL}/?course=1&frame=courses")
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Edit Roster']")
        add_email_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Add Email']"))
        )
        add_email_button.click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "add-course-member-email")))
        self.wait.until(
            lambda driver: driver.switch_to.active_element.get_attribute("id")
            == "add-course-member-email"
        )
        self.assertTrue(self._element_is_inert("nav.sidebar"))
        self._press_escape()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".popup-card")))
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", add_email_button
            )
        )

    def test_mobile_navigation_reports_state_and_closes_topmost_disclosure_first(self):
        self._login_as_preview_role("admin")
        self._set_viewport("phone")
        self.driver.get(f"{BASE_URL}/?frame=dashboard")
        self._assert_title("Dashboard")

        hamburger = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.hamburger"))
        )
        self.assertEqual(hamburger.get_attribute("aria-expanded"), "false")
        hamburger.click()
        self.wait.until(lambda _driver: hamburger.get_attribute("aria-expanded") == "true")
        self.wait.until(
            lambda driver: driver.execute_script(
                """
                const sidebar = document.querySelector('#rocky-sidebar-navigation');
                const bounds = sidebar?.getBoundingClientRect();
                return Boolean(bounds && bounds.left >= -1 && bounds.right > 0);
                """
            ),
            message="Expected the mobile navigation transition to finish.",
        )
        self.wait.until(lambda _driver: self._active_element_is_inside("#rocky-sidebar-navigation"))
        self.assertTrue(self._element_is_inert(".app-content"))
        self._assert_tab_wraps_inside("#rocky-sidebar-navigation")

        course_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-controls='rocky-course-menu']")
            )
        )
        course_button.click()
        self.wait.until(lambda _driver: course_button.get_attribute("aria-expanded") == "true")
        self.assertIsNone(course_button.get_attribute("aria-haspopup"))
        self.assertEqual(
            self.driver.find_element(By.ID, "rocky-course-menu").get_attribute("role"),
            "group",
        )
        self.wait.until(lambda _driver: self._active_element_is_inside("#rocky-course-menu"))

        self._press_escape()
        self.wait.until(lambda _driver: course_button.get_attribute("aria-expanded") == "false")
        self.assertEqual(hamburger.get_attribute("aria-expanded"), "true")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", course_button
            )
        )

        self._press_escape()
        self.wait.until(lambda _driver: hamburger.get_attribute("aria-expanded") == "false")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", hamburger
            )
        )

    def test_dashboard_and_account_disclosures_manage_focus(self):
        self._login_as_preview_role("student")
        self._set_viewport("desktop")

        view_button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-controls='dashboard-view-menu']"))
        )
        view_button.click()
        self.wait.until(lambda _driver: view_button.get_attribute("aria-expanded") == "true")
        self.wait.until(lambda _driver: self._active_element_is_inside("#dashboard-view-menu"))
        self.assertIsNone(view_button.get_attribute("aria-haspopup"))
        self.assertEqual(
            self.driver.find_element(By.ID, "dashboard-view-menu").get_attribute("role"),
            "group",
        )

        self.driver.find_element(By.CSS_SELECTOR, ".view-title h1").click()
        self.wait.until(lambda _driver: view_button.get_attribute("aria-expanded") == "false")

        view_button.click()
        self.wait.until(lambda _driver: view_button.get_attribute("aria-expanded") == "true")
        self._press_escape()
        self.wait.until(lambda _driver: view_button.get_attribute("aria-expanded") == "false")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", view_button
            )
        )

        self._click_sidebar_destination("Account")
        self._assert_title("Account Profile")
        avatar_button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".account-avatar-button"))
        )
        avatar_button.click()
        self.wait.until(lambda _driver: avatar_button.get_attribute("aria-expanded") == "true")
        self.wait.until(lambda _driver: self._active_element_is_inside("#account-avatar-picker"))
        self._press_escape()
        self.wait.until(lambda _driver: avatar_button.get_attribute("aria-expanded") == "false")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", avatar_button
            )
        )

    def test_course_composer_stays_inside_narrow_viewport(self):
        self._login_as_preview_role("admin")
        self._set_viewport("narrow_phone")

        create_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Create Course']"))
        )
        create_button.click()
        dialog = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".course-composer-popout"))
        )

        dialog_bounds = self.driver.execute_script(
            """
            const bounds = arguments[0].getBoundingClientRect();
            return { top: bounds.top, bottom: bounds.bottom, viewportHeight: innerHeight };
            """,
            dialog,
        )
        self.assertGreaterEqual(dialog_bounds["top"], -1)
        self.assertLessEqual(dialog_bounds["bottom"], dialog_bounds["viewportHeight"] + 1)

        submit_button = dialog.find_element(
            By.XPATH, ".//button[normalize-space()='Create Course']"
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({ block: 'nearest' });", submit_button
        )
        action_bounds = self.driver.execute_script(
            """
            const bounds = arguments[0].getBoundingClientRect();
            return { top: bounds.top, bottom: bounds.bottom, viewportHeight: innerHeight };
            """,
            submit_button,
        )
        self.assertGreaterEqual(action_bounds["top"], dialog_bounds["top"] - 1)
        self.assertLessEqual(action_bounds["bottom"], action_bounds["viewportHeight"] + 1)

    def test_course_disclosure_opens_while_courses_refresh(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.course-card")))

        self.driver.execute_script(
            """
            const originalFetch = window.fetch.bind(window);
            window.fetch = (input, init) => {
              const url = typeof input === 'string' ? input : input.url;
              if (url.includes('/api/backend/courses')) {
                return new Promise((resolve, reject) => {
                  setTimeout(() => originalFetch(input, init).then(resolve, reject), 750);
                });
              }
              return originalFetch(input, init);
            };
            """
        )

        course_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-controls='rocky-course-menu']")
            )
        )
        course_button.click()
        self.wait.until(lambda _driver: course_button.get_attribute("aria-expanded") == "true")
        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//*[@id='rocky-course-menu']//p[normalize-space()='Loading courses...']")
            ),
            message="Expected the disclosure to expose its loading state immediately.",
        )
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#rocky-course-menu a.course-popout-item"))
        )

    def test_mobile_chat_history_is_a_modal_drawer(self):
        self._login_as_preview_role("student")
        self._set_viewport("phone")
        self.driver.get(f"{BASE_URL}/?frame=chat")
        self.wait.until(EC.visibility_of_element_located((By.ID, "rocky-chat-input")))

        history_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-controls='rocky-chat-history']")
            )
        )
        history_button.click()
        self.wait.until(lambda _driver: history_button.get_attribute("aria-expanded") == "true")
        history_drawer = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "#rocky-chat-history[role='dialog']"))
        )
        self.wait.until(lambda _driver: self._active_element_is_inside("#rocky-chat-history"))
        self.assertEqual(history_drawer.get_attribute("aria-modal"), "true")
        self.assertTrue(self._element_is_inert(".chat-workspace"))
        self._assert_tab_wraps_inside("#rocky-chat-history")

        self._press_escape()
        self.wait.until(lambda _driver: history_button.get_attribute("aria-expanded") == "false")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", history_button
            )
        )

    def test_alert_and_image_dialogs_restore_focus(self):
        self._login_as_preview_role("admin")
        self._set_viewport("desktop")
        self.driver.get(f"{BASE_URL}/?frame=users")
        self._assert_title("User Management")

        account_checkbox = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "tbody input[type='checkbox']:not(:disabled)")
            )
        )
        account_checkbox.click()
        deactivate_button = self.wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Deactivate selected']"))
        )
        deactivate_button.click()
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "[role='alertdialog']"))
        )
        self.wait.until(lambda _driver: self._active_element_is_inside("[role='alertdialog']"))
        self.assertTrue(self._element_is_inert("nav.sidebar"))
        self._press_escape()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "[role='alertdialog']")))
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", deactivate_button
            )
        )

        self.driver.get(f"{BASE_URL}/?doc=course-roster&frame=help")
        self._assert_title("Course Roster Workflow")
        image_button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".markdown-image-preview"))
        )
        image_button.click()
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "dialog.markdown-image-dialog"))
        )
        self.wait.until(
            lambda _driver: self._active_element_is_inside("dialog.markdown-image-dialog")
        )
        self.assertTrue(self._element_is_inert("nav.sidebar"))
        self._assert_tab_wraps_inside("dialog.markdown-image-dialog")
        self._press_escape()
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "dialog.markdown-image-dialog"))
        )
        self.wait.until(
            lambda driver: driver.execute_script(
                "return document.activeElement === arguments[0];", image_button
            )
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
