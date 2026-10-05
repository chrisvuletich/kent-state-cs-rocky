from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class GroupSelfJoinE2ETests(FrontendBrowserTestCase):
    def _open_course_as(self, email, tab):
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(By.XPATH, f"//article[contains(@class,'preview-user-card')][.//p[normalize-space()='{email}']]//button")
        self._wait_for_post_login_navigation()
        self.driver.get(f"{BASE_URL}/?frame=courses&course=1")
        self._assert_title("Courses")
        self._click_element(By.XPATH, f"//button[@role='tab' and normalize-space()='{tab}']")

    def _request(self, path, method="GET", body=None):
        return self.driver.execute_async_script(
            "const [path, method, body, done] = arguments;"
            "fetch('/api/backend' + path, {method, headers: {'Content-Type': 'application/json'},"
            "body: body === null ? undefined : JSON.stringify(body)})"
            ".then(async r => done({status: r.status, data: await r.json()})).catch(e => done({error: String(e)}));",
            path, method, body,
        )

    def _settings(self, name):
        selector = f"button[aria-label='Group settings for {name}']"
        self._click_element(By.CSS_SELECTOR, selector)
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".join-settings-dialog")))
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == "group-name")
        return selector

    def _save_settings(self):
        self._click_element(By.XPATH, "//div[@role='dialog']//button[normalize-space()='Save settings']")
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".join-settings-dialog")))

    def _row(self, name):
        return self.driver.find_element(By.XPATH, f"//ul[contains(@class,'joinable-groups')]/li[.//strong[normalize-space()='{name}']]")

    def test_instructor_opt_in_student_join_capacity_and_disable(self):
        self._set_viewport("desktop")
        self._open_course_as("instructor.local@kent.edu", "Groups")
        created = self._request("/courses/1/groups", "POST", {"name": "Class Project"})
        self.assertEqual(created["status"], 200, created)
        group = created["data"]["groups"][-1]
        group_path = f"/courses/1/groups/{group['id']}"
        self.assertFalse(group["self_join_enabled"])
        self.driver.refresh()
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[@role='tab' and normalize-space()='Groups']")
        opener = self._settings("Class Project")
        self.assertFalse(self.driver.find_element(By.ID, "group-self-join").is_selected())
        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".join-settings-dialog")))
        self.wait.until(lambda driver: driver.execute_script("return document.activeElement === document.querySelector(arguments[0]);", opener))
        self._settings("Class Project")
        self.driver.find_element(By.ID, "group-self-join").click()
        self.driver.find_element(By.ID, "group-size-limit").send_keys("1")
        self.driver.save_screenshot(str(self._process_log_dir / "group-joining-settings.png"))
        self._save_settings()
        self.wait.until(lambda driver: driver.execute_script("return document.activeElement === document.querySelector(arguments[0]);", opener))

        self._open_course_as("student.local@kent.edu", "Groups")
        self.assertEqual(len(self.driver.find_elements(By.XPATH, "//button[@role='tab' and normalize-space()='Groups']")), 1)
        self.wait.until(lambda _: "Open to join" in self._row("Class Project").text)
        self.assertIn("You are a member", self._row("Team Alpha").text)
        self.driver.save_screenshot(str(self._process_log_dir / "student-groups-desktop.png"))
        self.driver.execute_script(r"""
            const original = window.fetch.bind(window);
            window.selfJoinRequests = [];
            window.fetch = async (url, init) => {
                if (String(url).endsWith('/join') && init?.method === 'POST') {
                    window.selfJoinRequests.push(JSON.parse(init.body));
                    if (window.selfJoinRequests.length === 1) return new Response(JSON.stringify({error: 'The group changed while saving.'}), {status:409});
                    await new Promise(resolve => window.releaseJoin = resolve);
                }
                return original(url, init);
            };
        """)
        self._row("Class Project").find_element(By.TAG_NAME, "button").click()
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".student-groups [role='alert']"), "The group changed"))
        self._click_element(By.XPATH, "//button[normalize-space()='Refresh groups']")
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".student-groups [role='alert']")))
        join_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Join Class Project']")))
        join_button.click()
        self.wait.until(lambda driver: driver.execute_script("return typeof window.releaseJoin === 'function'"))
        self.assertFalse(join_button.is_enabled())
        self.driver.execute_script("arguments[0].click();", join_button)
        self.driver.execute_script("window.releaseJoin();")
        self.wait.until(lambda _: "You are a member" in self._row("Class Project").text)
        self.assertEqual(self.driver.execute_script("return window.selfJoinRequests"), [{}, {}])
        self.assertIn("1 / 1 students", self._row("Class Project").text)
        saved = self._request("/courses/1")["data"]
        self.assertEqual(next(g for g in saved["groups"] if g["id"] == group["id"])["memberIds"], ["student.local@kent.edu"])
        self._row("Class Project").find_element(By.TAG_NAME, "button").click()
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, "#course-tab-panel"), "Group keys are managed by your course instructor"))
        self.assertTrue(self.driver.find_element(By.XPATH, "//button[@role='tab' and normalize-space()='Home']"))
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations", "[courses api] request failed"))

        self._set_viewport("phone")
        self._open_course_as("student.alt1@kent.edu", "Groups")
        self.wait.until(lambda _: "Full" in self._row("Class Project").text)
        self.assertFalse(self._row("Class Project").find_element(By.TAG_NAME, "button").is_enabled())
        self.assertFalse(self.driver.execute_script("return document.documentElement.scrollWidth > innerWidth;"))
        self.driver.save_screenshot(str(self._process_log_dir / "student-groups-phone.png"))
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))

        self._open_course_as("instructor.local@kent.edu", "Groups")
        self._settings("Class Project")
        self.driver.find_element(By.ID, "group-self-join").click()
        # Use a real editing keystroke: WebDriver.clear() alone does not emit
        # the input event used by Svelte's numeric binding in every browser.
        limit_input = self.driver.find_element(By.ID, "group-size-limit")
        limit_input.click()
        limit_input.send_keys(Keys.ARROW_RIGHT, Keys.BACKSPACE)
        self.assertEqual(limit_input.get_attribute("value"), "")
        self._save_settings()
        disabled = self._request("/courses/1")["data"]
        disabled_group = next(g for g in disabled["groups"] if g["id"] == group["id"])
        self.assertFalse(disabled_group["self_join_enabled"])
        self.assertIsNone(disabled_group["max_members"])
        self.assertEqual(disabled_group["memberIds"], ["student.local@kent.edu"])
        self._open_course_as("student.alt1@kent.edu", "Groups")
        self.wait.until(lambda _: "Instructor-assigned" in self._row("Class Project").text)
        self.assertFalse(self._row("Class Project").find_element(By.TAG_NAME, "button").is_enabled())

    def test_settings_errors_keep_inputs_and_course_close_disables_joining(self):
        self._set_viewport("phone")
        self._open_course_as("admin.local@kent.edu", "Groups")
        self._settings("Team Alpha")
        self.driver.find_element(By.ID, "group-self-join").click()
        self.driver.find_element(By.ID, "group-size-limit").send_keys("1")
        self._click_element(By.XPATH, "//div[@role='dialog']//button[normalize-space()='Save settings']")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".join-settings-dialog [role='alert']"), "smaller than its current membership"))
        self.assertTrue(self.driver.find_element(By.ID, "group-self-join").is_selected())
        self.assertEqual(self.driver.find_element(By.ID, "group-size-limit").get_attribute("value"), "1")
        self.driver.find_element(By.ID, "group-size-limit").clear()
        self.driver.find_element(By.ID, "group-size-limit").send_keys("5")
        self._save_settings()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations", "/api/backend/courses/1/groups/group-se3010-a", "[courses api] request failed"))
        closed = self._request("/courses/1/status", "PATCH", {"is_active": False})
        self.assertEqual(closed["status"], 200, closed)
        self._open_course_as("student.local@kent.edu", "Groups")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".student-groups"), "This course is closed"))
        self.assertTrue(self._row("Team Alpha").find_element(By.TAG_NAME, "button").is_enabled())
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))

    def _confirm_action(self, label):
        self.wait.until(EC.visibility_of_element_located((By.ID, "group-action-title")))
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == "group-action-cancel")
        self._click_element(By.XPATH, f"//div[@role='dialog']//button[normalize-space()='{label}']")
        self.wait.until(EC.invisibility_of_element_located((By.ID, "group-action-title")))

    def test_unified_management_rename_pause_resume_remove_and_delete(self):
        self._set_viewport("desktop")
        self._open_course_as("admin.local@kent.edu", "Groups")
        self.assertEqual(self._request("/courses/1/status", "PATCH", {"is_active": True})["status"], 200)
        self._open_course_as("instructor.local@kent.edu", "Groups")
        self.assertEqual(len(self.driver.find_elements(By.XPATH, "//button[@role='tab' and normalize-space()='Groups']")), 1)
        self.assertFalse(self.driver.find_elements(By.XPATH, "//button[@role='tab' and normalize-space()='Edit Groups']"))
        self.assertIn("frame=courses", self.driver.current_url)
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, ".manage-groups input[type='search']"))
        groups = self._request("/courses/1")["data"]["groups"]
        self.assertEqual(len(self.driver.find_elements(By.CSS_SELECTOR, ".group-list > li")), len(groups))
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "button[aria-label='View Team Alpha']")))
        self.driver.save_screenshot(str(self._process_log_dir / "unified-groups-desktop.png"))
        self._settings("Team Alpha")
        name = self.driver.find_element(By.ID, "group-name")
        name.clear()
        name.send_keys("Project Alpha")
        if not self.driver.find_element(By.ID, "group-self-join").is_selected():
            self.driver.find_element(By.ID, "group-self-join").click()
        self._save_settings()
        self._click_element(By.CSS_SELECTOR, "button[aria-label='View Project Alpha']")
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == "group-detail-title")
        self.assertIn("student.local@kent.edu", self.driver.find_element(By.CSS_SELECTOR, ".group-members").text)
        self._click_element(By.XPATH, "//button[normalize-space()='Close joining']")
        self.assertIn("memberships and shared keys are unchanged", self.driver.find_element(By.ID, "group-action-description").text)
        self._confirm_action("Close joining")
        self._click_element(By.XPATH, "//button[normalize-space()='Pause group']")
        self._confirm_action("Pause group")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".manage-groups"), "Paused — shared keys disabled"))
        generate_selector = "//button[normalize-space()='Generate Key' or normalize-space()='Regenerate Key']"
        generate = self.wait.until(EC.visibility_of_element_located((By.XPATH, generate_selector)))
        self.assertFalse(generate.is_enabled())
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, "button[aria-label='Add students to Project Alpha']").is_enabled())
        self._set_viewport("phone")
        self.wait.until(lambda driver: driver.execute_script("return document.querySelector('nav.sidebar').getBoundingClientRect().right <= 0;"))
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".feedback-success")))
        self.assertFalse(self.driver.execute_script("return document.documentElement.scrollWidth > innerWidth;"))
        self.driver.execute_script("for (let node = document.querySelector('#group-detail-title').parentElement; node; node = node.parentElement) node.scrollTop = 0;")
        self.driver.save_screenshot(str(self._process_log_dir / "group-details-phone.png"))
        self._click_element(By.XPATH, "//button[normalize-space()='Resume group']")
        self._confirm_action("Resume group")
        self.wait.until(EC.element_to_be_clickable((By.XPATH, generate_selector)))
        self._settings("Project Alpha")
        key_limit = self.driver.find_element(By.ID, "group-key-limit")
        key_limit.clear()
        key_limit.send_keys("0")
        self._save_settings()
        self.assertFalse(self.wait.until(EC.visibility_of_element_located((By.XPATH, generate_selector))).is_enabled())
        self._settings("Project Alpha")
        key_limit = self.driver.find_element(By.ID, "group-key-limit")
        key_limit.clear()
        key_limit.send_keys("1")
        self._save_settings()
        self.wait.until(EC.element_to_be_clickable((By.XPATH, generate_selector)))
        self._click_element(By.CSS_SELECTOR, ".group-members li:first-child button")
        self.assertIn("shared keys will be revoked", self.driver.find_element(By.ID, "group-action-description").text)
        self._confirm_action("Remove student")
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, ".group-members li")) == 1)
        self._click_element(By.XPATH, "//button[normalize-space()='Delete group']")
        self.assertIn("1 membership", self.driver.find_element(By.ID, "group-action-description").text)
        self.assertIn("Students stay enrolled", self.driver.find_element(By.ID, "group-action-description").text)
        # Cancel is the safe initial focus; Escape keeps the group unchanged.
        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        self.wait.until(EC.invisibility_of_element_located((By.ID, "group-action-title")))
        self._click_element(By.XPATH, "//button[normalize-space()='Delete group']")
        self._confirm_action("Delete group")
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == "group-list-summary")
        self.assertFalse(self.driver.execute_script("return document.documentElement.scrollWidth > innerWidth;"))
        self.driver.save_screenshot(str(self._process_log_dir / "unified-groups-phone.png"))
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='View Project Alpha']"))
        saved = self._request("/courses/1")["data"]
        self.assertTrue(any(m["email"] == "student.local@kent.edu" for m in saved["members"]))
        self.assertFalse(any(g["id"] == "group-se3010-a" for g in saved["groups"]))
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))

    def test_create_group_and_failed_settings_or_delete_keep_drafts(self):
        self._set_viewport("phone")
        self._open_course_as("admin.local@kent.edu", "Groups")
        self.driver.find_element(By.CSS_SELECTOR, "input[aria-label='New group name']").send_keys("Retry Team")
        self._click_element(By.XPATH, "//button[normalize-space()='Create Group']")
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "button[aria-label='View Retry Team']")))
        self._settings("Retry Team")
        name = self.driver.find_element(By.ID, "group-name")
        name.clear()
        name.send_keys("Retry Renamed")
        self.driver.execute_script(r"""
            const original = window.fetch.bind(window);
            window.groupSettingsRequests = 0;
            window.fetch = async (url, init) => {
                if (/\/groups\/[^/]+$/.test(String(url)) && init?.method === 'PATCH') {
                    window.groupSettingsRequests++;
                    if (window.groupSettingsRequests === 1) return new Response(JSON.stringify({error: 'The course changed while saving.'}), {status:409});
                }
                return original(url, init);
            };
        """)
        self._click_element(By.XPATH, "//div[@role='dialog']//button[normalize-space()='Save settings']")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".join-settings-dialog [role='alert']"), "The course changed"))
        self.assertEqual(name.get_attribute("value"), "Retry Renamed")
        self._save_settings()
        self._click_element(By.CSS_SELECTOR, "button[aria-label='View Retry Renamed']")
        self.driver.execute_script(r"""
            const original = window.fetch.bind(window);
            window.groupDeleteRequests = 0;
            window.fetch = async (url, init) => {
                if (/\/groups\/[^/]+$/.test(String(url)) && init?.method === 'DELETE') {
                    window.groupDeleteRequests++;
                    if (window.groupDeleteRequests === 1) return new Response(JSON.stringify({error: 'The course changed while saving.'}), {status:409});
                    await new Promise(resolve => window.releaseDelete = resolve);
                }
                return original(url, init);
            };
        """)
        self._click_element(By.XPATH, "//button[normalize-space()='Delete group']")
        self._click_element(By.XPATH, "//div[@role='dialog']//button[normalize-space()='Delete group']")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, "[role='dialog'] [role='alert']"), "The course changed"))
        self._click_element(By.XPATH, "//div[@role='dialog']//button[normalize-space()='Delete group']")
        self.wait.until(lambda driver: driver.execute_script("return typeof window.releaseDelete === 'function'"))
        self.assertFalse(self.driver.find_element(By.ID, "group-action-cancel").is_enabled())
        self.driver.execute_script("document.querySelector('[role=dialog] .popup-actions button:last-child').click();")
        self.driver.execute_script("window.releaseDelete();")
        self.wait.until(EC.invisibility_of_element_located((By.ID, "group-action-title")))
        self.assertEqual(self.driver.execute_script("return window.groupDeleteRequests"), 2)
        self.assertFalse(self.driver.execute_script("return document.documentElement.scrollWidth > innerWidth;"))
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations", "[courses api] request failed"))

    def test_student_paused_group_has_read_only_details_without_extra_tabs(self):
        self._set_viewport("phone")
        self._open_course_as("admin.local@kent.edu", "Groups")
        self.assertEqual(self._request("/courses/1/status", "PATCH", {"is_active": True})["status"], 200)
        created = self._request("/courses/1/groups", "POST", {"name": "Paused Project"})
        group_id = created["data"]["groups"][-1]["id"]
        path = f"/courses/1/groups/{group_id}"
        self.assertEqual(self._request(path + "/members", "POST", {"memberIds": ["student.local@kent.edu"]})["status"], 200)
        self.assertEqual(self._request(path, "PATCH", {"is_active": False, "self_join_enabled": True})["status"], 200)
        self._open_course_as("student.local@kent.edu", "Groups")
        self.assertIn("Paused", self._row("Paused Project").text)
        self.assertFalse(self.driver.find_elements(By.CSS_SELECTOR, "[role='tab'][id^='course-tab-group-']"))
        self._row("Paused Project").find_element(By.TAG_NAME, "button").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "student-group-detail-title"), "Paused Project"))
        self.assertIn("This group is paused", self.driver.find_element(By.ID, "course-tab-panel").text)
        self.assertFalse(self.driver.find_elements(By.XPATH, "//button[normalize-space()='Generate Key' or normalize-space()='Delete group' or normalize-space()='Group settings']"))
        self._click_element(By.XPATH, "//button[normalize-space()='Back to groups']")
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == f"student-view-group-{group_id}")
        self._open_course_as("student.alt1@kent.edu", "Groups")
        self.assertIn("Paused", self._row("Paused Project").text)
        self.assertFalse(self._row("Paused Project").find_element(By.TAG_NAME, "button").is_enabled())
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))


if __name__ == "__main__":
    import unittest
    unittest.main()
