import unittest
from playwright.sync_api import sync_playwright

from browser_toolkit.gm_shim import GM_FULL_SHIM_JS
from browser_toolkit.mutation_tracker import attach_mutation_tracker, collect_dom_mutations
from browser_toolkit.js_auditor import inject_userscript
from browser_toolkit.spa_checker import check_spa_resilience


class TestJSToolkit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_gm_polyfill_suite(self):
        page = self.browser.new_page()
        page.set_content("<html><body><h1>Test GM</h1></body></html>")
        page.evaluate(GM_FULL_SHIM_JS)

        # Test sync and async GM storage
        script = """
        (() => {
            GM_setValue('test_sync', 'sync_val');
            GM.setValue('test_async', 42);

            GM_registerMenuCommand('Action One', () => {
                window.__action_called = true;
                return 'result_1';
            });

            GM_setClipboard('copied_token_123');
        })();
        """
        page.evaluate(script)

        # Check values
        v1 = page.evaluate("() => GM_getValue('test_sync')")
        self.assertEqual(v1, "sync_val")

        v2 = page.evaluate("async () => await GM.getValue('test_async')")
        self.assertEqual(v2, 42)

        # Check menu command invocation bridge
        cmd_res = page.evaluate("() => window._gm_invoke_command('Action One')")
        self.assertTrue(cmd_res["success"])
        self.assertEqual(cmd_res["result"], "result_1")
        self.assertTrue(page.evaluate("() => window.__action_called"))

        # Check clipboard log
        clip = page.evaluate("() => window._gm_clipboard_log")
        self.assertEqual(len(clip), 1)
        self.assertEqual(clip[0]["text"], "copied_token_123")

        page.close()

    def test_dom_mutation_tracking(self):
        page = self.browser.new_page()
        page.set_content("<html><body><div id='container'></div></body></html>")

        script = """
        (() => {
            const btn = document.createElement('button');
            btn.id = 'my-custom-btn';
            btn.className = 'btn-action primary';
            btn.textContent = 'Download All';
            document.getElementById('container').appendChild(btn);

            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.textContent = 'v1.0';
            btn.appendChild(badge);
        })();
        """

        res = inject_userscript(page, raw_js=script, run_at="document-end", settle_ms=100)
        page.close()

        self.assertTrue(res.executed)
        self.assertGreater(len(res.mutations.added_nodes), 0)

        added_selectors = [n.selector for n in res.mutations.added_nodes]
        self.assertTrue(any("my-custom-btn" in s for s in added_selectors))
        btn_info = next(n for n in res.mutations.added_nodes if "my-custom-btn" in n.selector)
        self.assertEqual(btn_info.tag_name, "button")
        self.assertIn("Download All", btn_info.text_snippet)

    def test_spa_resilience_checker(self):
        page = self.browser.new_page()
        page.set_content("""
        <html>
        <body>
          <div id="content">Page A</div>
        </body>
        </html>
        """)

        # UserScript that listens to turbo:load / popstate to re-mount
        resilient_script = """
        function mount() {
            if (!document.getElementById('injected-header')) {
                const h = document.createElement('h2');
                h.id = 'injected-header';
                h.textContent = 'Resilient Header';
                document.body.prepend(h);
            }
        }
        mount();
        window.addEventListener('popstate', mount);
        document.addEventListener('turbo:load', mount);
        """

        rep = check_spa_resilience(
            page=page,
            initial_url=page.url,
            target_spa_url=page.url + "#page2",
            raw_js=resilient_script,
            run_at="document-end",
        )
        page.close()

        self.assertTrue(rep.survived)
        self.assertIn("#injected-header", rep.retained_selectors)


if __name__ == "__main__":
    unittest.main()
