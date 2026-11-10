import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .parser import parse_userstyle, parse_userscript
from .css_auditor import audit_css_on_page, CSSAuditResult
from .js_auditor import inject_userscript, setup_js_listeners, JSAuditResult, GM_SHIM_JS
from .search import search_dom
from .interaction import PageInteractor, execute_action_sequence
from .test_rule import test_rule_impact
from .scanner import scan_directory


class AuditorRunner:
    def __init__(self, profile_path: Optional[str] = None, use_profile: bool = True, headless: bool = True):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.headless = headless

    def audit_style(
        self,
        style_path: str | Path,
        target_url: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        info = parse_userstyle(style_path)
        url = target_url or info.get_target_url()
        css_to_apply = info.get_combined_css_for_url(url)

        out_path = Path(output_dir or f"./audit-results/{info.filepath.stem}").resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        report: Dict[str, Any] = {
            "type": "userstyle",
            "name": info.name or info.filepath.name,
            "version": info.version,
            "target_url": url,
            "style_file": str(info.filepath),
            "output_dir": str(out_path),
        }

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {
                    "headless": self.headless,
                }

                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    # Navigate to target
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    # 1. Capture BEFORE screenshot
                    before_screenshot = out_path / "before.png"
                    page.screenshot(path=str(before_screenshot), full_page=False)
                    report["screenshot_before"] = str(before_screenshot)

                    # 2. Run CSS Selector Audit & inject styles
                    css_result = audit_css_on_page(page, css_to_apply)
                    page.wait_for_timeout(1000)

                    # 3. Capture AFTER screenshot
                    after_screenshot = out_path / "after.png"
                    page.screenshot(path=str(after_screenshot), full_page=False)
                    report["screenshot_after"] = str(after_screenshot)

                    report["css_audit"] = {
                        "total_selectors": css_result.total_selectors,
                        "matched_count": len(css_result.matched),
                        "dead_count": len(css_result.dead),
                        "invalid_count": len(css_result.invalid),
                        "parse_error": css_result.parse_error,
                        "matched": [
                            {"selector": m.selector, "count": m.count, "samples": m.samples}
                            for m in css_result.matched
                        ],
                        "dead": [
                            {"selector": d.selector, "suggestions": d.suggestions}
                            for d in css_result.dead
                        ],
                        "invalid": css_result.invalid,
                    }
                finally:
                    context.close()

        return report

    def audit_script(
        self,
        script_path: str | Path,
        target_url: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        info = parse_userscript(script_path)
        url = target_url or info.get_target_url()

        out_path = Path(output_dir or f"./audit-results/{info.filepath.stem}").resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        report: Dict[str, Any] = {
            "type": "userscript",
            "name": info.name or info.filepath.name,
            "version": info.version,
            "target_url": url,
            "script_file": str(info.filepath),
            "output_dir": str(out_path),
        }

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {
                    "headless": self.headless,
                }

                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    js_result = JSAuditResult()
                    setup_js_listeners(page, js_result)
                    page.add_init_script(GM_SHIM_JS)

                    if info.run_at == "document-start":
                        page.add_init_script(info.raw_js)

                    page.goto(url, wait_until="domcontentloaded", timeout=30000)

                    if info.run_at != "document-start":
                        page.wait_for_timeout(1000)
                        try:
                            page.evaluate(info.raw_js)
                            js_result.executed = True
                        except Exception as e:
                            js_result.eval_error = str(e)
                            js_result.errors.append(f"Eval error: {e}")

                    page.wait_for_timeout(2000)

                    screenshot_path = out_path / "script_applied.png"
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    report["screenshot"] = str(screenshot_path)

                    try:
                        commands = page.evaluate("() => window._gm_registered_commands || []")
                        js_result.registered_commands = commands
                    except Exception:
                        pass

                    report["js_audit"] = {
                        "executed": js_result.executed,
                        "eval_error": js_result.eval_error,
                        "errors": js_result.errors,
                        "registered_commands": js_result.registered_commands,
                        "console_messages": js_result.console_messages[-30:],
                    }
                finally:
                    context.close()

        return report

    def inspect_element(self, url: str, selector: str) -> Dict[str, Any]:
        """
        Inspects an element on a live page using the Zen profile,
        returning its HTML, computed styles, and attributes.
        """
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {"headless": self.headless}
                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context()
                    page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)

                    data = page.evaluate(
                        """
                        (sel) => {
                            const els = document.querySelectorAll(sel);
                            if (els.length === 0) return { count: 0, items: [] };

                            const items = [];
                            for (let i = 0; i < Math.min(els.length, 5); i++) {
                                const el = els[i];
                                const comp = window.getComputedStyle(el);
                                const attrs = {};
                                for (const a of el.attributes) {
                                    attrs[a.name] = a.value;
                                }
                                items.push({
                                    tagName: el.tagName.toLowerCase(),
                                    attributes: attrs,
                                    outerHTML: el.outerHTML.slice(0, 500),
                                    display: comp.display,
                                    visibility: comp.visibility,
                                    color: comp.color,
                                    backgroundColor: comp.backgroundColor,
                                });
                            }
                            return { count: els.length, items: items };
                        }
                        """,
                        selector,
                    )
                    return {"url": url, "selector": selector, "result": data}
                finally:
                    context.close()

    def search(
        self,
        url: str,
        text: Optional[str] = None,
        keyword: Optional[str] = None,
        role: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {"headless": self.headless}
                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    results = search_dom(page, text=text, keyword=keyword, role=role, tag=tag)
                    return {"url": url, "matches_count": len(results), "matches": results}
                finally:
                    context.close()

    def screenshot(
        self,
        url: str,
        output_path: str | Path,
        selector: Optional[str] = None,
        hover_selector: Optional[str] = None,
        wait_selector: Optional[str] = None,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {"headless": self.headless}
                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)

                    interactor = PageInteractor(page)
                    if wait_selector:
                        interactor.wait_for(wait_selector)
                    if hover_selector:
                        interactor.hover(hover_selector)
                        page.wait_for_timeout(500)

                    saved = interactor.capture_screenshot(output_path, selector=selector, full_page=full_page)
                    return {"url": url, "saved_to": str(saved)}
                finally:
                    context.close()

    def test_rule(
        self,
        url: str,
        css_rule: str,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {"headless": self.headless}
                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    return test_rule_impact(page, css_rule, output_dir=output_dir)
                finally:
                    context.close()

    def interact(
        self,
        url: str,
        actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                launch_kwargs: Dict[str, Any] = {"headless": self.headless}
                if temp_profile:
                    context = p.firefox.launch_persistent_context(
                        user_data_dir=str(temp_profile),
                        viewport={"width": 1440, "height": 900},
                        **launch_kwargs,
                    )
                    page = context.new_page() if not context.pages else context.pages[0]
                else:
                    browser = p.firefox.launch(**launch_kwargs)
                    context = browser.new_context(viewport={"width": 1440, "height": 900})
                    page = context.new_page()

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    results = execute_action_sequence(page, actions)
                    return {"url": url, "action_results": results}
                finally:
                    context.close()
