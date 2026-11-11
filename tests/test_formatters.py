import os
import unittest
from unittest.mock import patch

from browser_toolkit.formatters import dump_data, resolve_format, output_result, to_toon
from browser_toolkit.cli import build_parser


class DummyArgs:
    def __init__(self, json=False, toon=False, format=None):
        self.json = json
        self.toon = toon
        self.format = format


class TestFormatters(unittest.TestCase):
    def setUp(self):
        self.sample_data = {
            "type": "userstyle",
            "name": "Test Style",
            "matched_count": 42,
            "items": [
                {"id": 1, "selector": ".header"},
                {"id": 2, "selector": ".footer"},
            ],
        }

    def test_dump_toon_format(self):
        rendered = dump_data(self.sample_data, fmt="toon")
        self.assertIn("type: userstyle", rendered)
        self.assertIn("items[2]{id,selector}:", rendered)
        self.assertIn("1,.header", rendered)

    def test_to_toon_helper(self):
        rendered = to_toon(self.sample_data)
        self.assertIn("type: userstyle", rendered)
        self.assertIn("items[2]{id,selector}:", rendered)

    def test_dump_compact_json(self):
        rendered = dump_data(self.sample_data, fmt="json")
        self.assertNotIn("\n", rendered)
        self.assertIn('"type":"userstyle"', rendered)

    def test_dump_pretty_json(self):
        rendered = dump_data(self.sample_data, fmt="json-pretty")
        self.assertIn("\n", rendered)
        self.assertIn('  "type": "userstyle"', rendered)

    def test_resolve_format_flags(self):
        self.assertEqual(resolve_format(DummyArgs(toon=True)), "toon")
        self.assertEqual(resolve_format(DummyArgs(json=True)), "json")
        self.assertEqual(resolve_format(DummyArgs(format="toon")), "toon")
        self.assertEqual(resolve_format(DummyArgs(format="json-pretty")), "json-pretty")
        self.assertEqual(resolve_format(DummyArgs()), "text")

    def test_resolve_format_env_var(self):
        with patch.dict(os.environ, {"BROWSER_TOOLKIT_FORMAT": "toon"}):
            self.assertEqual(resolve_format(DummyArgs()), "toon")

        with patch.dict(os.environ, {"BROWSER_TOOLKIT_FORMAT": "json"}):
            self.assertEqual(resolve_format(DummyArgs()), "json")

    def test_cli_parser_toon_and_format_options(self):
        parser = build_parser()
        args1 = parser.parse_args(["audit", "test.user.css", "--toon"])
        self.assertTrue(args1.toon)

        args2 = parser.parse_args(["audit", "test.user.css", "--format", "toon"])
        self.assertEqual(args2.format, "toon")

        args3 = parser.parse_args(["ext", "status", "--toon"])
        self.assertTrue(args3.toon)
