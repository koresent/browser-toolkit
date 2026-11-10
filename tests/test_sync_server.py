import http.client
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from browser_toolkit.extension_manager import ExtensionManager
from browser_toolkit.sync_server import ExtensionSyncHandler


class TestSyncServer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_dir.name)

        # Create sample userstyle
        self.styles_dir = self.tmp / "styles"
        self.styles_dir.mkdir()
        self.sample_css = self.styles_dir / "sample.user.css"
        self.sample_css.write_text("/* ==UserStyle==\n@name Test Style\n==/UserStyle== */\nbody { color: red; }")

        # Create sample userscript
        self.scripts_dir = self.tmp / "scripts"
        self.scripts_dir.mkdir()
        self.sample_js = self.scripts_dir / "sample.user.js"
        self.sample_js.write_text("// ==UserScript==\n// @name Test Script\n// ==/UserScript==\nconsole.log(1);")

        class CustomHandler(ExtensionSyncHandler):
            styles_dir = self.styles_dir
            scripts_dir = self.scripts_dir
            ext_manager = ExtensionManager()

        # Bind to port 0 (ephemeral OS assigned port)
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), CustomHandler)
        self.port = self.httpd.server_address[1]

        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp_dir.cleanup()

    def test_dashboard_endpoint(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("Extension Hub", body)
        self.assertIn("Test Style", body)
        self.assertIn("Test Script", body)
        conn.close()

    def test_serve_style_and_script_files(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

        # Test style endpoint
        conn.request("GET", "/styles/sample.user.css")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/css", resp.getheader("Content-Type", ""))
        body = resp.read().decode("utf-8")
        self.assertIn("body { color: red; }", body)

        # Test script endpoint
        conn.request("GET", "/scripts/sample.user.js")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("javascript", resp.getheader("Content-Type", ""))
        body = resp.read().decode("utf-8")
        self.assertIn("console.log(1);", body)

        conn.close()

    def test_backup_and_status_endpoints(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

        # Test API status endpoint
        conn.request("GET", "/api/status")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("application/json", resp.getheader("Content-Type", ""))
        body = resp.read().decode("utf-8")
        self.assertIn("styles_count", body)

        # Test 404 for unknown path
        conn.request("GET", "/unknown-route")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)

        conn.close()


if __name__ == "__main__":
    unittest.main()
