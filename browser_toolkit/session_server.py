import argparse
import json
import os
import re
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
from .inspector import inject_css_or_file, inspect_page_selector
from .interaction import PageInteractor, execute_action_sequence
from .js_auditor import inject_userscript
from .navigation import safe_goto
from .parser import parse_userscript
from .profile import ZenProfileContext
from .search import search_dom

DEFAULT_IDLE_TIMEOUT = 900.0  # 15 minutes


def get_session_socket_path(session_name: str = "default") -> Path:
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", (session_name or "default").strip())
    if not clean or clean == "default":
        return Path(tempfile.gettempdir()) / "browser-toolkit" / "session.sock"
    return Path(tempfile.gettempdir()) / "browser-toolkit" / f"session_{clean}.sock"


def get_session_pid_path(session_name: str = "default") -> Path:
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", (session_name or "default").strip())
    if not clean or clean == "default":
        return Path(tempfile.gettempdir()) / "browser-toolkit" / "session.pid"
    return Path(tempfile.gettempdir()) / "browser-toolkit" / f"session_{clean}.pid"


class SessionServer:
    def __init__(
        self,
        session_name: str = "default",
        profile_path: Optional[str] = None,
        use_profile: bool = True,
        headless: bool = True,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
    ):
        self.session_name = (session_name or "default").strip()
        self.socket_path = get_session_socket_path(self.session_name)
        self.pid_path = get_session_pid_path(self.session_name)
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
            if self.socket_path.exists():
                self.socket_path.unlink()
        except OSError:
            pass
        try:
            if self.pid_path.exists():
                self.pid_path.unlink()
        except OSError:
            pass

    def run(self, initial_url: Optional[str] = None) -> None:
        self._cleanup_paths()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.pid_path.write_text(str(os.getpid()), encoding="utf-8")

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
                self.server_sock.bind(str(self.socket_path))
                self.server_sock.listen(5)
                self.server_sock.setblocking(False)
                self.running = True

                try:
                    while self.running:
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
            return {"status": "ok", "message": "pong", "session_name": self.session_name}

        if action == "status":
            now = time.time()
            return {
                "status": "ok",
                "session_name": self.session_name,
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
                "session_name": self.session_name,
                "url": page.url,
                "title": page.title(),
            }

        if action == "eval":
            script = req.get("script", "")
            interactor = PageInteractor(page)
            res = interactor.evaluate(script)
            return {"status": "ok", "session_name": self.session_name, "result": res}

        if action == "eval_many":
            scripts = req.get("scripts", {})
            interactor = PageInteractor(page)
            res = interactor.evaluate_many(scripts)
            return {"status": "ok", "session_name": self.session_name, "results": res}

        if action == "interact":
            actions = req.get("actions", [])
            results = execute_action_sequence(page, actions)
            return {"status": "ok", "session_name": self.session_name, "results": results}

        if action == "inspect":
            selector = req.get("selector", "")
            if not selector:
                return {"status": "error", "message": "Missing 'selector' parameter"}
            data = inspect_page_selector(
                page,
                selector=selector,
                actions=req.get("actions"),
                properties=req.get("properties"),
                include_rules=bool(req.get("rules", False)),
                css=req.get("css"),
                pseudo=req.get("pseudo"),
                target_url=page.url,
            )
            return {
                "status": "ok",
                "session_name": self.session_name,
                "url": page.url,
                "selector": selector,
                "result": data,
            }

        if action == "search":
            results = search_dom(
                page,
                text=req.get("text"),
                keyword=req.get("keyword"),
                role=req.get("role"),
                tag=req.get("tag"),
                wait=req.get("wait"),
                actions=req.get("actions"),
            )
            return {
                "status": "ok",
                "session_name": self.session_name,
                "url": page.url,
                "matches_count": len(results),
                "matches": results,
            }

        if action == "inject_css":
            css_arg = req.get("css", "")
            if not css_arg:
                return {"status": "error", "message": "Missing 'css' parameter"}
            inject_css_or_file(page, css_arg, target_url=page.url)
            return {
                "status": "ok",
                "session_name": self.session_name,
                "url": page.url,
            }

        if action == "inject_script":
            raw_js = req.get("raw_js")
            file_arg = req.get("file")
            if raw_js is None and file_arg:
                p_js = Path(file_arg)
                if not p_js.is_file():
                    return {"status": "error", "message": f"Script file not found: {file_arg}"}
                if p_js.name.endswith(".user.js"):
                    raw_js = parse_userscript(p_js).raw_js
                else:
                    raw_js = p_js.read_text(encoding="utf-8")
            if not raw_js:
                return {"status": "error", "message": "Missing 'file' or 'raw_js' parameter"}
            settle_ms = int(req.get("settle_ms", 500))
            audit_res = inject_userscript(page, raw_js=raw_js, run_at="document-end", settle_ms=settle_ms)
            return {
                "status": "ok" if audit_res.executed and not audit_res.eval_error else "error",
                "session_name": self.session_name,
                "url": page.url,
                "executed": audit_res.executed,
                "eval_error": audit_res.eval_error,
                "errors": audit_res.errors,
                "added_count": len(audit_res.mutations.added_nodes),
                "registered_commands": audit_res.registered_commands,
            }

        if action == "screenshot":
            shots_dir = Path(tempfile.gettempdir()) / "browser-toolkit" / "screenshots"
            shots_dir.mkdir(parents=True, exist_ok=True)
            default_shot = str(shots_dir / f"session_{self.session_name}_{int(time.time() * 1000)}.png")
            out_path = req.get("output") or default_shot
            selector = req.get("selector")
            full_page = bool(req.get("full_page", False))
            interactor = PageInteractor(page)
            saved = interactor.capture_screenshot(out_path, selector=selector, full_page=full_page)
            return {"status": "ok", "session_name": self.session_name, "saved_to": str(saved)}

        if action == "stop":
            self.running = False
            return {"status": "ok", "session_name": self.session_name, "message": "Session stopped"}

        return {"status": "error", "message": f"Unknown action: {action}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Persistent Playwright browser session daemon")
    parser.add_argument("--session-name", default="default", help="Session name identifier")
    parser.add_argument("--url", help="Initial URL to navigate")
    parser.add_argument("--profile", help="Path to custom profile")
    parser.add_argument("--no-profile", action="store_true", help="Do not use profile clone")
    parser.add_argument("--headful", action="store_true", help="Run with visible window")
    parser.add_argument("--timeout", type=float, default=DEFAULT_IDLE_TIMEOUT, help="Idle timeout seconds")
    args = parser.parse_args()

    server = SessionServer(
        session_name=args.session_name,
        profile_path=args.profile,
        use_profile=not args.no_profile,
        headless=not args.headful,
        idle_timeout=args.timeout,
    )
    server.run(initial_url=args.url)


if __name__ == "__main__":
    main()
