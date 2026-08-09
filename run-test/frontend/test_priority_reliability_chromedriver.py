from __future__ import annotations

import os
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class PriorityReliabilityE2ETests(FrontendBrowserTestCase):
    def capture_evidence(self, name: str) -> None:
        output_dir = os.getenv("ROCKY_E2E_SCREENSHOT_DIR", "").strip()
        if not output_dir:
            return

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(destination / f"{name}.png"))

    def _login_as_admin(self) -> None:
        # Browser methods in this class share one isolated profile. Always end
        # the previous session so the test order cannot affect preview login.
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')]"
            "[.//span[contains(@class,'preview-role') and normalize-space()='admin']]//button",
        )
        self._wait_for_post_login_navigation()

    def test_chat_stop_reconciles_history_without_offering_duplicate_retry(self):
        self._login_as_admin()
        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button[normalize-space()='Chat']",
        )

        prompt = "Explain a stack in one sentence."
        textarea = self.wait.until(
            EC.element_to_be_clickable((By.ID, "rocky-chat-input")),
            message="Expected the chat composer to be available.",
        )
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url === '/api/chat' && init.method === 'POST') {
                    return new Promise((_resolve, reject) => {
                        const rejectAbort = () => reject(new DOMException('Aborted', 'AbortError'));
                        if (init.signal?.aborted) rejectAbort();
                        else init.signal?.addEventListener('abort', rejectAbort, { once: true });
                    });
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )

        textarea.send_keys(prompt)
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Send message']")
        stop_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-label='Stop waiting for response']")
            ),
            message="Expected Send to become a Stop control while generating.",
        )
        stop_button.click()

        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".chat-error-notice"), "Stopped waiting"
            ),
            message="Expected stopping to produce specific, non-error feedback.",
        )
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='Send message']")),
            message="Expected the composer to leave its generating state.",
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".chat-user-bubble")),
            0,
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".chat-message-assistant")),
            0,
        )
        self.assertEqual(
            len(
                self.driver.find_elements(
                    By.XPATH, "//button[normalize-space()='Edit and try again']"
                )
            ),
            0,
        )
        self.capture_evidence("chat-response-stopped")

    def test_analytics_filters_restore_and_follow_browser_history(self):
        self._login_as_admin()

        filtered_url = (
            f"{BASE_URL}/?frame=analytics&range=7d&course=CS-44001"
            "&operation=responses.create&outcome=failed"
        )
        self.driver.get(filtered_url)
        self._assert_title("Analytics")
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".analytics-filter-panel input")),
            message="Expected the analytics filter controls to render.",
        )
        course_input = self.driver.find_elements(
            By.CSS_SELECTOR, ".analytics-filter-panel input"
        )[1]
        self.assertEqual(course_input.get_attribute("value"), "CS-44001")
        self.assertEqual(
            Select(
                self.driver.find_elements(By.CSS_SELECTOR, ".analytics-filter-panel select")[0]
            ).first_selected_option.get_attribute("value"),
            "responses.create",
        )
        self.assertEqual(
            Select(
                self.driver.find_elements(By.CSS_SELECTOR, ".analytics-filter-panel select")[1]
            ).first_selected_option.get_attribute("value"),
            "failed",
        )
        self.driver.refresh()
        self._assert_title("Analytics")
        self.assertIn("course=CS-44001", self.driver.current_url)
        self.assertIn("range=7d", self.driver.current_url)

        outcome = Select(
            self.driver.find_elements(By.CSS_SELECTOR, ".analytics-filter-panel select")[1]
        )
        outcome.select_by_value("completed")
        self._click_element(
            By.XPATH,
            "//details[contains(@class,'analytics-filter-panel')]//button[normalize-space()='Apply filters']",
        )
        self.wait.until(
            lambda driver: "outcome=completed" in driver.current_url,
            message="Expected applying a filter to create a shareable URL state.",
        )
        self.driver.back()
        self.wait.until(
            lambda driver: "outcome=failed" in driver.current_url,
            message="Expected Back to restore the previous analytics state.",
        )
        self.assertEqual(
            Select(
                self.driver.find_elements(By.CSS_SELECTOR, ".analytics-filter-panel select")[1]
            ).first_selected_option.get_attribute("value"),
            "failed",
        )
        self.assertTrue(
            self.driver.find_element(By.XPATH, "//button[normalize-space()='Export JSON']").is_displayed()
        )
        self.assertTrue(
            self.driver.find_element(By.XPATH, "//button[normalize-space()='Export CSV']").is_displayed()
        )
        self.capture_evidence("analytics-shareable-filters")

    def test_course_key_warning_and_admin_panels(self):
        self._login_as_admin()

        course_card = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.course-card")),
            message="Expected dashboard courses to use keyboard-accessible buttons.",
        )
        self.assertEqual(course_card.tag_name.lower(), "button")
        course_card.click()
        self._assert_title("Courses")

        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")
        regenerate_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[normalize-space()='Regenerate Key']")
            ),
            message="Expected an existing group key to offer regeneration.",
        )
        regenerate_button.click()
        warning = self.wait.until(EC.alert_is_present())
        self.assertIn("immediately invalidate", warning.text.lower())
        warning.dismiss()

        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button[normalize-space()='Admin Panel']",
        )
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".admin-panel")),
            message="Expected the Admin Dashboard shell to render.",
        )
        for section_title in (
            "Recent Audit Logs",
            "System Status",
            "Top Courses — Last 30 Days",
        ):
            self.wait.until(
                EC.visibility_of_element_located(
                    (By.XPATH, f"//h2[normalize-space()='{section_title}']")
                ),
                message=f"Expected independently loadable admin section: {section_title}",
            )

        self.wait.until(
            lambda driver: all(
                "Checking" not in row.text
                for row in driver.find_elements(By.CSS_SELECTOR, ".status-row")
            ),
            message="Expected service health checks to settle independently.",
        )

        self.capture_evidence("admin-dashboard-reliability")

        self._click_element(
            By.XPATH,
            "//nav[contains(@class,'sidebar')]//button[normalize-space()='Chat']",
        )
        self.wait.until(
            lambda driver: driver.title == "Chat | Rocky",
            message="Expected Chat to replace the prior document title.",
        )
        self.capture_evidence("chat-full-workspace")

        self.driver.set_window_size(390, 844)
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "button.hamburger")),
            message="Expected mobile navigation control.",
        )
        has_horizontal_overflow = self.driver.execute_script(
            "return document.documentElement.scrollWidth > window.innerWidth;"
        )
        self.assertFalse(has_horizontal_overflow)
        landmarks = self.driver.execute_script(
            """
            const sidebar = document.querySelector('nav.sidebar');
            return {
              mainCount: document.querySelectorAll('main').length,
              sidebarInert: Boolean(sidebar?.inert),
              sidebarAriaHidden: sidebar?.getAttribute('aria-hidden')
            };
            """
        )
        self.assertEqual(landmarks["mainCount"], 1)
        self.assertTrue(landmarks["sidebarInert"])
        self.assertEqual(landmarks["sidebarAriaHidden"], "true")

        self._click_element(By.CSS_SELECTOR, "button.hamburger")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return !document.querySelector('nav.sidebar')?.inert;"
            ),
            message="Expected opening mobile navigation to restore keyboard access.",
        )
        self.capture_evidence("chat-mobile-workspace")


if __name__ == "__main__":
    import unittest

    unittest.main()
