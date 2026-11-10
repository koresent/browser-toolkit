import unittest
from playwright.sync_api import sync_playwright

from browser_toolkit.contrast_checker import JS_CONTRAST_ANALYSIS
from browser_toolkit.css_color_extractor import filter_declarations, parse_css_structure
from browser_toolkit.palette_extractor import JS_EXTRACT_PAGE_PALETTE
from browser_toolkit.palettes import GRUVBOX_PALETTES, format_gruvbox_css, get_gruvbox


class TestColorsAndPalettes(unittest.TestCase):
    def test_gruvbox_palettes(self):
        dark = get_gruvbox("dark")
        self.assertEqual(dark["bg0"], "#282828")
        self.assertEqual(dark["fg1"], "#ebdbb2")

        dark_hard = get_gruvbox("dark-hard")
        self.assertEqual(dark_hard["bg0"], "#1d2021")

        dark_soft = get_gruvbox("dark-soft")
        self.assertEqual(dark_soft["bg0"], "#32302f")

        light = get_gruvbox("light")
        self.assertEqual(light["bg0"], "#fbf1c7")
        self.assertEqual(light["fg0"], "#282828")

        # Test CSS variable formatting
        css_formatted = format_gruvbox_css("dark")
        self.assertIn(":root", css_formatted)
        self.assertIn("--bg0: #282828;", css_formatted)
        self.assertIn("--fg1: #ebdbb2;", css_formatted)

    def test_css_color_extractor_filtering(self):
        block = """
            margin: 10px 20px;
            padding: 5px;
            background-color: #282828;
            color: #ebdbb2;
            border: 1px solid rgba(255, 255, 255, 0.2);
            font-size: 14px;
            display: flex;
            box-shadow: 0 4px 6px #1d2021;
            fill: currentcolor;
            background: var(--bg-card);
        """
        filtered = filter_declarations(block)
        joined = " ".join(filtered)

        # Retained declarations
        self.assertIn("background-color: #282828", joined)
        self.assertIn("color: #ebdbb2", joined)
        self.assertIn("box-shadow: 0 4px 6px #1d2021", joined)
        self.assertIn("fill: currentcolor", joined)

        # Filtered out declarations
        self.assertNotIn("margin:", joined)
        self.assertNotIn("padding:", joined)
        self.assertNotIn("font-size:", joined)
        self.assertNotIn("display:", joined)
        self.assertNotIn("var(--bg-card)", joined)

    def test_parse_css_structure(self):
        raw_css = """
        /* Header section */
        .header {
            background-color: #333333;
            height: 60px;
            color: #ffffff;
        }

        .header .logo {
            fill: #ff0000;
            width: 120px;
        }
        """
        parsed = parse_css_structure(raw_css)
        self.assertIn(".header {", parsed)
        self.assertIn("background-color: #333333;", parsed)
        self.assertIn("color: #ffffff;", parsed)
        self.assertNotIn("height: 60px;", parsed)
        self.assertIn(".header .logo {", parsed)
        self.assertIn("fill: #ff0000;", parsed)
        self.assertNotIn("width: 120px;", parsed)


class TestColorAnalysisInBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.firefox.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_contrast_analysis_js(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body style="background-color: #282828; margin: 0; padding: 20px;">
          <h1 style="color: #ebdbb2;">High Contrast Text</h1>
          <p style="color: #302d2b; background-color: #282828;">Low Contrast Invisible Text</p>
        </body>
        </html>
        """)

        data = page.evaluate(JS_CONTRAST_ANALYSIS)
        page.close()

        self.assertGreater(data["totalChecked"], 0)
        # Should detect the low contrast paragraph
        self.assertGreater(len(data["issues"]), 0)
        worst = data["issues"][0]
        self.assertLess(worst["contrastRatio"], 3.0)
        self.assertIn("Low Contrast", worst["textSnippet"])

    def test_page_palette_extraction_js(self):
        page = self.browser.new_page()
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            :root {
                --theme-bg: #1d2021;
                --theme-text: #ebdbb2;
                --brand-accent: #fabd2f;
            }
            .card {
                background-color: #32302f;
                color: #ebdbb2;
                border: 1px solid #504945;
            }
          </style>
        </head>
        <body>
          <div class="card">Card 1</div>
          <div class="card">Card 2</div>
        </body>
        </html>
        """)

        data = page.evaluate(JS_EXTRACT_PAGE_PALETTE)
        page.close()

        # Check CSS variables extracted
        var_names = [v["name"] for v in data["siteColorVariables"]]
        self.assertIn("--theme-bg", var_names)
        self.assertIn("--theme-text", var_names)
        self.assertIn("--brand-accent", var_names)

        # Check DOM computed background clustering
        top_bgs = [b["color"] for b in data["backgroundColors"]]
        self.assertTrue(any("#32302f" in b for b in top_bgs))


if __name__ == "__main__":
    unittest.main()
