import re
import unittest
from browser_toolkit.session_client import (
    generate_session_name,
    is_session_alive,
    list_active_sessions,
    send_session_command,
    start_session,
    stop_session,
)


class TestSessionLifecycle(unittest.TestCase):
    def tearDown(self):
        stop_session("default")
        stop_session("test_a")
        stop_session("test_b")
        stop_session("test_guard")
        stop_session("test_info")

    def test_session_lifecycle_and_commands(self):
        # Ensure clean state
        stop_session("default")
        self.assertFalse(is_session_alive("default"))

        # Start session on about:blank with no_profile to be fast
        status = start_session(url="about:blank", session_name="default", no_profile=True, wait_timeout=15.0)
        self.assertEqual(status.get("status"), "ok")
        self.assertTrue(is_session_alive("default"))

        # Status check
        live_status = send_session_command({"action": "status"}, session_name="default")
        self.assertEqual(live_status.get("status"), "ok")
        self.assertEqual(live_status.get("url"), "about:blank")

        # Eval
        eval_res = send_session_command({"action": "eval", "script": "10 + 25"}, session_name="default")
        self.assertEqual(eval_res.get("result"), 35)

        # Eval many
        batch_res = send_session_command({
            "action": "eval_many",
            "scripts": {"s1": "'hello'.toUpperCase()", "s2": "3 * 7"},
        }, session_name="default")
        self.assertEqual(batch_res.get("results"), {"s1": "HELLO", "s2": 21})

        # Interact
        interact_res = send_session_command({
            "action": "interact",
            "actions": [{"action": "wait", "ms": 50}],
        }, session_name="default")
        self.assertEqual(interact_res.get("status"), "ok")
        self.assertEqual(len(interact_res.get("results", [])), 1)

        # Inject CSS + Inspect + Search + Inject Script
        css_res = send_session_command({
            "action": "inject_css",
            "css": "body { background-color: rgb(18, 52, 86); }",
        }, session_name="default")
        self.assertEqual(css_res.get("status"), "ok")

        script_res = send_session_command({
            "action": "inject_script",
            "raw_js": "const d = document.createElement('div'); d.id = 'sess-injected'; d.textContent = 'Session Widget'; document.body.appendChild(d);",
            "settle_ms": 100,
        }, session_name="default")
        self.assertEqual(script_res.get("status"), "ok")
        self.assertTrue(script_res.get("executed"))

        inspect_res = send_session_command({
            "action": "inspect",
            "selector": "#sess-injected",
            "rules": True,
        }, session_name="default")
        self.assertEqual(inspect_res.get("status"), "ok")
        self.assertEqual(inspect_res.get("result", {}).get("count"), 1)

        search_res = send_session_command({
            "action": "search",
            "text": "Session Widget",
        }, session_name="default")
        self.assertEqual(search_res.get("status"), "ok")
        self.assertGreaterEqual(search_res.get("matches_count", 0), 1)

        # Create a child iframe with name='widget' and test frame listing + targeted frame actions
        send_session_command({
            "action": "eval",
            "script": """
            (() => {
                const fr = document.createElement('iframe');
                fr.name = 'widget';
                fr.srcdoc = '<!DOCTYPE html><html><body style="background:#ffffff"><div id="inner-card" style="background:#202124;color:#ebdbb2">Widget Frame</div></body></html>';
                document.body.appendChild(fr);
                return true;
            })()
            """,
        }, session_name="default")
        send_session_command({
            "action": "interact",
            "actions": [{"action": "wait", "ms": 200}],
        }, session_name="default")

        frames_res = send_session_command({"action": "frames"}, session_name="default")
        self.assertEqual(frames_res.get("status"), "ok")
        frame_names = [f.get("name") for f in frames_res.get("frames", [])]
        self.assertIn("widget", frame_names)

        frame_eval = send_session_command({
            "action": "eval",
            "frame": "widget",
            "script": "document.getElementById('inner-card').textContent",
        }, session_name="default")
        self.assertEqual(frame_eval.get("status"), "ok")
        self.assertEqual(frame_eval.get("result"), "Widget Frame")

        frame_inspect = send_session_command({
            "action": "inspect",
            "frame": "widget",
            "selector": "#inner-card",
        }, session_name="default")
        self.assertEqual(frame_inspect.get("status"), "ok")
        self.assertEqual(frame_inspect.get("result", {}).get("count"), 1)

        frame_theme = send_session_command({
            "action": "check_theme",
            "frame": "widget",
            "theme": "dark",
            "exclude_colors": ["#282828"],
        }, session_name="default")
        self.assertEqual(frame_theme.get("status"), "ok")
        surface_colors = {s["color"] for s in frame_theme.get("dominant_surfaces", [])}
        self.assertIn("rgb(32, 33, 36)", surface_colors)

        # Stop
        stop_res = stop_session("default")
        self.assertEqual(stop_res.get("status"), "ok")
        self.assertFalse(is_session_alive("default"))

    def test_concurrent_named_sessions(self):
        stop_session("test_a")
        stop_session("test_b")

        s1 = start_session(url="about:blank", session_name="test_a", no_profile=True, wait_timeout=15.0)
        s2 = start_session(url="about:blank", session_name="test_b", no_profile=True, wait_timeout=15.0)

        self.assertEqual(s1.get("session_name"), "test_a")
        self.assertEqual(s2.get("session_name"), "test_b")

        active = list_active_sessions()
        names = {item.get("session_name") for item in active}
        self.assertIn("test_a", names)
        self.assertIn("test_b", names)

        # Independent evaluations
        r1 = send_session_command({"action": "eval", "script": "'agent_1_eval'"}, session_name="test_a")
        r2 = send_session_command({"action": "eval", "script": "'agent_2_eval'"}, session_name="test_b")
        self.assertEqual(r1.get("result"), "agent_1_eval")
        self.assertEqual(r2.get("result"), "agent_2_eval")

        stop_session("test_a")
        stop_session("test_b")
        self.assertFalse(is_session_alive("test_a"))
        self.assertFalse(is_session_alive("test_b"))

    def test_generate_session_name(self):
        name1 = generate_session_name()
        name2 = generate_session_name()
        self.assertTrue(re.match(r"^sess-[0-9a-f]{8}$", name1))
        self.assertTrue(re.match(r"^sess-[0-9a-f]{8}$", name2))
        self.assertNotEqual(name1, name2)

    def test_anti_hijack_guard_and_force(self):
        stop_session("test_guard")
        s = start_session(url="about:blank", session_name="test_guard", no_profile=True, wait_timeout=15.0)
        self.assertEqual(s.get("session_name"), "test_guard")

        # Navigate to first page
        send_session_command({"action": "goto", "url": "data:text/html,<h1>Page1</h1>"}, session_name="test_guard")

        # Attempting start_session to another URL without force must fail
        with self.assertRaises(RuntimeError) as ctx:
            start_session(url="data:text/html,<h1>Page2</h1>", session_name="test_guard")
        self.assertIn("already active on", str(ctx.exception))
        self.assertIn("Refusing to hijack", str(ctx.exception))

        # With force=True, navigation succeeds
        forced = start_session(url="data:text/html,<h1>Page2</h1>", session_name="test_guard", force=True)
        self.assertEqual(forced.get("status"), "ok")

        stop_session("test_guard")
        self.assertFalse(is_session_alive("test_guard"))

    def test_random_session_start(self):
        s = start_session(url="about:blank", random_name=True, no_profile=True, wait_timeout=15.0)
        name = s.get("session_name", "")
        try:
            self.assertTrue(name.startswith("sess-"))
            self.assertTrue(is_session_alive(name))
        finally:
            stop_session(name)

    def test_missing_session_error_lists_active(self):
        stop_session("test_info")
        start_session(url="about:blank", session_name="test_info", no_profile=True, wait_timeout=15.0)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                send_session_command({"action": "status"}, session_name="nonexistent_sess")
            self.assertIn("test_info", str(ctx.exception))
            self.assertIn("Active sessions found", str(ctx.exception))
        finally:
            stop_session("test_info")
