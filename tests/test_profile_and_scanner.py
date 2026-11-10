import tempfile
import unittest
from pathlib import Path

from browser_toolkit.profile import ZenProfileContext, find_zen_profile
from browser_toolkit.scanner import scan_directory


class TestProfileAndScanner(unittest.TestCase):
    def test_find_zen_profile(self):
        profile = find_zen_profile()
        self.assertIsNotNone(profile)
        self.assertTrue(profile.exists())
        self.assertTrue((profile / "prefs.js").exists())

    def test_zen_profile_context(self):
        profile = find_zen_profile()

        # Without profile cloning
        with ZenProfileContext(profile, use_profile=False) as ctx:
            self.assertIsNone(ctx)

        # With profile cloning
        with ZenProfileContext(profile, use_profile=True) as temp_dir:
            self.assertIsNotNone(temp_dir)
            self.assertTrue(temp_dir.exists())
            self.assertTrue((temp_dir / "prefs.js").exists())
            temp_path = temp_dir

        # Must be cleaned up after exit
        self.assertFalse(temp_path.exists())

    def test_scan_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            # Create dummy userstyle and userscript files
            style1 = root / "site1" / "style.user.css"
            style1.parent.mkdir(parents=True)
            style1.write_text("/* ==UserStyle==\n@name Site 1\n==/UserStyle== */\nbody { color: red; }")

            script1 = root / "site2" / "script.user.js"
            script1.parent.mkdir(parents=True)
            script1.write_text("// ==UserScript==\n// @name Script 1\n// @match *://*.site2.com/*\n// ==/UserScript==\nconsole.log(1);")

            # Ignore normal css/js files
            normal_css = root / "ignored.css"
            normal_css.write_text("h1 { color: blue; }")

            # Run scan without launching profile
            res = scan_directory(root, use_profile=False, headless=True)
            self.assertEqual(res["total_scanned"], 2)
            styles = [r for r in res["results"] if r.get("type") == "userstyle"]
            scripts = [r for r in res["results"] if r.get("type") == "userscript"]
            self.assertEqual(len(styles), 1)
            self.assertEqual(len(scripts), 1)
            self.assertEqual(styles[0]["name"], "Site 1")
            self.assertEqual(scripts[0]["name"], "Script 1")


if __name__ == "__main__":
    unittest.main()
