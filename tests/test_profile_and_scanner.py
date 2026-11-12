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

    def test_zen_profile_clean_styles_preserves_cookies(self):
        with tempfile.TemporaryDirectory() as src_dir:
            src = Path(src_dir)
            (src / "prefs.js").write_text("", encoding="utf-8")
            (src / "cookies.sqlite").write_text("cookie-data", encoding="utf-8")
            stylus_idb = src / "storage" / "default" / "moz-extension+++abc-stylus" / "idb"
            stylus_idb.mkdir(parents=True)
            (stylus_idb / "489858440shtsyil.sqlite").write_text("stylus", encoding="utf-8")
            vm_idb = src / "storage" / "default" / "moz-extension+++def-vm" / "idb"
            vm_idb.mkdir(parents=True)
            (vm_idb / "1234vm.sqlite").write_text("vm", encoding="utf-8")

            with ZenProfileContext(str(src), use_profile=True, clean_styles=True) as clone:
                self.assertIsNotNone(clone)
                self.assertTrue((clone / "cookies.sqlite").exists())
                self.assertFalse((clone / "storage" / "default" / "moz-extension+++abc-stylus").exists())
                self.assertTrue((clone / "storage" / "default" / "moz-extension+++def-vm").exists())

    def test_zen_profile_sanitization_nss_and_sessions(self):
        with tempfile.TemporaryDirectory() as src_dir:
            src = Path(src_dir)
            (src / "prefs.js").write_text("", encoding="utf-8")
            (src / "cookies.sqlite").write_text("cookie-data", encoding="utf-8")
            (src / "zen-sessions.jsonlz4").write_text("session", encoding="utf-8")
            (src / "zen-live-folders.jsonlz4").write_text("folders", encoding="utf-8")
            (src / "signedInUser.json").write_text("sync-auth", encoding="utf-8")
            (src / "pkcs11.txt").write_text(f"parameters=configdir='sql:{src}'\n", encoding="utf-8")
            dangling_lock = src / "lock"
            dangling_lock.symlink_to("127.0.0.1:+999999")

            with ZenProfileContext(str(src), use_profile=True) as clone:
                self.assertIsNotNone(clone)
                # Cookies and authentic auth remain intact
                self.assertTrue((clone / "cookies.sqlite").exists())
                # Zen session files and sync must be removed
                self.assertFalse((clone / "zen-sessions.jsonlz4").exists())
                self.assertFalse((clone / "zen-live-folders.jsonlz4").exists())
                self.assertFalse((clone / "signedInUser.json").exists())
                # Dangling lock must be removed
                self.assertFalse((clone / "lock").is_symlink())
                # pkcs11.txt must point to the clone directory, never the src directory
                pkcs_content = (clone / "pkcs11.txt").read_text(encoding="utf-8")
                self.assertIn(str(clone), pkcs_content)
                self.assertNotIn(str(src), pkcs_content)

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
