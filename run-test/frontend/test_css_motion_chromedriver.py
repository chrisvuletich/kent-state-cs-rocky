from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class CssAndMotionE2ETests(FrontendBrowserTestCase):
    def _set_reduced_motion(self, value: str) -> None:
        self.driver.execute_cdp_cmd(
            "Emulation.setEmulatedMedia",
            {
                "media": "screen",
                "features": [{"name": "prefers-reduced-motion", "value": value}],
            },
        )

    def test_reduced_motion_keeps_content_and_status_visible(self):
        self._set_reduced_motion("reduce")
        try:
            self.driver.get(f"{BASE_URL}/credits")
            self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".credits-page h1")))
            self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-rocky-page-ready='true']")
                )
            )
            self._click_element(By.CSS_SELECTOR, ".roll-button")
            credits_shell = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".credits-shell.credits-rolling"))
            )
            credits_state = self.driver.execute_script(
                """
                const shell = arguments[0];
                const list = shell.querySelector('.credits-list');
                const stage = shell.querySelector('.credits-stage');
                return {
                    animationName: getComputedStyle(list).animationName,
                    transform: getComputedStyle(list).transform,
                    stageOverflowY: getComputedStyle(stage).overflowY,
                    liveRegion: stage.getAttribute('aria-live'),
                    finaleVisible: Boolean(
                        shell.querySelector('.credits-finale')?.getClientRects().length
                    )
                };
                """,
                credits_shell,
            )
            self.assertEqual(credits_state["animationName"], "none")
            self.assertEqual(credits_state["transform"], "none")
            self.assertIn(credits_state["stageOverflowY"], ("auto", "scroll"))
            self.assertEqual(credits_state["liveRegion"], "polite")
            self.assertTrue(credits_state["finaleVisible"])

            self._login_as_preview_role("admin")
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
            # The isolated harness intentionally omits the optional chat service.
            # Clear its settled Dashboard 502 before checking this CSS-only flow.
            self._read_browser_console()
            presentation = self.driver.execute_script(
                """
                const card = document.querySelector('.course-card');
                return {
                    fontFamily: getComputedStyle(document.body).fontFamily,
                    cardTransitionDurations: card
                        ? getComputedStyle(card).transitionDuration.split(',').map((value) => value.trim())
                        : []
                };
                """
            )
            self.assertIn("system-ui", presentation["fontFamily"])
            self.assertTrue(presentation["cardTransitionDurations"])
            self.assertTrue(
                all(value == "0s" for value in presentation["cardTransitionDurations"])
            )
            self._assert_no_framework_error_overlay()
            self._assert_no_browser_console_errors()
        finally:
            self._set_reduced_motion("no-preference")


if __name__ == "__main__":
    import unittest

    unittest.main()
