import shutil
import tempfile
import unittest
from pathlib import Path

from browser_toolkit.extension_manager import ExtensionManager


class TestExtensionManager(unittest.TestCase):
    def setUp(self):
        self.mgr = ExtensionManager()

    def test_webext_uuids_loaded(self):
        self.assertGreater(len(self.mgr.webext_uuids), 0)
        self.assertIn(ExtensionManager.STYLUS_ADDON_ID, self.mgr.webext_uuids)
        self.assertIn(ExtensionManager.VM_ADDON_ID, self.mgr.webext_uuids)

    def test_stylus_db_inspection(self):
        db_path = self.mgr.get_stylus_db_path()
        self.assertIsNotNone(db_path)
        self.assertTrue(db_path.exists())

        styles = self.mgr.list_styles()
        self.assertGreater(len(styles), 20)
        qna_style = next((s for s in styles if "qna habr" in s.name.lower()), None)
        self.assertIsNotNone(qna_style)
        self.assertTrue(qna_style.enabled)

        # Test to_usercss generation
        usercss = qna_style.to_usercss()
        self.assertIn("==UserStyle==", usercss)
        self.assertIn("@-moz-document", usercss)

    def test_violentmonkey_db_inspection(self):
        db_path = self.mgr.get_violentmonkey_db_path()
        self.assertIsNotNone(db_path)
        self.assertTrue(db_path.exists())

        scripts = self.mgr.list_scripts()
        self.assertGreater(len(scripts), 5)
        yt_script = next((sc for sc in scripts if "youtube" in sc.name.lower()), None)
        self.assertIsNotNone(yt_script)
        self.assertGreater(len(yt_script.code), 100)

    def test_diff_operations(self):
        styles_dir = Path.home() / "Projects" / "personal" / "userstyles"
        scripts_dir = Path.home() / "Projects" / "personal" / "userscripts"

        if styles_dir.exists():
            diff_styles = self.mgr.diff_styles(styles_dir)
            self.assertGreater(diff_styles["in_sync"], 0)

        if scripts_dir.exists():
            diff_scripts = self.mgr.diff_scripts(scripts_dir)
            self.assertGreater(diff_scripts["in_sync"], 0)

    def test_backup_generators(self):
        styles_dir = Path.home() / "Projects" / "personal" / "userstyles"
        scripts_dir = Path.home() / "Projects" / "personal" / "userscripts"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_out = tmp / "stylus.json"
            zip_out = tmp / "vm.zip"

            if styles_dir.exists():
                count = self.mgr.build_stylus_backup_json(styles_dir, json_out)
                self.assertGreater(count, 0)
                self.assertTrue(json_out.exists())

            if scripts_dir.exists():
                count = self.mgr.build_violentmonkey_backup_zip(scripts_dir, zip_out)
                self.assertGreater(count, 0)
                self.assertTrue(zip_out.exists())

    def test_stylus_mutations(self):
        """Tests enabling, disabling, installing, updating, and deleting Stylus styles on isolated copy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            shutil.copy2(self.mgr.profile_dir / "prefs.js", tmp / "prefs.js")
            shutil.copytree(self.mgr.profile_dir / "storage", tmp / "storage")

            tmp_mgr = ExtensionManager(profile_path=tmp)
            styles = tmp_mgr.list_styles()
            self.assertGreater(len(styles), 0)
            sample = styles[0]

            # Toggle off
            self.assertTrue(tmp_mgr.set_style_enabled(sample.id, False))
            updated = tmp_mgr.find_style(sample.id)
            self.assertIsNotNone(updated)
            self.assertFalse(updated.enabled)

            # Toggle on
            self.assertTrue(tmp_mgr.toggle_style(sample.id))
            updated = tmp_mgr.find_style(sample.id)
            self.assertTrue(updated.enabled)

            # Install new style
            test_css = tmp / "custom.user.css"
            test_css.write_text(
                "/* ==UserStyle==\n@name Unit Test Gruvbox\n@version 1.0.0\n==/UserStyle== */\n@-moz-document domain(\"unit.test\") { body { color: #ebdbb2; } }"
            )
            res = tmp_mgr.install_or_update_style(test_css, enabled=True)
            self.assertEqual(res["action"], "created")
            new_style = tmp_mgr.find_style("Unit Test Gruvbox")
            self.assertIsNotNone(new_style)
            self.assertEqual(new_style.id, res["id"])

            # Update existing style and verify Stylus Web Cache API is invalidated
            stylus_cache = tmp_mgr.get_stylus_db_path().parent.parent / "cache"
            stylus_cache.mkdir(parents=True, exist_ok=True)
            (stylus_cache / "caches.sqlite").write_text("stale-cache", encoding="utf-8")

            test_css.write_text(
                "/* ==UserStyle==\n@name Unit Test Gruvbox\n@version 2.0.0\n==/UserStyle== */\n@-moz-document domain(\"unit.test\") { body { color: #fbf1c7; } }"
            )
            res_up = tmp_mgr.install_or_update_style(test_css, enabled=False)
            self.assertEqual(res_up["action"], "updated")
            self.assertFalse(stylus_cache.exists())
            updated_style = tmp_mgr.find_style("Unit Test Gruvbox")
            self.assertFalse(updated_style.enabled)

            # Delete style
            self.assertTrue(tmp_mgr.delete_style(res["id"]))
            self.assertIsNone(tmp_mgr.find_style("Unit Test Gruvbox"))

    def test_violentmonkey_mutations(self):
        """Tests enabling, disabling, installing, updating, and deleting Violentmonkey scripts on isolated copy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            shutil.copy2(self.mgr.profile_dir / "prefs.js", tmp / "prefs.js")
            shutil.copytree(self.mgr.profile_dir / "storage", tmp / "storage")

            tmp_mgr = ExtensionManager(profile_path=tmp)
            scripts = tmp_mgr.list_scripts()
            self.assertGreater(len(scripts), 0)
            sample = scripts[0]

            # Toggle off
            self.assertTrue(tmp_mgr.set_script_enabled(sample.id, False))
            updated = tmp_mgr.find_script(sample.id)
            self.assertIsNotNone(updated)
            self.assertFalse(updated.enabled)

            # Toggle on
            self.assertTrue(tmp_mgr.toggle_script(sample.id))
            updated = tmp_mgr.find_script(sample.id)
            self.assertTrue(updated.enabled)

            # Install new script
            test_js = tmp / "custom.user.js"
            test_js.write_text(
                "// ==UserScript==\n// @name Unit Test Script\n// @version 1.0.0\n// @match *://unit.test/*\n// ==/UserScript==\nconsole.log(\"Hello test\");"
            )
            res = tmp_mgr.install_or_update_script(test_js, enabled=True)
            self.assertEqual(res["action"], "created")
            new_script = tmp_mgr.find_script("Unit Test Script")
            self.assertIsNotNone(new_script)
            self.assertIn("Hello test", new_script.code)

            # Update existing script
            test_js.write_text(
                "// ==UserScript==\n// @name Unit Test Script\n// @version 2.0.0\n// @match *://unit.test/*\n// ==/UserScript==\nconsole.log(\"Updated test\");"
            )
            res_up = tmp_mgr.install_or_update_script(test_js, enabled=False)
            self.assertEqual(res_up["action"], "updated")
            updated_script = tmp_mgr.find_script("Unit Test Script")
            self.assertFalse(updated_script.enabled)
            self.assertIn("Updated test", updated_script.code)

            # Delete script
            self.assertTrue(tmp_mgr.delete_script(res["id"]))
            self.assertIsNone(tmp_mgr.find_script("Unit Test Script"))

    def test_bulk_sync(self):
        """Tests bulk synchronization of styles and scripts on isolated profile copy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            shutil.copy2(self.mgr.profile_dir / "prefs.js", tmp / "prefs.js")
            shutil.copytree(self.mgr.profile_dir / "storage", tmp / "storage")

            tmp_mgr = ExtensionManager(profile_path=tmp)

            styles_dir = tmp / "userstyles"
            styles_dir.mkdir()
            test_css = styles_dir / "bulk_test.user.css"
            test_css.write_text(
                "/* ==UserStyle==\n@name Bulk Sync Style\n@version 1.0.0\n==/UserStyle== */\n@-moz-document domain(\"sync.test\") { body { background: #282828; } }"
            )

            scripts_dir = tmp / "userscripts"
            scripts_dir.mkdir()
            test_js = scripts_dir / "bulk_test.user.js"
            test_js.write_text(
                "// ==UserScript==\n// @name Bulk Sync Script\n// @version 1.0.0\n// @match *://sync.test/*\n// ==/UserScript==\nconsole.log(\"sync test\");"
            )

            # First run: both should be installed as new
            res = tmp_mgr.sync(styles_dir=styles_dir, scripts_dir=scripts_dir)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(res["styles"]["installed"]), 1)
            self.assertEqual(len(res["scripts"]["installed"]), 1)
            self.assertEqual(res["styles"]["installed"][0]["name"], "Bulk Sync Style")
            self.assertEqual(res["scripts"]["installed"][0]["name"], "Bulk Sync Script")

            # Second run without changes: in_sync should be 1, installed/updated 0
            res2 = tmp_mgr.sync(styles_dir=styles_dir, scripts_dir=scripts_dir)
            self.assertEqual(res2["styles"]["in_sync"], 1)
            self.assertEqual(len(res2["styles"]["installed"]), 0)
            self.assertEqual(len(res2["styles"]["updated"]), 0)
            self.assertEqual(res2["scripts"]["in_sync"], 1)
            self.assertEqual(len(res2["scripts"]["installed"]), 0)
            self.assertEqual(len(res2["scripts"]["updated"]), 0)

            # Modify both files: should be updated
            test_css.write_text(
                "/* ==UserStyle==\n@name Bulk Sync Style\n@version 2.0.0\n==/UserStyle== */\n@-moz-document domain(\"sync.test\") { body { background: #32302f; } }"
            )
            test_js.write_text(
                "// ==UserScript==\n// @name Bulk Sync Script\n// @version 2.0.0\n// @match *://sync.test/*\n// ==/UserScript==\nconsole.log(\"updated sync test\");"
            )
            res3 = tmp_mgr.sync(styles_dir=styles_dir, scripts_dir=scripts_dir)
            self.assertEqual(len(res3["styles"]["updated"]), 1)
            self.assertEqual(len(res3["scripts"]["updated"]), 1)
            self.assertEqual(res3["styles"]["updated"][0]["name"], "Bulk Sync Style")
            self.assertEqual(res3["scripts"]["updated"][0]["name"], "Bulk Sync Script")


if __name__ == "__main__":
    unittest.main()
