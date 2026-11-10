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
        styles_dir = Path("/home/koresent/Projects/personal/userstyles")
        scripts_dir = Path("/home/koresent/Projects/personal/userscripts")

        if styles_dir.exists():
            diff_styles = self.mgr.diff_styles(styles_dir)
            self.assertGreater(diff_styles["in_sync"], 0)

        if scripts_dir.exists():
            diff_scripts = self.mgr.diff_scripts(scripts_dir)
            self.assertGreater(diff_scripts["in_sync"], 0)

    def test_backup_generators(self):
        styles_dir = Path("/home/koresent/Projects/personal/userstyles")
        scripts_dir = Path("/home/koresent/Projects/personal/userscripts")

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


if __name__ == "__main__":
    unittest.main()
