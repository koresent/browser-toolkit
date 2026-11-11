import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from browser_toolkit.browser_backend import (
    ensure_playwright_browser,
    safe_launch_browser,
    safe_launch_persistent_context,
)


class TestBrowserBackend(unittest.TestCase):
    def test_ensure_browser_when_exists(self):
        mock_playwright = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser_type.executable_path = str(Path(__file__).resolve())
        mock_playwright.firefox = mock_browser_type

        with patch("subprocess.run") as mock_run:
            ensure_playwright_browser(mock_playwright, "firefox")
            mock_run.assert_not_called()

    def test_ensure_browser_missing_triggers_install(self):
        mock_playwright = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser_type.executable_path = "/nonexistent/path/firefox"
        mock_playwright.firefox = mock_browser_type

        with patch("subprocess.run") as mock_run:
            ensure_playwright_browser(mock_playwright, "firefox")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("playwright", args)
            self.assertIn("install", args)
            self.assertIn("firefox", args)

    def test_ensure_browser_install_failure_raises(self):
        mock_playwright = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser_type.executable_path = "/nonexistent/path/firefox"
        mock_playwright.firefox = mock_browser_type

        with patch("subprocess.run", side_effect=Exception("network down")):
            with self.assertRaises(RuntimeError):
                ensure_playwright_browser(mock_playwright, "firefox")

    def test_safe_launch_browser_recovers_on_executable_missing(self):
        mock_playwright = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser_type.executable_path = str(Path(__file__).resolve())

        mock_browser_instance = MagicMock()
        mock_browser_type.launch.side_effect = [
            Exception("BrowserType.launch: Executable doesn't exist at /fake/path"),
            mock_browser_instance,
        ]
        mock_playwright.firefox = mock_browser_type

        with patch("subprocess.run") as mock_run:
            res = safe_launch_browser(mock_playwright, "firefox", headless=True)
            self.assertEqual(res, mock_browser_instance)
            mock_run.assert_called_once()

    def test_safe_launch_persistent_context_recovers_on_executable_missing(self):
        mock_playwright = MagicMock()
        mock_browser_type = MagicMock()
        mock_browser_type.executable_path = str(Path(__file__).resolve())

        mock_context_instance = MagicMock()
        mock_browser_type.launch_persistent_context.side_effect = [
            Exception("Executable doesn't exist at /fake/path"),
            mock_context_instance,
        ]
        mock_playwright.firefox = mock_browser_type

        with patch("subprocess.run") as mock_run:
            res = safe_launch_persistent_context(mock_playwright, "/tmp/user_data", "firefox")
            self.assertEqual(res, mock_context_instance)
            mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
