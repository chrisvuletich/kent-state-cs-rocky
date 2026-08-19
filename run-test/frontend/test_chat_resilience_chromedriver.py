from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class ChatResilienceE2ETests(FrontendBrowserTestCase):
    def _login_as_admin(self) -> None:
        self.driver.get(f"{BASE_URL}/logout")
        self.wait.until(EC.url_contains("/login"))
        self.driver.get(f"{BASE_URL}/login/preview")
        self._click_element(
            By.XPATH,
            "//article[contains(@class,'preview-user-card')]"
            "[.//span[contains(@class,'preview-role') and normalize-space()='admin']]//button",
        )
        self._wait_for_post_login_navigation()
        # The dashboard may probe optional chat services that are intentionally
        # absent from this isolated harness. Wait for that probe to settle before
        # starting each assertion with fresh logs so its expected 502 cannot race
        # a later console check.
        self.wait.until(
            lambda driver: driver.execute_script(
                """
                return !Array.from(document.querySelectorAll('.recent-chats-note')).some(
                    (element) => element.getClientRects().length > 0
                        && element.textContent.trim().startsWith('Loading recent chats')
                );
                """
            )
        )
        self._read_browser_console()

    def test_unavailable_chat_preserves_editable_draft_until_recovery(self):
        self._login_as_admin()
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.__rockyHealthChecks = 0;
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url.startsWith('/api/server-health')) {
                    window.__rockyHealthChecks += 1;
                    const healthy = window.__rockyHealthChecks > 1;
                    return Promise.resolve(Response.json({
                        ok: healthy,
                        services: ['granite', 'chat-api', 'ollama'].map((name) => ({
                            name,
                            ok: healthy,
                            latencyMs: 1
                        }))
                    }, { status: healthy ? 200 : 503 }));
                }
                if (url === '/api/chat/conversations' && init.method === 'POST') {
                    return Promise.resolve(Response.json({ conversations: [] }));
                }
                if (url === '/api/chat/capabilities') {
                    return Promise.resolve(Response.json({ imageInput: { enabled: false } }));
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )

        self._click_sidebar_destination("Chat")
        notice = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".chat-availability-notice")),
            message="Expected an explanation when Rocky is unavailable.",
        )
        self.assertIn("temporarily unavailable", notice.text)
        self.assertIn("draft stays here", notice.text)

        textarea = self.driver.find_element(By.ID, "rocky-chat-input")
        textarea.send_keys("Draft that must survive an outage")
        send_button = self.driver.find_element(
            By.CSS_SELECTOR, ".chat-composer-footer > button"
        )
        self.assertFalse(send_button.is_enabled())
        self.assertIn("temporarily unavailable", send_button.get_attribute("aria-label"))

        textarea.send_keys(" and remain editable")
        expected_draft = "Draft that must survive an outage and remain editable"
        self.assertEqual(textarea.get_attribute("value"), expected_draft)

        logging_notice = self.driver.find_element(By.ID, "rocky-chat-logging-notice")
        self.assertTrue(logging_notice.is_displayed())
        self.assertIn("no expectation of privacy", logging_notice.text)
        self.assertGreaterEqual(
            float(
                self.driver.execute_script(
                    "return Number.parseFloat(getComputedStyle(arguments[0]).fontSize);",
                    logging_notice,
                )
            ),
            12.0,
        )
        self.assertIn(
            "rocky-chat-logging-notice", textarea.get_attribute("aria-describedby")
        )

        self._click_element(By.XPATH, "//button[normalize-space()='Check again']")
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".chat-availability-notice")),
            message="Expected the outage notice to clear after a healthy recheck.",
        )
        recovered_send_button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Send message']")),
            message="Expected sending to be restored after service recovery.",
        )
        self.assertTrue(recovered_send_button.is_enabled())
        self.assertEqual(textarea.get_attribute("value"), expected_draft)
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()

    def test_image_capabilities_retry_after_a_temporary_discovery_failure(self):
        self._login_as_admin()
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.__rockyCapabilityChecks = 0;
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url.startsWith('/api/server-health')) {
                    return Promise.resolve(Response.json({
                        ok: true,
                        services: ['granite', 'chat-api', 'ollama'].map((name) => ({
                            name,
                            ok: true,
                            latencyMs: 1
                        }))
                    }));
                }
                if (url === '/api/chat/conversations' && init.method === 'POST') {
                    return Promise.resolve(Response.json({ conversations: [] }));
                }
                if (url === '/api/chat/capabilities') {
                    window.__rockyCapabilityChecks += 1;
                    if (window.__rockyCapabilityChecks === 1) {
                        return Promise.resolve(Response.json({
                            error: { message: 'Capability discovery is temporarily unavailable.' }
                        }, { status: 503 }));
                    }
                    return Promise.resolve(Response.json({
                        imageInput: {
                            enabled: true,
                            limits: {
                                maxImages: 4,
                                maxImageBytes: 4194304,
                                maxTotalBytes: 6291456,
                                maxPixels: 20000000,
                                maxTotalPixels: 40000000
                            }
                        }
                    }));
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )

        self._click_sidebar_destination("Chat")
        self.wait.until(
            lambda driver: driver.execute_script(
                "return window.__rockyCapabilityChecks === 1;"
            ),
            message="Expected the first capability request to fail closed.",
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Attach images']")),
            0,
        )

        self.driver.execute_script(
            "document.dispatchEvent(new Event('visibilitychange'));"
        )
        self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Attach images']")),
            message="Expected capability discovery to retry after the healthy visibility check.",
        )
        self.assertEqual(
            self.driver.execute_script("return window.__rockyCapabilityChecks;"),
            2,
        )
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()

    def test_history_refresh_failure_keeps_cached_results_and_retries(self):
        self._login_as_admin()
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.__rockyConversationLoads = 0;
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url === '/api/chat/conversations' && init.method === 'POST') {
                    window.__rockyConversationLoads += 1;
                    if (window.__rockyConversationLoads === 2) {
                        return Promise.resolve(Response.json({
                            error: { message: 'Conversation history is temporarily unavailable.' }
                        }, { status: 503 }));
                    }
                    const recovered = window.__rockyConversationLoads > 2;
                    return Promise.resolve(Response.json({ conversations: [{
                        conversation_id: 'cached-conversation',
                        title: recovered ? 'Recovered arrays lesson' : 'Cached arrays lesson',
                        updated_at: '2026-08-18T12:00:00Z'
                    }] }));
                }
                if (url === '/api/chat' && init.method === 'POST') {
                    return Promise.resolve(Response.json({
                        output_text: 'Arrays store ordered values.',
                        conversation_id: 'cached-conversation',
                        message_stored: true
                    }, {
                        status: 200,
                        headers: {
                            'X-Rocky-Conversation-Id': 'cached-conversation',
                            'X-Rocky-Message-Stored': 'true'
                        }
                    }));
                }
                if (url === '/api/chat/capabilities') {
                    return Promise.resolve(Response.json({ imageInput: { enabled: false } }));
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )

        self._click_sidebar_destination("Chat")
        cached_item = self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//button[.//span[normalize-space()='Cached arrays lesson']]")
            ),
            message="Expected the first history request to populate cached results.",
        )
        self.assertTrue(cached_item.is_displayed())

        textarea = self.wait.until(
            EC.element_to_be_clickable((By.ID, "rocky-chat-input"))
        )
        textarea.send_keys("What is an array?")
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Send message']")

        error = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".chat-history-error")),
            message="Expected a recoverable history refresh error.",
        )
        self.assertIn("temporarily unavailable", error.text)
        self.assertTrue(
            self.driver.find_element(
                By.XPATH, "//button[.//span[normalize-space()='Cached arrays lesson']]"
            ).is_displayed(),
            msg="Cached history should remain visible during a refresh failure.",
        )

        retry_button = error.find_element(By.XPATH, ".//button[normalize-space()='Retry']")
        retry_button.click()
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".chat-history-error")),
            message="Expected Retry to clear the history error after recovery.",
        )
        self.wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//button[.//span[normalize-space()='Recovered arrays lesson']]")
            ),
            message="Expected Retry to refresh the cached conversation list.",
        )
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()
