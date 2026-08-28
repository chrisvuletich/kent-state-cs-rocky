from __future__ import annotations

import base64
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from mongita import MongitaClientDisk
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

    def test_chat_stop_reconciles_persisted_history_without_offering_duplicate_retry(self):
        self._login_as_admin()
        self._click_sidebar_destination("Chat")

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
                    const encoder = new TextEncoder();
                    const frame = (event) =>
                        `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
                    const body = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode([
                                { type: 'response.created', sequence_number: 0 },
                                { type: 'response.in_progress', sequence_number: 1 },
                                { type: 'response.output_item.added', sequence_number: 2 },
                                { type: 'response.content_part.added', sequence_number: 3 },
                                {
                                    type: 'response.output_text.delta',
                                    sequence_number: 4,
                                    delta: 'Partial answer'
                                }
                            ].map(frame).join('')));
                            const stop = () => controller.error(new DOMException('Aborted', 'AbortError'));
                            if (init.signal?.aborted) stop();
                            else init.signal?.addEventListener('abort', stop, { once: true });
                        }
                    });
                    return Promise.resolve(new Response(body, {
                        status: 200,
                        headers: {
                            'Content-Type': 'text/event-stream; charset=utf-8',
                            'X-Rocky-Conversation-Id': 'conversation-stopped',
                            'X-Rocky-Message-Stored': 'true'
                        }
                    }));
                }
                if (url === '/api/chat/conversations' && init.method === 'POST') {
                    return Promise.resolve(Response.json({ conversations: [{
                        conversation_id: 'conversation-stopped',
                        title: 'Explain a stack'
                    }] }));
                }
                if (url === '/api/chat/conversations/conversation-stopped' && init.method === 'POST') {
                    return Promise.resolve(Response.json({ messages: [
                        {
                            message_id: 'stopped-user-message',
                            role: 'user',
                            content: 'Explain a stack in one sentence.',
                            status: 'failed'
                        },
                        {
                            message_id: 'stopped-assistant-message',
                            role: 'assistant',
                            content: 'Partial answer',
                            status: 'failed'
                        }
                    ] }));
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
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".chat-user-bubble")),
            message="Expected stopped durable history to reload.",
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".chat-user-bubble")),
            1,
        )
        self.assertEqual(
            len(self.driver.find_elements(By.CSS_SELECTOR, ".chat-message-assistant")),
            1,
        )
        self.assertIn(
            "Explain a stack in one sentence.",
            self.driver.find_element(By.CSS_SELECTOR, ".chat-user-bubble").text,
        )
        self.assertIn(
            "Partial answer",
            self.driver.find_element(By.CSS_SELECTOR, ".chat-message-assistant").text,
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

    def test_chat_renders_streamed_deltas_before_completion(self):
        self._login_as_admin()
        self._click_sidebar_destination("Chat")

        textarea = self.wait.until(
            EC.element_to_be_clickable((By.ID, "rocky-chat-input")),
            message="Expected the chat composer to be available.",
        )
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url !== '/api/chat' || init.method !== 'POST') {
                    return window.__rockyOriginalFetch(input, init);
                }
                const encoder = new TextEncoder();
                const frame = (event) =>
                    `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
                const prefix = [
                    { type: 'response.created', sequence_number: 0 },
                    { type: 'response.in_progress', sequence_number: 1 },
                    { type: 'response.output_item.added', sequence_number: 2 },
                    { type: 'response.content_part.added', sequence_number: 3 },
                    {
                        type: 'response.output_text.delta',
                        sequence_number: 4,
                        delta: 'Streaming now'
                    }
                ].map(frame).join('');
                const suffix = [
                    {
                        type: 'response.output_text.delta',
                        sequence_number: 5,
                        delta: ' works.'
                    },
                    {
                        type: 'response.output_text.done',
                        sequence_number: 6,
                        text: 'Streaming now works.'
                    },
                    { type: 'response.content_part.done', sequence_number: 7 },
                    { type: 'response.output_item.done', sequence_number: 8 },
                    {
                        type: 'response.completed',
                        sequence_number: 9,
                        response: {
                            id: 'resp_browser_stream',
                            status: 'completed',
                            output_text: 'Streaming now works.',
                            conversation_id: 'conversation-browser-stream',
                            message_stored: true
                        }
                    }
                ].map(frame).join('');
                const body = new ReadableStream({
                    start(controller) {
                        controller.enqueue(encoder.encode(prefix));
                        window.__rockyFinishSyntheticStream = () => {
                            controller.enqueue(encoder.encode(suffix));
                            controller.close();
                        };
                    },
                    cancel() {
                        window.__rockySyntheticStreamCancelled = true;
                    }
                });
                return Promise.resolve(new Response(body, {
                    status: 200,
                    headers: {
                        'Content-Type': 'text/event-stream; charset=utf-8',
                        'X-Request-Id': 'req_browser_stream',
                        'X-Rocky-Conversation-Id': 'conversation-browser-stream',
                        'X-Rocky-Message-Stored': 'true'
                    }
                }));
            };
            """
        )

        textarea.send_keys("Demonstrate streaming.")
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Send message']")
        streamed_message = self.wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".chat-message-assistant.chat-message-streaming")
            ),
            message="Expected the first streamed delta before completion.",
        )
        self.assertIn("Streaming now", streamed_message.text)
        self.assertTrue(
            self.driver.find_element(
                By.CSS_SELECTOR, "button[aria-label='Stop waiting for response']"
            ).is_displayed()
        )

        self.driver.execute_script("window.__rockyFinishSyntheticStream();")
        completed_message = self.wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".chat-message-assistant:not(.chat-message-streaming)")
            ),
            message="Expected the streamed assistant message to reach its terminal state.",
        )
        self.assertIn("Streaming now works.", completed_message.text)
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label='Send message']")),
            message="Expected the composer to leave its streaming state.",
        )
        self.wait.until(
            lambda driver: "conversation=conversation-browser-stream" in driver.current_url,
            message="Expected the completed conversation to become addressable in the URL.",
        )
        self.capture_evidence("chat-streaming-completed")

    def test_chat_reconciles_browser_history_after_an_active_stream(self):
        self._login_as_admin()
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url === '/api/chat/conversations' && init.method === 'POST') {
                    return Promise.resolve(Response.json({ conversations: [
                        { conversation_id: 'conversation-a', title: 'Conversation A' },
                        { conversation_id: 'conversation-b', title: 'Conversation B' }
                    ] }));
                }
                if (url.startsWith('/api/chat/conversations/') && init.method === 'POST') {
                    const conversationId = url.split('/').pop();
                    return Promise.resolve(Response.json({ messages: [{
                        message_id: `${conversationId}-message`,
                        role: 'user',
                        content: conversationId === 'conversation-a'
                            ? 'Conversation A history'
                            : 'Conversation B history',
                        status: 'sent'
                    }] }));
                }
                if (url === '/api/chat/capabilities') {
                    return Promise.resolve(Response.json({ imageInput: { enabled: false } }));
                }
                if (url === '/api/chat' && init.method === 'POST') {
                    const encoder = new TextEncoder();
                    const frame = (event) =>
                        `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
                    const prefix = [
                        { type: 'response.created', sequence_number: 0 },
                        { type: 'response.in_progress', sequence_number: 1 },
                        { type: 'response.output_item.added', sequence_number: 2 },
                        { type: 'response.content_part.added', sequence_number: 3 },
                        {
                            type: 'response.output_text.delta',
                            sequence_number: 4,
                            delta: 'Streaming in conversation B'
                        }
                    ].map(frame).join('');
                    const suffix = [
                        {
                            type: 'response.output_text.done',
                            sequence_number: 5,
                            text: 'Streaming in conversation B'
                        },
                        { type: 'response.content_part.done', sequence_number: 6 },
                        { type: 'response.output_item.done', sequence_number: 7 },
                        {
                            type: 'response.completed',
                            sequence_number: 8,
                            response: {
                                id: 'resp_history_stream',
                                status: 'completed',
                                output_text: 'Streaming in conversation B',
                                conversation_id: 'conversation-b',
                                message_stored: true
                            }
                        }
                    ].map(frame).join('');
                    const body = new ReadableStream({
                        start(controller) {
                            controller.enqueue(encoder.encode(prefix));
                            window.__rockyFinishHistoryStream = () => {
                                controller.enqueue(encoder.encode(suffix));
                                controller.close();
                            };
                        }
                    });
                    return Promise.resolve(new Response(body, {
                        status: 200,
                        headers: {
                            'Content-Type': 'text/event-stream; charset=utf-8',
                            'X-Rocky-Conversation-Id': 'conversation-b',
                            'X-Rocky-Message-Stored': 'true'
                        }
                    }));
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )
        self._click_sidebar_destination("Chat")

        self._click_element(
            By.XPATH,
            "//button[.//span[normalize-space()='Conversation A']]",
        )
        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".chat-user-bubble"), "Conversation A history"
            )
        )
        self._click_element(
            By.XPATH,
            "//button[.//span[normalize-space()='Conversation B']]",
        )
        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".chat-user-bubble"), "Conversation B history"
            )
        )

        textarea = self.wait.until(EC.element_to_be_clickable((By.ID, "rocky-chat-input")))
        textarea.send_keys("Keep browser history consistent.")
        self._click_element(By.CSS_SELECTOR, "button[aria-label='Send message']")
        self.wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, ".chat-message-assistant.chat-message-streaming")
            )
        )

        self.driver.back()
        self.wait.until(
            lambda driver: "conversation=conversation-a" in driver.current_url,
            message="Expected Back to request Conversation A while streaming.",
        )
        self.driver.execute_script("window.__rockyFinishHistoryStream();")

        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".chat-user-bubble"), "Conversation A history"
            ),
            message="Expected the queued browser destination to load after streaming finished.",
        )
        self.assertIn("conversation=conversation-a", self.driver.current_url)
        self.assertNotIn("Conversation B history", self.driver.find_element(By.TAG_NAME, "main").text)
        self._assert_no_framework_error_overlay()
        self._assert_no_browser_console_errors()

    def test_chat_previews_and_sends_an_image_only_message(self):
        self._login_as_admin()
        self.driver.execute_script(
            """
            window.__rockyOriginalFetch = window.fetch.bind(window);
            window.fetch = (input, init = {}) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url === '/api/chat/capabilities') {
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
                if (url === '/api/chat' && init.method === 'POST') {
                    window.__rockySyntheticImagePayload = JSON.parse(init.body);
                    return Promise.resolve(Response.json({
                        id: 'resp_browser_image',
                        status: 'completed',
                        output_text: 'I can see the attached image.',
                        message_stored: false
                    }));
                }
                return window.__rockyOriginalFetch(input, init);
            };
            """
        )
        self._click_sidebar_destination("Chat")

        self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Attach images']")),
            message="Expected image capability discovery to enable attachments.",
        )
        fixture_data = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
            "AAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory(prefix="rocky-image-e2e-") as temporary_dir:
            image_path = Path(temporary_dir) / "one-pixel.png"
            image_path.write_bytes(base64.b64decode(fixture_data))
            self.driver.find_element(
                By.CSS_SELECTOR, "input[type='file'][accept*='image/png']"
            ).send_keys(str(image_path))
            self.wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".chat-attachment-preview img")),
                message="Expected a local image preview before sending.",
            )

        send_button = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Send message']")),
            message="Expected an image-only message to be sendable.",
        )
        send_button.click()
        user_image = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".chat-user-bubble .chat-message-images img")),
            message="Expected the optimistic user message to retain its image.",
        )
        self.assertTrue(user_image.get_attribute("src").startswith("data:image/png;base64,"))
        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".chat-message-assistant"),
                "I can see the attached image.",
            )
        )
        payload = self.driver.execute_script("return window.__rockySyntheticImagePayload;")
        self.assertEqual(payload["message"], "")
        self.assertEqual(payload["images"][0]["detail"], "auto")
        self.assertTrue(payload["images"][0]["image_url"].startswith("data:image/png;base64,"))
        self.assertIn(
            "attached images",
            self.driver.find_element(By.CSS_SELECTOR, ".chat-privacy-note").text,
        )
        self.capture_evidence("chat-image-input-completed")

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

    def test_analytics_request_detail_shows_queue_admission(self):
        request_id = "req_queue_ui_evidence"
        now = datetime.now(timezone.utc)
        client = MongitaClientDisk(self._mongita_dir)
        try:
            client["rocky_db"]["telemetry_interactions"].insert_one({
                "_id": request_id,
                "request_id": request_id,
                "schema_version": 3,
                "state": "terminal",
                "outcome": "completed",
                "http_status": 200,
                "received_at": now,
                "terminal_at": now,
                "source": "public_api",
                "operation": "responses.create",
                "actor": {
                    "user_id": "queue-ui-student",
                    "email": "queue-ui-student@kent.edu",
                    "name": "Queue UI Student",
                },
                "model": {
                    "public_model": "course-model",
                    "actual_model": "course-model",
                },
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 2,
                    "total_tokens": 6,
                    "input_bytes": 20,
                    "output_bytes": 10,
                },
                "performance": {"request_latency_ms": 1500},
                "queue": {
                    "status": "admitted",
                    "initial_position": 2,
                    "depth_on_arrival": 1,
                    "wait_ms": 250,
                    "capacity": 12,
                    "queued_bytes_on_arrival": 100,
                },
                "request": {"input_text": "Queue UI test"},
                "response": {"output_text": "Queue UI response"},
                "content_available": True,
                "expires_at": None,
            })
        finally:
            client.close()

        self._login_as_admin()
        self.driver.get(f"{BASE_URL}/?frame=analytics&request={request_id}")
        self._assert_title("Analytics")
        detail = self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".analytics-detail-panel.open")),
            message="Expected the correlated request detail to open.",
        )
        self.wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, ".analytics-detail-panel.open"),
                "Position 2 of 12",
            )
        )
        self.assertIn("Queue status\nAdmitted", detail.text)
        self.assertIn("Queue wait\n250 ms", detail.text)
        self.assertIn("Queue arrival\nPosition 2 of 12", detail.text)
        self.capture_evidence("analytics-queue-admission-detail")

    def test_course_key_warning_and_admin_panels(self):
        self._login_as_admin()

        course_card = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.course-card")),
            message="Expected dashboard courses to use addressable links.",
        )
        self.assertEqual(course_card.tag_name.lower(), "a")
        self.assertIn("frame=courses", course_card.get_attribute("href"))
        self.assertIn("course=", course_card.get_attribute("href"))
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

        self._click_sidebar_destination("Admin Panel")
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

        self._click_sidebar_destination("Chat")
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
