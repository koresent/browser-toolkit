import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .session_server import get_session_pid_path, get_session_socket_path


def resolve_session_name(session_name: Optional[str] = None) -> str:
    """Resolves session name from parameter, env var, or falls back to 'default'."""
    if session_name and session_name.strip():
        return session_name.strip()
    env_name = os.getenv("BROWSER_TOOLKIT_SESSION", "").strip()
    if env_name:
        return env_name
    return "default"


def is_session_alive(session_name: Optional[str] = None) -> bool:
    """Checks whether the session daemon for session_name is running and responding."""
    name = resolve_session_name(session_name)
    sock_path = get_session_socket_path(name)
    if not sock_path.exists():
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(str(sock_path))
        sock.sendall(json.dumps({"action": "ping"}).encode("utf-8") + b"\n")
        resp = sock.recv(1024)
        if resp:
            data = json.loads(resp.decode("utf-8").strip())
            return data.get("status") == "ok"
    except (OSError, ValueError):
        try:
            sock_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    finally:
        sock.close()
    return False


def send_session_command(
    command: Dict[str, Any],
    session_name: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Sends a command to the running session daemon and returns the response."""
    name = resolve_session_name(session_name)
    if not is_session_alive(name):
        raise RuntimeError(
            f"No active browser-toolkit session '{name}'. Start one with 'browser-toolkit session --name {name} start <url>'"
        )

    sock_path = get_session_socket_path(name)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(sock_path))
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
    session_name: Optional[str] = None,
    profile_path: Optional[str] = None,
    no_profile: bool = False,
    headful: bool = False,
    wait_timeout: float = 20.0,
) -> Dict[str, Any]:
    """Starts session daemon if not running, or navigates existing session."""
    name = resolve_session_name(session_name)
    sock_path = get_session_socket_path(name)

    if is_session_alive(name):
        if url:
            return send_session_command({"action": "goto", "url": url}, session_name=name)
        return send_session_command({"action": "status"}, session_name=name)

    cmd = [
        sys.executable,
        "-m",
        "browser_toolkit.session_server",
        "--session-name",
        name,
    ]
    if url:
        cmd.extend(["--url", url])
    if profile_path:
        cmd.extend(["--profile", profile_path])
    if no_profile:
        cmd.append("--no-profile")
    if headful:
        cmd.append("--headful")

    sock_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if is_session_alive(name):
            return send_session_command({"action": "status"}, session_name=name)
        time.sleep(0.3)

    raise RuntimeError(f"Failed to start session daemon '{name}' within timeout")


def stop_session(session_name: Optional[str] = None) -> Dict[str, Any]:
    """Stops the active session daemon."""
    name = resolve_session_name(session_name)
    sock_path = get_session_socket_path(name)

    if not is_session_alive(name):
        return {"status": "ok", "session_name": name, "message": f"No active session '{name}'"}

    try:
        res = send_session_command({"action": "stop"}, session_name=name, timeout=5.0)
    except Exception:
        res = {"status": "ok", "session_name": name, "message": "Session terminated"}

    deadline = time.time() + 3.0
    while time.time() < deadline and sock_path.exists():
        time.sleep(0.1)

    try:
        if sock_path.exists():
            sock_path.unlink()
    except OSError:
        pass

    return res


def list_active_sessions() -> List[Dict[str, Any]]:
    """Scans and queries all active browser sessions."""
    toolkit_dir = Path(tempfile.gettempdir()) / "browser-toolkit"
    if not toolkit_dir.exists():
        return []

    active: List[Dict[str, Any]] = []
    for sock in toolkit_dir.glob("session*.sock"):
        name = "default" if sock.name == "session.sock" else sock.stem.replace("session_", "")
        if is_session_alive(name):
            try:
                st = send_session_command({"action": "status"}, session_name=name, timeout=2.0)
                active.append(st)
            except Exception:
                pass
    return active
