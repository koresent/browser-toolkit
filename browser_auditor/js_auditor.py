from dataclasses import dataclass, field
from typing import Any, Dict, List
from playwright.sync_api import Page, ConsoleMessage, Error as PlaywrightError

GM_SHIM_JS = """
(() => {
    if (window._gm_shim_installed) return;
    window._gm_shim_installed = true;

    const storage = {};
    window._gm_registered_commands = [];

    window.unsafeWindow = window;

    window.GM_getValue = function(key, defaultValue) {
        if (key in storage) return storage[key];
        const val = localStorage.getItem('__gm_' + key);
        if (val !== null) {
            try { return JSON.parse(val); } catch(_) { return val; }
        }
        return defaultValue;
    };

    window.GM_setValue = function(key, value) {
        storage[key] = value;
        try {
            localStorage.setItem('__gm_' + key, JSON.stringify(value));
        } catch(_) {}
    };

    window.GM_deleteValue = function(key) {
        delete storage[key];
        localStorage.removeItem('__gm_' + key);
    };

    window.GM_listValues = function() {
        const keys = Object.keys(storage);
        for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            if (k && k.startsWith('__gm_')) {
                keys.push(k.slice(5));
            }
        }
        return [...new Set(keys)];
    };

    window.GM_registerMenuCommand = function(name, fn) {
        window._gm_registered_commands.push(name);
    };

    window.GM_addStyle = function(css) {
        const style = document.createElement('style');
        style.textContent = css;
        (document.head || document.documentElement).appendChild(style);
        return style;
    };

    window.GM_log = function(...args) {
        console.log('[GM_log]', ...args);
    };

    window.GM_xmlhttpRequest = function(details) {
        const url = details.url;
        const method = details.method || 'GET';
        fetch(url, {
            method: method,
            headers: details.headers || {},
            body: details.data || undefined
        }).then(async resp => {
            const text = await resp.text();
            if (details.onload) {
                details.onload({
                    status: resp.status,
                    statusText: resp.statusText,
                    responseText: text,
                    responseHeaders: resp.headers
                });
            }
        }).catch(err => {
            if (details.onerror) details.onerror(err);
        });
    };
})();
"""


@dataclass
class JSAuditResult:
    executed: bool = False
    console_messages: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    registered_commands: List[str] = field(default_factory=list)
    eval_error: str | None = None


def setup_js_listeners(page: Page, result: JSAuditResult) -> None:
    def on_console(msg: ConsoleMessage):
        result.console_messages.append({"type": msg.type, "text": msg.text, "location": str(msg.location)})

    def on_page_error(err: PlaywrightError):
        result.errors.append(str(err))

    page.on("console", on_console)
    page.on("pageerror", on_page_error)


def inject_userscript(page: Page, raw_js: str, run_at: str = "document-end") -> JSAuditResult:
    result = JSAuditResult()
    setup_js_listeners(page, result)

    # Inject GM shim first
    page.add_init_script(GM_SHIM_JS)

    if run_at == "document-start":
        page.add_init_script(raw_js)
        result.executed = True
    else:
        # For document-end or document-idle, evaluate on the loaded page
        try:
            page.evaluate(raw_js)
            result.executed = True
        except Exception as e:
            result.eval_error = str(e)
            result.errors.append(f"Evaluation error: {e}")

    # Inspect registered commands from GM shim
    try:
        commands = page.evaluate("() => window._gm_registered_commands || []")
        result.registered_commands = commands
    except Exception:
        pass

    return result
