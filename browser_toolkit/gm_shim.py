"""
Comprehensive polyfill for Greasemonkey / Violentmonkey / Tampermonkey APIs.
Supports both synchronous GM_* and modern asynchronous GM.* Promise-based APIs.
Includes request logging, clipboard tracking, and command invocation bridge.
"""

GM_FULL_SHIM_JS = r"""
(() => {
    if (window.__gm_shim_installed) return;
    window.__gm_shim_installed = true;

    const storage = {};
    window._gm_storage = storage;
    window._gm_commands = {};
    window._gm_network_log = [];
    window._gm_clipboard_log = [];
    window._gm_notifications_log = [];
    window._gm_opened_tabs_log = [];

    window.unsafeWindow = window;

    // GM_info metadata mock
    window.GM_info = {
        scriptHandler: 'browser-toolkit',
        version: '0.1.0',
        script: {
            name: 'UserScript',
            version: '1.0.0',
            description: 'Audited with browser-toolkit'
        }
    };

    // Storage Sync
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

    // Menu Commands
    window.GM_registerMenuCommand = function(name, fn) {
        window._gm_commands[name] = fn;
    };

    window.GM_unregisterMenuCommand = function(name) {
        delete window._gm_commands[name];
    };

    // Command invocation bridge
    window._gm_invoke_command = function(name) {
        const fn = window._gm_commands[name];
        if (!fn) {
            throw new Error(`Menu command '${name}' not found. Available: ${Object.keys(window._gm_commands).join(', ')}`);
        }
        try {
            return { success: true, result: fn() };
        } catch (err) {
            return { success: false, error: String(err) };
        }
    };

    // DOM & Styles
    window.GM_addStyle = function(css) {
        const style = document.createElement('style');
        style.setAttribute('data-userscript-style', 'true');
        style.textContent = css;
        (document.head || document.documentElement).appendChild(style);
        return style;
    };

    window.GM_log = function(...args) {
        console.log('[GM_log]', ...args);
    };

    // Clipboard
    window.GM_setClipboard = function(text, type = 'text/plain') {
        window._gm_clipboard_log.push({ text: text, type: type, timestamp: Date.now() });
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).catch(() => {});
        }
    };

    // Notifications
    window.GM_notification = function(text, title, image, onclick) {
        const notif = {
            text: typeof text === 'object' ? text.text : text,
            title: typeof text === 'object' ? text.title : title,
            image: typeof text === 'object' ? text.image : image,
            timestamp: Date.now()
        };
        window._gm_notifications_log.push(notif);
        console.log('[GM_notification]', notif.title || 'Notification', notif.text);
    };

    // Open in Tab
    window.GM_openInTab = function(url, options = {}) {
        window._gm_opened_tabs_log.push({ url: url, options: options, timestamp: Date.now() });
        console.log('[GM_openInTab]', url);
        return { closed: false, close: () => {} };
    };

    // Network / XHR
    window.GM_xmlhttpRequest = function(details) {
        const startTime = Date.now();
        const url = details.url;
        const method = (details.method || 'GET').toUpperCase();
        const headers = details.headers || {};
        const data = details.data || undefined;

        const logEntry = {
            id: 'req_' + Math.random().toString(36).slice(2, 8),
            url: url,
            method: method,
            headers: headers,
            data: typeof data === 'string' ? data.slice(0, 500) : null,
            status: null,
            durationMs: 0,
            error: null,
            timestamp: startTime
        };
        window._gm_network_log.push(logEntry);

        fetch(url, {
            method: method,
            headers: headers,
            body: data
        }).then(async resp => {
            logEntry.durationMs = Date.now() - startTime;
            logEntry.status = resp.status;
            const text = await resp.text();

            if (details.onload) {
                try {
                    details.onload({
                        status: resp.status,
                        statusText: resp.statusText,
                        responseText: text,
                        responseHeaders: resp.headers,
                        readyState: 4
                    });
                } catch (cbErr) {
                    console.error('[GM_xmlhttpRequest onload callback error]', cbErr);
                }
            }
        }).catch(err => {
            logEntry.durationMs = Date.now() - startTime;
            logEntry.error = String(err);
            if (details.onerror) {
                try {
                    details.onerror({ error: String(err), readyState: 4 });
                } catch (cbErr) {
                    console.error('[GM_xmlhttpRequest onerror callback error]', cbErr);
                }
            }
        });
    };

    // Modern asynchronous GM.* API
    window.GM = {
        info: window.GM_info,
        getValue: async function(key, defaultValue) {
            return window.GM_getValue(key, defaultValue);
        },
        setValue: async function(key, value) {
            window.GM_setValue(key, value);
        },
        deleteValue: async function(key) {
            window.GM_deleteValue(key);
        },
        listValues: async function() {
            return window.GM_listValues();
        },
        addStyle: function(css) {
            return window.GM_addStyle(css);
        },
        registerMenuCommand: function(name, fn) {
            return window.GM_registerMenuCommand(name, fn);
        },
        setClipboard: async function(text, type) {
            return window.GM_setClipboard(text, type);
        },
        notification: function(options, ondone) {
            return window.GM_notification(options);
        },
        openInTab: function(url, options) {
            return window.GM_openInTab(url, options);
        },
        xmlHttpRequest: function(details) {
            return window.GM_xmlhttpRequest(details);
        }
    };
})();
"""
