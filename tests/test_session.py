import unittest
from browser_toolkit.session_client import (
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
