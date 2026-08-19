from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class ThemeAndInactiveE2ETests(FrontendBrowserTestCase):
    def _assert_element_contrast(self, selector: str, minimum: float = 4.5) -> None:
        element = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector)),
            message=f"Expected visible contrast target: {selector}",
        )
        ratio = self.driver.execute_script(
            """
            const element = arguments[0];
            const rgb = (value) => value.match(/[0-9.]+/g).slice(0, 3).map(Number);
            const luminance = (value) => {
                const channels = rgb(value).map((channel) => {
                    const normalized = channel / 255;
                    return normalized <= 0.04045
                        ? normalized / 12.92
                        : Math.pow((normalized + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
            };
            let backgroundElement = element;
            let background = getComputedStyle(backgroundElement).backgroundColor;
            while (
                backgroundElement.parentElement
                && (background === 'rgba(0, 0, 0, 0)' || background === 'transparent')
            ) {
                backgroundElement = backgroundElement.parentElement;
                background = getComputedStyle(backgroundElement).backgroundColor;
            }
            const foregroundLuminance = luminance(getComputedStyle(element).color);
            const backgroundLuminance = luminance(background);
            return (Math.max(foregroundLuminance, backgroundLuminance) + 0.05)
                / (Math.min(foregroundLuminance, backgroundLuminance) + 0.05);
            """,
            element,
        )
        self.assertGreaterEqual(
            ratio,
            minimum,
            msg=f"Expected {selector} contrast >= {minimum}, got {ratio:.2f}.",
        )

    def test_inactive_account_offers_truthful_sign_out_path(self):
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')]"
            "[.//p[normalize-space()='student.alt3@kent.edu']]//button",
        )
        self._wait_for_post_login_navigation()
        self._click_sidebar_destination("Account")
        self._assert_title("Account Profile")
        theme_switch = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']")
            )
        )
        if theme_switch.get_attribute("aria-checked") != "true":
            theme_switch.click()
            self.wait.until(
                lambda driver: driver.find_element(By.TAG_NAME, "html").get_attribute(
                    "data-theme"
                )
                == "dark"
            )

        self._login_as_preview_role("admin")
        self._read_browser_console()
        deactivation = self.driver.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            (async () => {
                const usersResponse = await fetch('/api/backend/users');
                const users = await usersResponse.json();
                const target = users.find((user) => user.email === 'student.alt3@kent.edu');
                if (!target) {
                    done({ ok: false, message: 'Inactive-account test user was not found.' });
                    return;
                }
                const response = await fetch(`/api/backend/users/${encodeURIComponent(target.id)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: false })
                });
                done({ ok: response.ok, status: response.status });
            })().catch((error) => done({ ok: false, message: String(error) }));
            """
        )
        self.assertTrue(deactivation.get("ok"), msg=str(deactivation))

        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')]"
            "[.//p[normalize-space()='student.alt3@kent.edu']]//button",
        )

        self.wait.until(EC.url_contains("/deactivated"))
        self.wait.until(EC.title_is("Account inactive | Rocky"))
        self.assertEqual(
            self.driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme"),
            "dark",
        )
        heading = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".deactivated-card h1"))
        )
        self.assertEqual(heading.text, "Your account has been deactivated")
        self.assertIn(
            "You are signed in",
            self.driver.find_element(By.CSS_SELECTOR, ".deactivated-message").text,
        )
        action = self.driver.find_element(By.CSS_SELECTOR, ".deactivated-action")
        self.assertEqual(action.text, "Sign out and return to sign in")
        self.assertTrue(action.get_attribute("href").endswith("/logout"))
        action.click()
        self.wait.until(EC.url_contains("/login"))
        self.wait.until(EC.title_is("Sign in | Rocky"))

        self.driver.get(f"{BASE_URL}/deactivated")
        self.wait.until(EC.url_contains("/login"))
        self.assertNotIn("/deactivated", self.driver.current_url)
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()

    def test_light_and_dark_preferences_persist_with_accessible_contrast(self):
        self._login_as_preview_role("admin")
        self._read_browser_console()
        self._click_sidebar_destination("Account")
        self._assert_title("Account Profile")

        root = self.driver.find_element(By.TAG_NAME, "html")
        theme_switch = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"))
        )
        self.assertEqual(root.get_attribute("data-theme"), "light")
        self.assertEqual(theme_switch.get_attribute("aria-checked"), "false")

        theme_switch.click()
        self.wait.until(
            lambda driver: driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
            == "dark"
        )
        self.wait.until(
            lambda driver: driver.find_element(
                By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"
            ).is_enabled()
        )

        self.driver.refresh()
        self._assert_title("Account Profile")
        self.assertEqual(
            self.driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme"),
            "dark",
        )
        theme_switch = self.driver.find_element(
            By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"
        )
        self.assertEqual(theme_switch.get_attribute("aria-checked"), "true")

        contrast = self.driver.execute_script(
            """
            const resolveColor = (property) => {
                const probe = document.createElement('span');
                probe.style.color = `var(${property})`;
                document.body.appendChild(probe);
                const value = getComputedStyle(probe).color;
                probe.remove();
                return value;
            };
            const rgb = (value) => {
                const match = value.match(/[0-9.]+/g).map(Number);
                return match.slice(0, 3).map((channel) => channel / 255);
            };
            const luminance = (value) => {
                const channels = rgb(value).map((channel) =>
                    channel <= 0.04045
                        ? channel / 12.92
                        : Math.pow((channel + 0.055) / 1.055, 2.4)
                );
                return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
            };
            const ratio = (foreground, background) => {
                const first = luminance(resolveColor(foreground));
                const second = luminance(resolveColor(background));
                return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
            };
            return {
                primary: ratio('--color-text-primary', '--color-bg-primary'),
                secondary: ratio('--color-text-secondary', '--color-bg-primary'),
                accent: ratio('--color-text-accent', '--color-bg-primary'),
                sidebar: ratio('--color-text-inverse', '--color-bg-sidebar')
            };
            """
        )
        for name, ratio in contrast.items():
            self.assertGreaterEqual(
                ratio,
                4.5,
                msg=f"Expected dark-theme {name} text contrast >= 4.5, got {ratio:.2f}.",
            )

        contrast_targets = (
            ("admin", "Admin Dashboard", (".card-header h2", ".status-row span:first-child")),
            ("analytics", "Analytics", (".analytics-refresh",)),
            ("users", "User Management", ("#kent-accounts-tab",)),
            ("help", "Help Center", (".help-resource-action",)),
        )
        for frame, title, selectors in contrast_targets:
            with self.subTest(frame=frame):
                self.driver.get(f"{BASE_URL}/?frame={frame}")
                if frame == "admin":
                    self.wait.until(EC.title_is("Admin Dashboard | Rocky"))
                    heading = self.wait.until(
                        EC.visibility_of_element_located(
                            (By.CSS_SELECTOR, ".admin-panel .header h1")
                        )
                    )
                    self.assertEqual(heading.text, title)
                    self.wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "[data-rocky-app-ready='true']")
                        )
                    )
                else:
                    self._assert_title(title)
                for selector in selectors:
                    self._assert_element_contrast(selector)

        self.driver.get(f"{BASE_URL}/?frame=account")
        self._assert_title("Account Profile")
        theme_switch = self.driver.find_element(
            By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"
        )
        theme_switch.click()
        self.wait.until(
            lambda driver: driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme")
            == "light"
        )
        self.wait.until(
            lambda driver: driver.find_element(
                By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"
            ).is_enabled()
        )
        self.driver.refresh()
        self._assert_title("Account Profile")
        self.assertEqual(
            self.driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme"),
            "light",
        )
        self.assertEqual(
            self.driver.find_element(
                By.CSS_SELECTOR, "button[role='switch'][aria-label='Dark mode']"
            ).get_attribute("aria-checked"),
            "false",
        )
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()


if __name__ == "__main__":
    import unittest

    unittest.main()
