import unittest
from browser_toolkit.session_client import (
    is_session_alive,
    send_session_command,
    start_session,
    stop_session,
)


class TestSessionLifecycle(unittest.TestCase):
    def tearDown(self):
        stop_session()

    def test_session_lifecycle_and_commands(self):
        # Ensure clean state
        stop_session()
        self.assertFalse(is_session_alive())

        # Start session on about:blank with no_profile to be fast
        status = start_session(url="about:blank", no_profile=True, wait_timeout=15.0)
        self.assertEqual(status.get("status"), "ok")
        self.assertTrue(is_session_alive())

        # Status check
        live_status = send_session_command({"action": "status"})
        self.assertEqual(live_status.get("status"), "ok")
        self.assertEqual(live_status.get("url"), "about:blank")

        # Eval
        eval_res = send_session_command({"action": "eval", "script": "10 + 25"})
        self.assertEqual(eval_res.get("result"), 35)

        # Eval many
        batch_res = send_session_command({
            "action": "eval_many",
            "scripts": {"s1": "'hello'.toUpperCase()", "s2": "3 * 7"},
        })
        self.assertEqual(batch_res.get("results"), {"s1": "HELLO", "s2": 21})

        # Interact
        interact_res = send_session_command({
            "action": "interact",
            "actions": [{"action": "wait", "ms": 50}],
        })
        self.assertEqual(interact_res.get("status"), "ok")
        self.assertEqual(len(interact_res.get("results", [])), 1)

        # Stop
        stop_res = stop_session()
        self.assertEqual(stop_res.get("status"), "ok")
        self.assertFalse(is_session_alive())
