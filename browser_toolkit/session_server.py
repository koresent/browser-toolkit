import argparse
import json
import os
import select
import signal
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright

from .browser_backend import safe_launch_browser, safe_launch_persistent_context
from .interaction import PageInteractor, execute_action_sequence
from .navigation import safe_goto
from .profile import ZenProfileContext

SOCKET_PATH = Path(tempfile.gettempdir()) / "browser-toolkit" / "session.sock"
PID_PATH = Path(tempfile.gettempdir()) / "browser-toolkit" / "session.pid"
DEFAULT_IDLE_TIMEOUT = 900.0  # 15 minutes


class SessionServer:
    def __init__(
        self,
        profile_path: Optional[str] = None,
        use_profile: bool = True,
        headless: bool = True,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    ):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.headless = headless
        self.idle_timeout = idle_timeout
        self.start_time = time.time()
        self.last_activity = time.time()
        self.running = False
        self.server_sock: Optional[socket.socket] = None

    def _cleanup_paths(self) -> None:
        try:
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()
        except OSError:
            pass
        try:
            if PID_PATH.exists():
                PID_PATH.unlink()
        except OSError:
            pass

    def run(self, initial_url: Optional[str] = None) -> None:
        self._cleanup_paths()
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

        def handle_signal(signum: int, frame: Any) -> None:
            self.running = False

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                vp = {"width": 1440, "height": 900}
                if temp_profile:
                    context = safe_launch_persistent_context(
                        p,
                        user_data_dir=str(temp_profile),
                        viewport=vp,
                        headless=self.headless,
                        bypass_csp=True,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = safe_launch_browser(p, headless=self.headless)
                    context = browser.new_context(viewport=vp, bypass_csp=True)
                    page = context.new_page()

                if initial_url:
                    safe_goto(page, initial_url)

                self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.server_sock.bind(str(SOCKET_PATH))
                self.server_sock.listen(5)
                self.server_sock.setblocking(False)
                self.running = True

                try:
                    while self.running:
                        # Check idle timeout
                        if time.time() - self.last_activity > self.idle_timeout:
                            break

                        readable, _, _ = select.select([self.server_sock], [], [], 1.0)
                        if not readable:
                            continue

                        conn, _ = self.server_sock.accept()
                        self.last_activity = time.time()
                        self._handle_client(conn, page, context)
                finally:
                    if self.server_sock:
                        try:
                            self.server_sock.close()
                        except OSError:
                            pass
                    self._cleanup_paths()
                    try:
                        context.close()
                    except Exception:
                        pass

    def _handle_client(self, conn: socket.socket, page: Any, context: Any) -> None:
        conn.settimeout(30.0)
        try:
            with conn:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk

                if not buf:
                    return

                line = buf.decode("utf-8").strip()
                if not line:
                    return

                req = json.loads(line)
                action = req.get("action", "")
                response = self._process_command(action, req, page, context)
                conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except Exception as e:
            try:
                err_resp = {"status": "error", "message": str(e)}
                conn.sendall(json.dumps(err_resp).encode("utf-8") + b"\n")
            except OSError:
                pass

    def _process_command(
        self,
        action: str,
        req: Dict[str, Any],
        page: Any,
        context: Any,
    ) -> Dict[str, Any]:
        if action == "ping":
            return {"status": "ok", "message": "pong"}

        if action == "status":
            now = time.time()
            return {
                "status": "ok",
                "url": page.url,
                "title": page.title() if page.url != "about:blank" else "",
                "uptime_seconds": round(now - self.start_time, 1),
                "idle_seconds": round(now - self.last_activity, 1),
            }

        if action == "goto":
            url = req.get("url", "")
            if not url:
                return {"status": "error", "message": "Missing 'url' parameter"}
            safe_goto(page, url)
            return {
                "status": "ok",
                "url": page.url,
                "title": page.title(),
            }

        if action == "eval":
            script = req.get("script", "")
            interactor = PageInteractor(page)
            res = interactor.evaluate(script)
            return {"status": "ok", "result": res}

        if action == "eval_many":
            scripts = req.get("scripts", {})
            interactor = PageInteractor(page)
            res = interactor.evaluate_many(scripts)
            return {"status": "ok", "results": res}

        if action == "interact":
            actions = req.get("actions", [])
            results = execute_action_sequence(page, actions)
            return {"status": "ok", "results": results}

        if action == "screenshot":
            out_path = req.get("output") or str(Path(tempfile.gettempdir()) / "browser-toolkit" / "session_screenshot.png")
            selector = req.get("selector")
            full_page = bool(req.get("full_page", False))
            interactor = PageInteractor(page)
            saved = interactor.capture_screenshot(out_path, selector=selector, full_page=full_page)
            return {"status": "ok", "saved_to": str(saved)}

        if action == "stop":
            self.running = False
            return {"status": "ok", "message": "Session stopped"}

        return {"status": "error", "message": f"Unknown action: {action}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent Playwright browser session daemon")
    parser.add_argument("--url", help="Initial URL to navigate")
    parser.add_argument("--profile", help="Path to custom profile")
    parser.add_argument("--no-profile", action="store_true", help="Do not use profile clone")
    parser.add_argument("--headful", action="store_true", help="Run with visible window")
    parser.add_argument("--timeout", type=float, default=DEFAULT_IDLE_TIMEOUT, help="Idle timeout seconds")
    args = parser.parse_args()

    server = SessionServer(
        profile_path=args.profile,
        use_profile=not args.no_profile,
        headless=not args.headful,
        idle_timeout=args.timeout,
    )
    server.run(initial_url=args.url)


if __name__ == "__main__":
    main()
