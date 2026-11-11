import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

SOCKET_PATH = Path(tempfile.gettempdir()) / "browser-toolkit" / "session.sock"
PID_PATH = Path(tempfile.gettempdir()) / "browser-toolkit" / "session.pid"


def is_session_alive() -> bool:
    """Checks whether the session daemon is running and responding."""
    if not SOCKET_PATH.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(str(SOCKET_PATH))
        sock.sendall(json.dumps({"action": "ping"}).encode("utf-8") + b"\n")
        resp = sock.recv(1024)
        if resp:
            data = json.loads(resp.decode("utf-8").strip())
            return data.get("status") == "ok"
    except (OSError, ValueError):
        # Stale socket
        try:
            SOCKET_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    finally:
        sock.close()
    return False


def send_session_command(command: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    """Sends a command to the running session daemon and returns the response."""
    if not is_session_alive():
        raise RuntimeError("No active browser-toolkit session. Start one with 'browser-toolkit session start <url>'")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(SOCKET_PATH))
        sock.sendall(json.dumps(command).encode("utf-8") + b"\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        if not buf:
            raise RuntimeError("Empty response received from session daemon")
        return json.loads(buf.decode("utf-8").strip())
    finally:
        sock.close()


def start_session(
    url: Optional[str] = None,
    profile_path: Optional[str] = None,
    no_profile: bool = False,
    headful: bool = False,
    wait_timeout: float = 20.0,
) -> Dict[str, Any]:
    """Starts session daemon if not running, or navigates existing session."""
    if is_session_alive():
        if url:
            return send_session_command({"action": "goto", "url": url})
        return send_session_command({"action": "status"})

    cmd = [sys.executable, "-m", "browser_toolkit.session_server"]
    if url:
        cmd.extend(["--url", url])
    if profile_path:
        cmd.extend(["--profile", profile_path])
    if no_profile:
        cmd.append("--no-profile")
    if headful:
        cmd.append("--headful")

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if is_session_alive():
            return send_session_command({"action": "status"})
        time.sleep(0.3)

    raise RuntimeError("Failed to start session daemon within timeout")


def stop_session() -> Dict[str, Any]:
    """Stops the active session daemon."""
    if not is_session_alive():
        return {"status": "ok", "message": "No active session"}

    try:
        res = send_session_command({"action": "stop"}, timeout=5.0)
    except Exception:
        res = {"status": "ok", "message": "Session terminated"}

    deadline = time.time() + 3.0
    while time.time() < deadline and SOCKET_PATH.exists():
        time.sleep(0.1)

    try:
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
    except OSError:
        pass

    return res
