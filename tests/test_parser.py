import tempfile
import unittest
from pathlib import Path

from browser_toolkit.parser import (
    StyleSection,
    UserScriptInfo,
    UserStyleInfo,
    parse_userscript,
    parse_userstyle,
)


class TestParser(unittest.TestCase):
    def test_parse_userstyle_full_metadata_and_sections(self):
        sample_css = """/* ==UserStyle==
@name         Habr Gruvbox Dark
@namespace    github.com/koresent/userstyles
@version      2.1.0
@description  Comprehensive dark theme for Habr
@author       Koresent
@homepageURL  https://github.com/koresent/userstyles
@license      MIT
==/UserStyle== */

@-moz-document domain("habr.com"), domain("qna.habr.com") {
    :root {
        --bg-primary: #282828;
        --fg-primary: #ebdbb2;
    }

    body {
        background-color: var(--bg-primary);
        color: var(--fg-primary);
    }

    .nested {
        div {
            color: #fabd2f;
        }
    }
}

@-moz-document url-prefix("https://habr.com/ru/articles/") {
    .article-formatted-body {
        font-family: monospace;
    }
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".user.css", delete=False) as f:
            f.write(sample_css)
            f_path = Path(f.name)

        try:
            info = parse_userstyle(f_path)
            self.assertEqual(info.name, "Habr Gruvbox Dark")
            self.assertEqual(info.namespace, "github.com/koresent/userstyles")
            self.assertEqual(info.version, "2.1.0")
            self.assertEqual(info.description, "Comprehensive dark theme for Habr")
            self.assertEqual(info.author, "Koresent")
            self.assertEqual(info.homepage_url, "https://github.com/koresent/userstyles")
            self.assertEqual(len(info.sections), 2)

            sec1 = info.sections[0]
            self.assertIn("habr.com", sec1.domains)
            self.assertIn("qna.habr.com", sec1.domains)
            self.assertIn("--bg-primary: #282828", sec1.css_content)
            self.assertIn(".nested", sec1.css_content)

            sec2 = info.sections[1]
            self.assertEqual(len(sec2.url_prefixes), 1)
            self.assertEqual(sec2.url_prefixes[0], "https://habr.com/ru/articles/")
            self.assertIn("article-formatted-body", sec2.css_content)

            # Test URL-specific CSS extraction
            css_for_habr = info.get_combined_css_for_url("https://habr.com/ru/feed/")
            self.assertIn("--bg-primary: #282828", css_for_habr)
            self.assertNotIn("article-formatted-body", css_for_habr)

            css_for_article = info.get_combined_css_for_url("https://habr.com/ru/articles/12345/")
            self.assertIn("--bg-primary: #282828", css_for_article)
            self.assertIn("article-formatted-body", css_for_article)

            css_for_other = info.get_combined_css_for_url("https://example.com")
            self.assertNotIn("--bg-primary: #282828", css_for_other)

            all_css = info.get_all_css()
            self.assertIn("--bg-primary: #282828", all_css)
            self.assertIn("article-formatted-body", all_css)
        finally:
            if f_path.exists():
                f_path.unlink()

    def test_parse_userstyle_fallback_no_moz_document(self):
        sample_css = """/* ==UserStyle==
@name Simple Fallback
@version 1.0.0
==/UserStyle== */
body { background: black; color: white; }
"""
        with tempfile.NamedTemporaryFile("w", suffix=".user.css", delete=False) as f:
            f.write(sample_css)
            f_path = Path(f.name)

        try:
            info = parse_userstyle(f_path)
            self.assertEqual(info.name, "Simple Fallback")
            self.assertEqual(len(info.sections), 1)
            self.assertIn("body { background: black; color: white; }", info.sections[0].css_content)
            # Should apply globally
            self.assertIn("background: black", info.get_combined_css_for_url("https://any-site.org"))
        finally:
            if f_path.exists():
                f_path.unlink()

    def test_parse_userscript_metadata_and_url_derivation(self):
        sample_js = """// ==UserScript==
// @name         YouTube Enhancer
// @namespace    https://github.com/koresent
// @version      3.4.1
// @description  Custom controls and keybindings for YouTube
// @author       Koresent
// @match        *://*.youtube.com/*
// @include      https://youtube.com/watch*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-start
// ==/UserScript==

console.log("YouTube script active");
"""
        with tempfile.NamedTemporaryFile("w", suffix=".user.js", delete=False) as f:
            f.write(sample_js)
            f_path = Path(f.name)

        try:
            info = parse_userscript(f_path)
            self.assertEqual(info.name, "YouTube Enhancer")
            self.assertEqual(info.namespace, "https://github.com/koresent")
            self.assertEqual(info.version, "3.4.1")
            self.assertEqual(info.description, "Custom controls and keybindings for YouTube")
            self.assertEqual(info.author, "Koresent")
            self.assertEqual(info.run_at, "document-start")
            self.assertIn("*://*.youtube.com/*", info.matches)
            self.assertIn("https://youtube.com/watch*", info.includes)
            self.assertIn("GM_setValue", info.grants)
            self.assertIn("GM_getValue", info.grants)

            target_url = info.get_target_url()
            self.assertTrue(target_url.startswith("https://youtube.com"))
        finally:
            if f_path.exists():
                f_path.unlink()


if __name__ == "__main__":
    unittest.main()
