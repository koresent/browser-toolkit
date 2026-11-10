"""
UserScript execution auditor with modern GM polyfills, DOM mutation tracking,
network logging, and menu command invocation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page, ConsoleMessage, Error as PlaywrightError

from .gm_shim import GM_FULL_SHIM_JS
from .mutation_tracker import (
    attach_mutation_tracker,
    collect_dom_mutations,
    DOMMutationReport,
    JS_INIT_MUTATION_TRACKER,
)

GM_SHIM_JS = GM_FULL_SHIM_JS


@dataclass
class JSAuditResult:
    executed: bool = False
    console_messages: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    registered_commands: List[str] = field(default_factory=list)
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    clipboard_log: List[Dict[str, Any]] = field(default_factory=list)
    notifications_log: List[Dict[str, Any]] = field(default_factory=list)
    mutations: DOMMutationReport = field(default_factory=DOMMutationReport)
    eval_error: Optional[str] = None
    command_invocation_result: Optional[Dict[str, Any]] = None


def setup_js_listeners(page: Page, result: JSAuditResult) -> None:
    def on_console(msg: ConsoleMessage):
        result.console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "location": str(msg.location),
        })

    def on_page_error(err: PlaywrightError):
        result.errors.append(str(err))

    page.on("console", on_console)
    page.on("pageerror", on_page_error)


def inject_userscript(
    page: Page,
    raw_js: str,
    run_at: str = "document-end",
    invoke_command: Optional[str] = None,
    settle_ms: int = 500,
) -> JSAuditResult:
    """Injects modern GM polyfill and userscript, tracks DOM mutations,

    console messages, and network requests.
    """
    result = JSAuditResult()
    setup_js_listeners(page, result)

    # 1. Attach GM shim and DOM mutation observer to future navigations and current document
    page.add_init_script(GM_FULL_SHIM_JS)
    attach_mutation_tracker(page)
    try:
        page.evaluate(GM_FULL_SHIM_JS)
        page.evaluate(JS_INIT_MUTATION_TRACKER)
    except Exception:
        pass

    wrapped_js = f"(() => {{\n{raw_js}\n}})()"

    if run_at == "document-start":
        page.add_init_script(wrapped_js)
        result.executed = True
    else:
        try:
            page.evaluate(wrapped_js)
            result.executed = True
        except Exception as e:
            result.eval_error = str(e)
            result.errors.append(f"Evaluation error: {e}")

    # Allow async script tasks to settle
    if settle_ms > 0:
        page.wait_for_timeout(settle_ms)

    # 2. Extract registered menu commands
    try:
        cmds = page.evaluate("() => Object.keys(window._gm_commands || {})")
        result.registered_commands = cmds
    except Exception:
        pass

    # 3. If command invocation requested, trigger it
    if invoke_command:
        try:
            cmd_res = page.evaluate(
                f"window._gm_invoke_command({invoke_command!r})"
            )
            result.command_invocation_result = cmd_res
            if not cmd_res.get("success"):
                result.errors.append(f"Command '{invoke_command}' error: {cmd_res.get('error')}")
            # Give callback time to settle
            page.wait_for_timeout(300)
        except Exception as e:
            result.command_invocation_result = {"success": False, "error": str(e)}
            result.errors.append(f"Failed to invoke command '{invoke_command}': {e}")

    # 4. Extract network requests
    try:
        net_log = page.evaluate("() => window._gm_network_log || []")
        result.network_requests = net_log
    except Exception:
        pass

    # 5. Extract clipboard & notifications
    try:
        result.clipboard_log = page.evaluate("() => window._gm_clipboard_log || []")
        result.notifications_log = page.evaluate("() => window._gm_notifications_log || []")
    except Exception:
        pass

    # 6. Extract DOM mutations
    result.mutations = collect_dom_mutations(page)

    return result
