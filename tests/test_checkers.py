import unittest
from playwright.sync_api import sync_playwright

from browser_toolkit.responsive_checker import ResponsiveChecker, JS_RESPONSIVE_AUDIT
from browser_toolkit.theme_flaw_checker import ThemeFlawChecker, JS_THEME_FLAW_AUDIT


class TestResponsiveChecker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_horizontal_overflow_and_touch_target_detection(self):
        page = self.browser.new_page()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            body { margin: 0; padding: 0; }
            .giant-card {
                width: 700px;
                height: 100px;
                background: red;
            }
            .tiny-button {
                width: 14px;
                height: 14px;
                display: inline-block;
            }
          </style>
        </head>
        <body>
          <div class="giant-card" id="blowout">Overflowing Box</div>
          <button class="tiny-button" id="bad-btn">X</button>
        </body>
        </html>
        """
        page.set_viewport_size({"width": 390, "height": 844})
        page.set_content(html)
        page.wait_for_timeout(100)

        raw = page.evaluate(JS_RESPONSIVE_AUDIT)
        page.close()

        self.assertTrue(raw["hasHorizontalOverflow"])
        self.assertGreater(len(raw["overflowElements"]), 0)
        top_overflow = raw["overflowElements"][0]
        self.assertIn("blowout", top_overflow["selector"])
        self.assertGreater(top_overflow["overflowPx"], 250)

        # Touch targets check on mobile (<= 820px)
        self.assertGreater(len(raw["touchTargetIssues"]), 0)
        touch_sel = raw["touchTargetIssues"][0]["selector"]
        self.assertIn("bad-btn", touch_sel)


class TestThemeFlawChecker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_bleedthrough_and_invisible_text_detection(self):
        page = self.browser.new_page()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body { background: #282828; color: #ebdbb2; margin: 0; }
            .white-card {
                background-color: #ffffff;
                width: 300px;
                height: 150px;
            }
            .stealth-text {
                color: #2a2a2a;
                background-color: #282828;
                font-size: 14px;
            }
            input.bright-input {
                background-color: #ffffff;
                color: #000000;
            }
          </style>
        </head>
        <body>
          <div class="white-card" id="bad-card">White Flash</div>
          <p class="stealth-text" id="bad-text">You cannot read this</p>
          <input type="text" class="bright-input" id="bad-input" value="test" />
        </body>
        </html>
        """
        page.set_viewport_size({"width": 1024, "height": 768})
        page.set_content(html)
        page.wait_for_timeout(100)

        raw = page.evaluate(JS_THEME_FLAW_AUDIT, "dark")
        page.close()

        # Bleedthrough
        self.assertGreater(len(raw["bleedthroughIssues"]), 0)
        self.assertIn("bad-card", raw["bleedthroughIssues"][0]["selector"])

        # Invisible text
        self.assertGreater(len(raw["invisibleTextIssues"]), 0)
        self.assertIn("bad-text", raw["invisibleTextIssues"][0]["selector"])
        self.assertLess(raw["invisibleTextIssues"][0]["contrastRatio"], 1.8)

        # Unstyled bright input
        self.assertGreater(len(raw["unstyledInputIssues"]), 0)
        self.assertIn("bad-input", raw["unstyledInputIssues"][0]["selector"])


if __name__ == "__main__":
    unittest.main()
