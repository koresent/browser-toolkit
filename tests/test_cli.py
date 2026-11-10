import unittest

from browser_toolkit.cli import build_parser


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_audit_subcommand_args(self):
        args = self.parser.parse_args(["audit", "style.user.css", "--url", "https://habr.com", "--deep-hunt", "--json"])
        self.assertEqual(args.command, "audit")
        self.assertEqual(args.file, "style.user.css")
        self.assertEqual(args.url, "https://habr.com")
        self.assertTrue(args.deep_hunt)
        self.assertTrue(args.json)

    def test_scan_subcommand_args(self):
        args = self.parser.parse_args(["scan", "/path/to/styles", "--only-broken"])
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.dir, "/path/to/styles")
        self.assertTrue(args.only_broken)

    def test_search_subcommand_args(self):
        args = self.parser.parse_args(["search", "https://github.com", "--keyword", "copilot", "--tag", "button"])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.url, "https://github.com")
        self.assertEqual(args.keyword, "copilot")
        self.assertEqual(args.tag, "button")

    def test_test_rule_subcommand_args(self):
        args = self.parser.parse_args(["test-rule", "https://example.com", "--css", "h1 { color: red; }"])
        self.assertEqual(args.command, "test-rule")
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.css, "h1 { color: red; }")

    def test_check_responsive_subcommand_args(self):
        args = self.parser.parse_args(["check-responsive", "https://example.com", "--screenshots-dir", "./shots"])
        self.assertEqual(args.command, "check-responsive")
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.screenshots_dir, "./shots")

    def test_check_theme_subcommand_args(self):
        args = self.parser.parse_args(["check-theme", "https://example.com", "--theme", "dark", "--css", "style.css"])
        self.assertEqual(args.command, "check-theme")
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.theme, "dark")
        self.assertEqual(args.css, "style.css")

    def test_ext_subcommands_args(self):
        # ext status
        args = self.parser.parse_args(["ext", "status", "--json"])
        self.assertEqual(args.command, "ext")
        self.assertEqual(args.ext_action, "status")
        self.assertTrue(args.json)

        # ext list-styles
        args = self.parser.parse_args(["ext", "list-styles", "--search", "habr"])
        self.assertEqual(args.ext_action, "list-styles")
        self.assertEqual(args.search, "habr")

        # ext enable-style
        args = self.parser.parse_args(["ext", "enable-style", "Habr Dark"])
        self.assertEqual(args.ext_action, "enable-style")
        self.assertEqual(args.target, "Habr Dark")

        # ext install-style
        args = self.parser.parse_args(["ext", "install-style", "habr.user.css", "--disabled"])
        self.assertEqual(args.ext_action, "install-style")
        self.assertEqual(args.file, "habr.user.css")
        self.assertTrue(args.disabled)

        # ext toggle-script
        args = self.parser.parse_args(["ext", "toggle-script", "15"])
        self.assertEqual(args.ext_action, "toggle-script")
        self.assertEqual(args.target, "15")

        # ext backup
        args = self.parser.parse_args(["ext", "backup", "--out-stylus", "custom-stylus.json"])
        self.assertEqual(args.ext_action, "backup")
        self.assertEqual(args.out_stylus, "custom-stylus.json")


if __name__ == "__main__":
    unittest.main()
