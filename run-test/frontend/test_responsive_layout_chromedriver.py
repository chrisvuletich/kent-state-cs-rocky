from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from frontend.test_support import BASE_URL, FrontendBrowserTestCase


class ResponsiveLayoutE2ETests(FrontendBrowserTestCase):
    def _wait_for_analytics(self):
        state = self.wait.until(
            lambda driver: driver.find_elements(By.CSS_SELECTOR, ".analytics-kpis")
            or driver.find_elements(By.XPATH, "//button[normalize-space()='Try again']")
        )
        if state[0].tag_name == "button":
            state[0].click()
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".analytics-kpis"))
        )

    def _assert_local_horizontal_scroll(self, wrapper_selector: str, table_selector: str):
        dimensions = self.driver.execute_script(
            """
            const wrapper = document.querySelector(arguments[0]);
            const table = document.querySelector(arguments[1]);
            if (!wrapper || !table) return null;
            const bounds = wrapper.getBoundingClientRect();
            return {
              wrapperClientWidth: wrapper.clientWidth,
              wrapperScrollWidth: wrapper.scrollWidth,
              tableScrollWidth: table.scrollWidth,
              overflowX: getComputedStyle(wrapper).overflowX,
              left: bounds.left,
              right: bounds.right,
              viewportWidth: window.innerWidth,
            };
            """,
            wrapper_selector,
            table_selector,
        )
        self.assertIsNotNone(dimensions, f"Expected {wrapper_selector} and {table_selector}.")
        self.assertIn(dimensions["overflowX"], ("auto", "scroll"))
        self.assertLessEqual(dimensions["right"], dimensions["viewportWidth"] + 1)
        self.assertGreaterEqual(dimensions["left"], -1)
        self.assertGreater(
            dimensions["tableScrollWidth"],
            dimensions["wrapperClientWidth"],
            f"Expected {table_selector} to be wider than its local scroll region.",
        )
        self.assertGreater(
            dimensions["wrapperScrollWidth"],
            dimensions["wrapperClientWidth"],
            f"Expected {wrapper_selector} to own horizontal overflow.",
        )

        scrolled = self.driver.execute_script(
            """
            const wrapper = document.querySelector(arguments[0]);
            wrapper.scrollLeft = wrapper.scrollWidth;
            return wrapper.scrollLeft;
            """,
            wrapper_selector,
        )
        self.assertGreater(scrolled, 0)
        self._assert_no_document_horizontal_overflow()

    def test_navigation_is_reachable_at_limited_heights(self):
        self._login_as_preview_role("admin")

        for viewport_name in ("short_laptop", "phone_landscape"):
            with self.subTest(viewport=viewport_name):
                self._set_viewport(viewport_name)
                self.driver.get(f"{BASE_URL}/?frame=dashboard")
                self._assert_title("Dashboard")

                layout = self.driver.execute_script(
                    """
                    const nav = document.querySelector('.sidebar-navigation');
                    const footer = document.querySelector('.sidebar-footer');
                    const navBounds = nav.getBoundingClientRect();
                    const footerBounds = footer.getBoundingClientRect();
                    return {
                      navClientHeight: nav.clientHeight,
                      navScrollHeight: nav.scrollHeight,
                      navBottom: navBounds.bottom,
                      footerTop: footerBounds.top,
                      overflowY: getComputedStyle(nav).overflowY,
                    };
                    """
                )
                self.assertIn(layout["overflowY"], ("auto", "scroll"))
                self.assertGreater(layout["navScrollHeight"], layout["navClientHeight"])
                self.assertLessEqual(layout["navBottom"], layout["footerTop"] + 1)

                last_link_is_reachable = self.driver.execute_script(
                    """
                    const nav = document.querySelector('.sidebar-navigation');
                    const chat = [...nav.querySelectorAll('a')].find(
                      (link) => link.textContent.trim() === 'Chat'
                    );
                    nav.scrollTop = nav.scrollHeight;
                    const navBounds = nav.getBoundingClientRect();
                    const chatBounds = chat.getBoundingClientRect();
                    return chatBounds.top >= navBounds.top - 1 && chatBounds.bottom <= navBounds.bottom + 1;
                    """
                )
                self.assertTrue(last_link_is_reachable)
                self._assert_no_document_horizontal_overflow()

    def test_wide_tables_scroll_inside_their_regions(self):
        self._login_as_preview_role("admin")
        self._set_viewport("narrow_phone")

        table_views = (
            ("users", "User Management", ".table-container", ".users-table"),
            ("audit", "Audit Logs", ".table-container", ".audit-table"),
            ("api-keys", "API Keys", ".table-container", ".audit-table"),
        )
        for frame, title, wrapper_selector, table_selector in table_views:
            with self.subTest(frame=frame):
                self.driver.get(f"{BASE_URL}/?frame={frame}")
                self._assert_title(title)
                self.wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, table_selector))
                )
                self._assert_local_horizontal_scroll(wrapper_selector, table_selector)

        self.driver.get(f"{BASE_URL}/?frame=analytics")
        self._assert_title("Analytics")
        self._wait_for_analytics()
        self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".breakdown-table-scroll table"))
        )
        self._assert_local_horizontal_scroll(
            ".breakdown-table-scroll", ".breakdown-table-scroll table"
        )

    def test_analytics_summaries_wrap_without_clipping(self):
        self._login_as_preview_role("admin")

        for viewport_name, minimum_rows in (("phone_landscape", 2), ("narrow_phone", 4)):
            with self.subTest(viewport=viewport_name):
                self._set_viewport(viewport_name)
                self.driver.get(f"{BASE_URL}/?frame=analytics")
                self._assert_title("Analytics")
                self._wait_for_analytics()

                layout = self.driver.execute_script(
                    """
                    const summary = document.querySelector('.analytics-kpis');
                    const bounds = summary.getBoundingClientRect();
                    const cards = [...summary.querySelectorAll('article')].map((card) => {
                      const cardBounds = card.getBoundingClientRect();
                      return {
                        top: Math.round(cardBounds.top),
                        left: cardBounds.left,
                        right: cardBounds.right,
                      };
                    });
                    return {
                      cardCount: cards.length,
                      rowCount: new Set(cards.map((card) => card.top)).size,
                      cardsInside: cards.every(
                        (card) => card.left >= bounds.left - 1 && card.right <= bounds.right + 1
                      ),
                      clientWidth: summary.clientWidth,
                      scrollWidth: summary.scrollWidth,
                    };
                    """
                )
                self.assertEqual(layout["cardCount"], 4)
                self.assertGreaterEqual(layout["rowCount"], minimum_rows)
                self.assertTrue(layout["cardsInside"])
                self.assertLessEqual(layout["scrollWidth"], layout["clientWidth"] + 1)

                if viewport_name == "narrow_phone":
                    window_layout = self.driver.execute_script(
                        """
                        const control = document.querySelector('.analytics-window-control');
                        const buttons = [...control.querySelectorAll('button')];
                        return {
                          clientWidth: control.clientWidth,
                          scrollWidth: control.scrollWidth,
                          rowCount: new Set(
                            buttons.map((button) => Math.round(button.getBoundingClientRect().top))
                          ).size,
                          buttonsInside: buttons.every((button) => {
                            const buttonBounds = button.getBoundingClientRect();
                            const controlBounds = control.getBoundingClientRect();
                            return buttonBounds.left >= controlBounds.left - 1
                              && buttonBounds.right <= controlBounds.right + 1;
                          }),
                        };
                        """
                    )
                    self.assertLessEqual(
                        window_layout["scrollWidth"], window_layout["clientWidth"] + 1
                    )
                    self.assertEqual(window_layout["rowCount"], 2)
                    self.assertTrue(window_layout["buttonsInside"])
                self._assert_no_document_horizontal_overflow()


if __name__ == "__main__":
    import unittest

    unittest.main()
