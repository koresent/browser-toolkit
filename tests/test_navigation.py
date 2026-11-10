import unittest
from unittest.mock import MagicMock
from browser_toolkit.navigation import safe_goto


class TestSafeGoto(unittest.TestCase):
    def test_safe_goto_success(self):
        page = MagicMock()
        mock_response = MagicMock()
        page.goto.return_value = mock_response

        res = safe_goto(page, "https://example.com")
        page.goto.assert_called_once_with(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        self.assertEqual(res, mock_response)

    def test_safe_goto_handles_ns_binding_aborted(self):
        page = MagicMock()
        page.goto.side_effect = Exception("Page.goto: NS_BINDING_ABORTED")

        res = safe_goto(page, "https://chatgpt.com")
        self.assertIsNone(res)
        page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=15000)

    def test_safe_goto_handles_net_err_aborted(self):
        page = MagicMock()
        page.goto.side_effect = Exception("net::ERR_ABORTED")

        res = safe_goto(page, "https://chatgpt.com")
        self.assertIsNone(res)
        page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=15000)

    def test_safe_goto_raises_other_errors(self):
        page = MagicMock()
        page.goto.side_effect = ValueError("Fatal protocol error")

        with self.assertRaises(ValueError):
            safe_goto(page, "https://example.com")


if __name__ == "__main__":
    unittest.main()
