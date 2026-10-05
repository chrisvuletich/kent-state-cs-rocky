from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class GroupStudentsE2ETests(FrontendBrowserTestCase):
    dialog = ".group-students-dialog"
    opener = "button[aria-label='Add students to Team Alpha']"

    def _open_groups_as(self, email):
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(By.XPATH, f"//article[contains(@class,'preview-user-card')][.//p[normalize-space()='{email}']]//button")
        self._wait_for_post_login_navigation()
        self.driver.get(f"{BASE_URL}/?frame=courses&course=1")
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")

    def _request(self, path, method="GET", body=None):
        return self.driver.execute_async_script(
            "const [path, method, body, done] = arguments;"
            "fetch('/api/backend' + path, {method, headers: {'Content-Type': 'application/json'},"
            "body: body === null ? undefined : JSON.stringify(body)})"
            ".then(async r => done({status: r.status, data: await r.json()})).catch(e => done({error: String(e)}));",
            path, method, body,
        )

    def _open_dialog(self):
        self._click_element(By.CSS_SELECTOR, self.opener)
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, self.dialog)))
        self.wait.until(lambda driver: driver.switch_to.active_element.get_attribute("id") == "group-students-search")

    def _search(self, text):
        field = self.driver.find_element(By.ID, "group-students-search")
        field.clear()
        field.send_keys(text)
        self.wait.until(lambda driver: driver.find_element(By.ID, "group-students-search").get_attribute("value") == text)

    def _button(self, text):
        return self.driver.find_element(By.XPATH, f"//div[@role='dialog']//button[normalize-space()='{text}']")

    def _selected(self, count):
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".selection-toolbar [role='status']"), f"{count} selected"))

    def test_bulk_selection_retry_and_saved_membership(self):
        self._set_viewport("desktop")
        self._open_groups_as("admin.local@kent.edu")
        added = self._request("/courses/1/members", "POST", {"members": [{"email": "bulk.one@kent.edu"}, {"email": "bulk.two@kent.edu"}]})
        self.assertEqual(added["status"], 200, added)
        self.driver.refresh()
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")
        self._open_dialog()
        self.assertNotIn("instructor.local@kent.edu", self.driver.find_element(By.CSS_SELECTOR, self.dialog).text)
        existing = self.driver.find_element(By.CSS_SELECTOR, ".student-row input[value='student.local@kent.edu']")
        self.assertTrue(existing.is_selected())
        self.assertFalse(existing.is_enabled())
        self.assertIn("Already in group", self.driver.find_element(By.CSS_SELECTOR, self.dialog).text)

        self._search("bulk.one")
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".student-row input[value='bulk.one@kent.edu']"))).click()
        self._selected(1)
        self._search("no-match-at-all")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".empty-students"), "No students match"))
        self.assertFalse(self._button("Select all matching").is_enabled())
        self._selected(1)
        self._search("bulk.two")
        self._button("Select all matching").click()
        self._selected(2)
        self._button("Clear selection").click()
        self._selected(0)
        self._button("Select all matching").click()
        self._selected(1)
        self._search("bulk.")
        self._button("Select all matching").click()
        self._selected(2)
        self.assertEqual(len(self.driver.find_elements(By.CSS_SELECTOR, ".student-row")), 2)
        self.driver.save_screenshot(str(self._process_log_dir / "group-students-desktop.png"))

        # Fail one request without changing the database. Keep selections for retry,
        # and gate the retry to check duplicate-click protection while it is pending.
        self.driver.execute_script("""
            const original = window.fetch.bind(window);
            window.groupAddRequests = [];
            window.fetch = async (url, init) => {
                if (String(url).endsWith('/groups/group-se3010-a/members') && init?.method === 'POST') {
                    window.groupAddRequests.push(JSON.parse(init.body));
                    if (window.groupAddRequests.length === 1) {
                        return new Response(JSON.stringify({error: 'The course changed. Review your selection and try again.'}), {status: 409});
                    }
                    await new Promise(resolve => window.releaseGroupAdd = resolve);
                }
                return original(url, init);
            };
        """)
        self._button("Add 2 students").click()
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".group-students-dialog [role='alert']"), "The course changed"))
        self._selected(2)
        self._button("Add 2 students").click()
        self.wait.until(lambda driver: driver.execute_script("return typeof window.releaseGroupAdd === 'function'"))
        self.assertFalse(self._button("Adding students…").is_enabled())
        self.assertFalse(self._button("Cancel").is_enabled())
        self.driver.execute_script("document.querySelector('.group-students-dialog .popup-actions button:last-child').click();")
        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, self.dialog).is_displayed())
        self.driver.execute_script("window.releaseGroupAdd();")
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.dialog)))
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".feedback-success"), "Added 2 students to Team Alpha"))
        self.wait.until(lambda driver: driver.execute_script("return document.activeElement === document.querySelector(arguments[0]);", self.opener))
        self.assertEqual(self.driver.execute_script("return window.groupAddRequests"), [
            {"memberIds": ["bulk.two@kent.edu", "bulk.one@kent.edu"]},
            {"memberIds": ["bulk.two@kent.edu", "bulk.one@kent.edu"]},
        ])
        saved = self._request("/courses/1")["data"]
        group = next(group for group in saved["groups"] if group["id"] == "group-se3010-a")
        self.assertEqual(group["memberIds"].count("bulk.one@kent.edu"), 1)
        self.assertEqual(group["memberIds"].count("bulk.two@kent.edu"), 1)
        self._click_element(By.CSS_SELECTOR, "button[aria-label='View Team Alpha']")
        self.assertIn("bulk.one@kent.edu", self.driver.find_element(By.CSS_SELECTOR, ".group-members").text)
        self.assertIn("bulk.two@kent.edu", self.driver.find_element(By.CSS_SELECTOR, ".group-members").text)
        self._open_dialog()
        self._search("bulk.")
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, ".student-row input:disabled")) == 2)
        self._selected(0)
        self.assertFalse(self._button("Add 0 students").is_enabled())
        self._button("Cancel").click()
        self._assert_no_framework_error_overlay()
        # The 409 is deliberately injected above; chat is not started by this harness.
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations", "[courses api] request failed"))

    def test_instructor_keyboard_mobile_and_empty_roster(self):
        self._set_viewport("phone")
        self._open_groups_as("instructor.local@kent.edu")
        self._open_dialog()
        self._search("instructor.alt@kent.edu")
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".student-row input[value='instructor.alt@kent.edu']"))).click()
        self._selected(1)
        self.assertTrue(self.driver.execute_script("return Boolean(document.querySelector('nav.sidebar')?.closest('[inert]'));"))
        last = self._button("Add 1 student")
        self.driver.execute_script("arguments[0].focus();", last)
        last.send_keys(Keys.TAB)
        self.assertEqual(self.driver.switch_to.active_element.get_attribute("id"), "group-students-search")
        self.driver.switch_to.active_element.send_keys(Keys.SHIFT, Keys.TAB)
        self.assertEqual(self.driver.switch_to.active_element.text, "Add 1 student")
        bounds = self.driver.execute_script("""
            const r = document.querySelector('.group-students-dialog').getBoundingClientRect();
            return {left:r.left, right:r.right, top:r.top, bottom:r.bottom, width:innerWidth, height:innerHeight};
        """)
        self.assertGreaterEqual(bounds["left"], 0)
        self.assertLessEqual(bounds["right"], bounds["width"])
        self.assertGreaterEqual(bounds["top"], 0)
        self.assertLessEqual(bounds["bottom"], bounds["height"])
        self.driver.save_screenshot(str(self._process_log_dir / "group-students-phone.png"))
        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.dialog)))
        self.wait.until(lambda driver: driver.execute_script("return document.activeElement === document.querySelector(arguments[0]);", self.opener))
        self._open_dialog()
        self._selected(0)
        self._search("instructor.alt@kent.edu")
        self._button("Select all matching").click()
        self._button("Add 1 student").click()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.dialog)))
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".feedback-success"), "Added 1 student"))
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))

        # Create an isolated empty course for the empty-list state.
        self._open_groups_as("admin.local@kent.edu")
        instructor_id = self._request("/courses/1")["data"]["instructor_id"]
        created = self._request("/courses", "POST", {"id": 909, "code": "CS 909", "name": "Empty group test", "instructor_id": instructor_id, "members": [], "groups": []})
        self.assertEqual(created["status"], 201, created)
        group_result = self._request("/courses/909/groups", "POST", {"name": "Empty Team"})
        self.assertEqual(group_result["status"], 200, group_result)
        self.driver.get(f"{BASE_URL}/?frame=courses&course=909")
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Add students to Empty Team']")
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".empty-students"), "No students are on this course roster yet"))
        self.assertFalse(self._button("Select all matching").is_enabled())
        self.assertFalse(self._button("Add 0 students").is_enabled())
        self._button("Cancel").click()

    def test_large_roster_on_short_viewport(self):
        self._set_viewport("phone_landscape")
        self._open_groups_as("admin.local@kent.edu")
        instructor_id = self._request("/courses/1")["data"]["instructor_id"]
        emails = [f"batch.student{index:03}@kent.edu" for index in range(125)]
        created = self._request("/courses", "POST", {
            "id": 910, "code": "CS 910", "name": "Large roster test",
            "instructor_id": instructor_id,
            "members": [{"email": email} for email in emails + ["unselected@kent.edu"]],
            "groups": [{"id": "large-team", "name": "Large Team", "memberIds": []}],
        })
        self.assertEqual(created["status"], 201, created)
        self.driver.get(f"{BASE_URL}/?frame=courses&course=910")
        self._assert_title("Courses")
        self._click_element(By.XPATH, "//button[normalize-space()='Groups']")
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Add students to Large Team']")
        self.wait.until(EC.visibility_of_element_located((By.ID, "group-students-search")))
        self._search("BATCH.")
        self._button("Select all matching").click()
        self._selected(125)
        self.assertTrue(self.driver.execute_script(
            "const list = document.querySelector('.student-list'); return list.scrollHeight > list.clientHeight;"
        ))
        self._search("batch.student124")
        self.wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, ".student-row")) == 1)
        self.assertTrue(self.driver.find_element(By.CSS_SELECTOR, ".student-row input").is_selected())
        self._selected(125)
        self._button("Add 125 students").click()
        self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, self.dialog)))
        self.wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, ".feedback-success"), "Added 125 students"))
        saved = self._request("/courses/910")["data"]
        self.assertEqual(saved["groups"][0]["memberIds"], emails)
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors(allowed_message_fragments=("/api/chat/conversations",))


if __name__ == "__main__":
    import unittest

    unittest.main()
