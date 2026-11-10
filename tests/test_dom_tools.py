import unittest
from playwright.sync_api import sync_playwright

from browser_toolkit.css_auditor import audit_css_on_page
from browser_toolkit.interaction import PageInteractor, execute_action_sequence
from browser_toolkit.search import JS_SEARCH_DOM
from browser_toolkit.selector_generator import JS_SELECTOR_SYNTHESIZER
from browser_toolkit.test_rule import JS_TEST_RULE_IMPACT, test_rule_impact


class TestDOMTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_page_interactor_and_action_sequence(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body>
          <input id="search-box" type="text" value="" />
          <button id="submit-btn" onclick="document.getElementById('result').textContent = 'Submitted ' + document.getElementById('search-box').value">Go</button>
          <div id="result">Initial</div>
        </body>
        </html>
        """)

        interactor = PageInteractor(page)
        self.assertTrue(interactor.fill("#search-box", "Gruvbox"))
        self.assertTrue(interactor.click("#submit-btn"))
        page.wait_for_timeout(100)

        result_text = page.text_content("#result")
        self.assertEqual(result_text, "Submitted Gruvbox")

        # Test execute_action_sequence
        actions = [
            {"action": "fill", "selector": "#search-box", "text": "Dark Theme"},
            {"action": "click", "selector": "#submit-btn"},
            {"action": "wait", "ms": 50},
        ]
        results = execute_action_sequence(page, actions)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["status"] == "success" for r in results))
        self.assertEqual(page.text_content("#result"), "Submitted Dark Theme")
        page.close()

    def test_selector_synthesizer(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body>
          <button data-testid="fork-btn" class="btn primary-action">Fork Repository</button>
          <div id="account-settings" class="settings-pane">Settings</div>
        </body>
        </html>
        """)

        page.evaluate(JS_SELECTOR_SYNTHESIZER)

        # Run synthesizer on the button
        scored_btn = page.evaluate("() => window._synthesizeSelectorForElement(document.querySelector('button'))")
        self.assertGreater(len(scored_btn), 0)
        self.assertTrue(any('data-testid="fork-btn"' in s["selector"] for s in scored_btn))

        # Run synthesizer on the div
        scored_div = page.evaluate("() => window._synthesizeSelectorForElement(document.querySelector('#account-settings'))")
        self.assertGreater(len(scored_div), 0)
        self.assertTrue(any("#account-settings" in s["selector"] for s in scored_div))
        page.close()

    def test_search_dom(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body>
          <nav aria-label="Main Navigation">
            <a href="/home">Home</a>
            <a href="/explore">Explore Topics</a>
          </nav>
          <div class="user-profile-badge">User Profile</div>
        </body>
        </html>
        """)

        # Search by text
        matches_text = page.evaluate(JS_SEARCH_DOM, {"text": "Explore Topics"})
        self.assertGreater(len(matches_text), 0)
        self.assertTrue(any(m["tagName"] == "a" for m in matches_text))

        # Search by keyword in class
        matches_kw = page.evaluate(JS_SEARCH_DOM, {"keyword": "profile"})
        self.assertGreater(len(matches_kw), 0)
        self.assertIn("user-profile-badge", matches_kw[0]["className"])
        page.close()

    def test_css_auditor(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body>
          <header class="app-header">
            <h1 class="title">My Application</h1>
          </header>
          <main class="content">Content</main>
        </body>
        </html>
        """)

        css = """
        .app-header { background: #282828; }
        .title { color: #ebdbb2; }
        .non-existent-modal { display: none; }
        """
        res = audit_css_on_page(page, css)
        self.assertEqual(res.total_selectors, 3)

        matched_sels = [m.selector for m in res.matched]
        self.assertIn(".app-header", matched_sels)
        self.assertIn(".title", matched_sels)

        dead_sels = [d.selector for d in res.dead]
        self.assertIn(".non-existent-modal", dead_sels)
        page.close()

    def test_rule_impact(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; width: 1000px; height: 1000px;">
          <div id="giant-hero" style="width: 1000px; height: 800px; background: blue;">Hero</div>
          <button id="small-btn">Click me</button>
        </body>
        </html>
        """)

        # Impact test for the giant hero banner (> 25% of viewport)
        impact = page.evaluate(JS_TEST_RULE_IMPACT, "#giant-hero { display: none; }")
        self.assertGreater(len(impact["matched"]), 0)
        hero_item = impact["matched"][0]
        self.assertTrue(hero_item["isLargeElement"])
        self.assertGreater(hero_item["viewportRatioPercent"], 25)

        # Impact test for small button (< 25% of viewport)
        btn_impact = page.evaluate(JS_TEST_RULE_IMPACT, "#small-btn { color: red; }")
        self.assertGreater(len(btn_impact["matched"]), 0)
        btn_item = btn_impact["matched"][0]
        self.assertFalse(btn_item["isLargeElement"])
        page.close()


if __name__ == "__main__":
    unittest.main()
