import unittest

from browser_toolkit.cli import build_parser


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def test_audit_subcommand_args(self):
        args = self.parser.parse_args(["audit", "style.user.css", "--url", "https://habr.com", "--deep-hunt", "--toon"])
        self.assertEqual(args.command, "audit")
        self.assertEqual(args.file, "style.user.css")
        self.assertEqual(args.url, "https://habr.com")
        self.assertTrue(args.deep_hunt)
        self.assertTrue(args.toon)

        args_json = self.parser.parse_args(["audit", "style.user.css", "--json"])
        self.assertTrue(args_json.json)

    def test_scan_subcommand_args(self):
        args = self.parser.parse_args(["scan", "/path/to/styles", "--only-broken"])
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.dir, "/path/to/styles")
        self.assertTrue(args.only_broken)

    def test_search_subcommand_args(self):
        args = self.parser.parse_args([
            "search", "https://github.com",
            "--keyword", "copilot",
            "--tag", "button",
            "--wait", ".chatlist-chat",
            "--actions", '[{"action": "wait", "ms": 500}]',
        ])
        self.assertEqual(args.command, "search")
        self.assertEqual(args.url, "https://github.com")
        self.assertEqual(args.keyword, "copilot")
        self.assertEqual(args.tag, "button")
        self.assertEqual(args.wait, ".chatlist-chat")
        self.assertEqual(args.actions, '[{"action": "wait", "ms": 500}]')

    def test_inspect_subcommand_args(self):
        args = self.parser.parse_args([
            "inspect", "https://example.com",
            "--selector", ".bubble.is-out",
            "--rules",
            "--properties", "color,border-radius",
            "--css", ".bubble { border-radius: 10px; }",
            "--pseudo", "::after",
            "--actions", '[{"action": "click", "selector": ".chat"}]',
        ])
        self.assertEqual(args.command, "inspect")
        self.assertEqual(args.url, "https://example.com")
        self.assertEqual(args.selector, ".bubble.is-out")
        self.assertTrue(args.rules)
        self.assertEqual(args.properties, "color,border-radius")
        self.assertEqual(args.css, ".bubble { border-radius: 10px; }")
        self.assertEqual(args.pseudo, "::after")
        self.assertIn("click", args.actions)

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
        args = self.parser.parse_args(["ext", "status", "--toon"])
        self.assertEqual(args.command, "ext")
        self.assertEqual(args.ext_action, "status")
        self.assertTrue(args.toon)

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

    def test_config_subcommand_args(self):
        args1 = self.parser.parse_args(["config", "--set-format", "toon"])
        self.assertEqual(args1.command, "config")
        self.assertEqual(args1.set_format, "toon")

        args2 = self.parser.parse_args(["config", "format", "json"])
        self.assertEqual(args2.command, "config")
        self.assertEqual(args2.key, "format")
        self.assertEqual(args2.value, "json")

    def test_session_subcommand_args(self):
        args_list = self.parser.parse_args(["session", "list", "--toon"])
        self.assertEqual(args_list.command, "session")
        self.assertEqual(args_list.session_command, "list")
        self.assertTrue(args_list.toon)

        args_start = self.parser.parse_args(["session", "start", "https://example.com", "--name", "worker_1", "--no-profile", "--toon"])
        self.assertEqual(args_start.command, "session")
        self.assertEqual(args_start.session_command, "start")
        self.assertEqual(args_start.url, "https://example.com")
        self.assertEqual(args_start.name, "worker_1")
        self.assertTrue(args_start.no_profile)
        self.assertTrue(args_start.toon)

        args_status = self.parser.parse_args(["session", "status", "--name", "worker_1"])
        self.assertEqual(args_status.session_command, "status")
        self.assertEqual(args_status.name, "worker_1")

        args_goto = self.parser.parse_args(["session", "goto", "https://example.com/login"])
        self.assertEqual(args_goto.session_command, "goto")
        self.assertEqual(args_goto.url, "https://example.com/login")

        args_eval = self.parser.parse_args(["session", "eval", "document.title"])
        self.assertEqual(args_eval.session_command, "eval")
        self.assertEqual(args_eval.script, "document.title")

        args_eval_many = self.parser.parse_args(["session", "eval-many", '{"a": "1"}'])
        self.assertEqual(args_eval_many.session_command, "eval-many")
        self.assertEqual(args_eval_many.scripts, '{"a": "1"}')

        args_interact = self.parser.parse_args(["session", "interact", "--actions", '[{"action": "wait", "ms": 100}]'])
        self.assertEqual(args_interact.session_command, "interact")
        self.assertEqual(args_interact.actions, '[{"action": "wait", "ms": 100}]')

        args_shot = self.parser.parse_args(["session", "screenshot", "--selector", "#main", "--full-page"])
        self.assertEqual(args_shot.session_command, "screenshot")
        self.assertEqual(args_shot.selector, "#main")
        self.assertTrue(args_shot.full_page)

        args_stop = self.parser.parse_args(["session", "stop"])
        self.assertEqual(args_stop.session_command, "stop")

        args_eval_file = self.parser.parse_args(["session", "eval", "--file", "probe.js", "--name", "s1"])
        self.assertEqual(args_eval_file.session_command, "eval")
        self.assertEqual(args_eval_file.file, "probe.js")
        self.assertEqual(args_eval_file.name, "s1")

        args_s_inspect = self.parser.parse_args(["session", "inspect", "--selector", ".avatar", "--rules", "--pseudo", "::after", "--name", "tg"])
        self.assertEqual(args_s_inspect.session_command, "inspect")
        self.assertEqual(args_s_inspect.selector, ".avatar")
        self.assertTrue(args_s_inspect.rules)
        self.assertEqual(args_s_inspect.pseudo, "::after")

        args_s_search = self.parser.parse_args(["session", "search", "--text", "Login", "--tag", "button", "--name", "tg"])
        self.assertEqual(args_s_search.session_command, "search")
        self.assertEqual(args_s_search.text, "Login")
        self.assertEqual(args_s_search.tag, "button")

        args_inj_css = self.parser.parse_args(["session", "inject-css", "theme.user.css", "--name", "tg"])
        self.assertEqual(args_inj_css.session_command, "inject-css")
        self.assertEqual(args_inj_css.css, "theme.user.css")

        args_inj_js = self.parser.parse_args(["session", "inject-script", "script.user.js", "--settle-ms", "200"])
        self.assertEqual(args_inj_js.session_command, "inject-script")
        self.assertEqual(args_inj_js.file, "script.user.js")
        self.assertEqual(args_inj_js.settle_ms, 200)

        args_frames = self.parser.parse_args(["session", "frames", "--name", "gg"])
        self.assertEqual(args_frames.session_command, "frames")
        self.assertEqual(args_frames.name, "gg")

        args_s_clean = self.parser.parse_args(["session", "start", "https://www.google.com", "--clean-styles", "--name", "gg"])
        self.assertEqual(args_s_clean.session_command, "start")
        self.assertTrue(args_s_clean.clean_styles)

        args_frame_eval = self.parser.parse_args(["session", "eval", "document.title", "--frame", "account"])
        self.assertEqual(args_frame_eval.frame, "account")

        args_s_theme = self.parser.parse_args(["session", "check-theme", "--theme", "dark", "--exclude-colors", "#282828,#3c3836", "--frame", "account"])
        self.assertEqual(args_s_theme.session_command, "check-theme")
        self.assertEqual(args_s_theme.exclude_colors, "#282828,#3c3836")
        self.assertEqual(args_s_theme.frame, "account")

        args_theme_clean = self.parser.parse_args(["check-theme", "https://www.google.com", "--clean-styles", "--exclude-colors", "#282828"])
        self.assertTrue(args_theme_clean.clean_styles)
        self.assertEqual(args_theme_clean.exclude_colors, "#282828")

    def test_profile_info_args(self):
        args = self.parser.parse_args(["profile-info", "--toon"])
        self.assertEqual(args.command, "profile-info")
        self.assertTrue(args.toon)

        args_root = self.parser.parse_args(["--toon", "profile-info"])
        self.assertEqual(args_root.command, "profile-info")
        self.assertTrue(args_root.toon)


if __name__ == "__main__":
    unittest.main()
