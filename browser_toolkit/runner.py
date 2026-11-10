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
from .crawler import discover_sample_subpages
from .archetype_crawler import crawl_site_archetypes, CrawlReport
from .palette_extractor import extract_site_palette
from .contrast_checker import check_page_contrast
from .preview import run_live_preview
from .css_color_extractor import extract_colors_from_file_or_url


class AuditorRunner:
    def __init__(self, profile_path: Optional[str] = None, use_profile: bool = True, headless: bool = True):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.headless = headless

    def audit_style(
        self,
        style_path: str | Path,
        target_url: Optional[str] = None,
        urls: Optional[List[str]] = None,
        sample_pages: int = 2,
        deep_hunt: bool = False,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        info = parse_userstyle(style_path)
        base_url = target_url or info.get_target_url()
        css_to_apply = info.get_combined_css_for_url(base_url)

        out_path = Path(output_dir or f"./audit-results/{info.filepath.stem}").resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        pages_to_test = list(urls) if urls else [base_url]

        report: Dict[str, Any] = {
            "type": "userstyle",
            "name": info.name or info.filepath.name,
            "version": info.version,
            "target_url": base_url,
            "style_file": str(info.filepath),
            "output_dir": str(out_path),
            "tested_pages": [],
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
                    if deep_hunt and not urls:
                        crawl_res = crawl_site_archetypes(
                            page=page,
                            start_url=base_url,
                            css_content=css_to_apply,
                            output_dir=out_path,
                        )
                        report["deep_hunt"] = {
                            "stopped_reason": crawl_res.stopped_reason,
                            "pages_scanned": crawl_res.total_pages_visited,
                            "archetypes_count": len(crawl_res.archetypes),
                            "archetypes": [
                                {
                                    "url": a.url,
                                    "title": a.title,
                                    "matched_selectors_count": len(a.matched_selectors),
                                    "similarity_to_previous": a.similarity_to_previous,
                                    "screenshot": a.screenshot_path,
                                }
                                for a in crawl_res.archetypes
                            ],
                        }
                        report["tested_pages"] = [
                            {"url": a.url, "matched_count": len(a.matched_selectors), "screenshot_after": a.screenshot_path}
                            for a in crawl_res.archetypes
                        ]
                        report["css_audit"] = {
                            "total_selectors": len(crawl_res.cumulative_matched_selectors) + len(crawl_res.remaining_dead_selectors),
                            "cumulative_matched_count": len(crawl_res.cumulative_matched_selectors),
                            "dead_count": len(crawl_res.remaining_dead_selectors),
                            "invalid_count": 0,
                            "parse_error": None,
                            "matched": [{"selector": s, "total_count": 1} for s in crawl_res.cumulative_matched_selectors],
                            "dead": [{"selector": s, "suggestions": []} for s in crawl_res.remaining_dead_selectors],
                            "invalid": [],
                        }
                        return report
                    # 1. Navigate to base URL
                    page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)

                    # Auto-discover representative subpages if requested and not explicitly provided
                    if sample_pages > 0 and not urls:
                        discovered = discover_sample_subpages(page, base_url, max_subpages=sample_pages)
                        for d_url in discovered:
                            if d_url not in pages_to_test:
                                pages_to_test.append(d_url)

                    # Track aggregated selector coverage across all tested pages
                    matched_by_selector: Dict[str, Dict[str, Any]] = {}
                    dead_candidates: Dict[str, List[Any]] = {}
                    invalid_selectors: List[Dict[str, str]] = []
                    total_selectors_count = 0
                    parse_err = None

                    for idx, p_url in enumerate(pages_to_test):
                        if idx > 0:
                            page.goto(p_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(1500)

                        # Screenshots
                        before_shot = out_path / f"page_{idx + 1}_before.png"
                        page.screenshot(path=str(before_shot), full_page=False)

                        css_result = audit_css_on_page(page, css_to_apply)
                        total_selectors_count = max(total_selectors_count, css_result.total_selectors)
                        if css_result.parse_error:
                            parse_err = css_result.parse_error

                        after_shot = out_path / f"page_{idx + 1}_after.png"
                        page.screenshot(path=str(after_shot), full_page=False)

                        page_matched = 0
                        for m in css_result.matched:
                            page_matched += 1
                            if m.selector not in matched_by_selector:
                                matched_by_selector[m.selector] = {
                                    "selector": m.selector,
                                    "total_count": m.count,
                                    "found_on_pages": [p_url],
                                    "samples": m.samples,
                                }
                            else:
                                matched_by_selector[m.selector]["total_count"] += m.count
                                matched_by_selector[m.selector]["found_on_pages"].append(p_url)

                        for d in css_result.dead:
                            if d.selector not in matched_by_selector:
                                if d.selector not in dead_candidates:
                                    dead_candidates[d.selector] = d.suggestions

                        for inv in css_result.invalid:
                            if inv not in invalid_selectors:
                                invalid_selectors.append(inv)

                        report["tested_pages"].append({
                            "url": p_url,
                            "matched_count": page_matched,
                            "screenshot_before": str(before_shot),
                            "screenshot_after": str(after_shot),
                        })

                    # Dead selectors are strictly those not matched on ANY page
                    truly_dead = [
                        {"selector": sel, "suggestions": dead_candidates.get(sel, [])}
                        for sel in dead_candidates.keys()
                        if sel not in matched_by_selector
                    ]

                    report["css_audit"] = {
                        "total_selectors": total_selectors_count,
                        "cumulative_matched_count": len(matched_by_selector),
                        "dead_count": len(truly_dead),
                        "invalid_count": len(invalid_selectors),
                        "parse_error": parse_err,
                        "matched": list(matched_by_selector.values()),
                        "dead": truly_dead,
                        "invalid": invalid_selectors,
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

    def map_site(
        self,
        url: str,
        css_path: Optional[str | Path] = None,
        max_archetypes: int = 8,
        max_pages: int = 25,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        css_content = None
        if css_path:
            info = parse_userstyle(css_path)
            css_content = info.get_combined_css_for_url(url)

        out_path = Path(output_dir or "./audit-results/site-map").resolve()
        out_path.mkdir(parents=True, exist_ok=True)

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
                    crawl_res = crawl_site_archetypes(
                        page=page,
                        start_url=url,
                        css_content=css_content,
                        max_archetypes=max_archetypes,
                        max_pages=max_pages,
                        output_dir=out_path,
                    )
                    return {
                        "base_url": url,
                        "pages_visited": crawl_res.total_pages_visited,
                        "archetypes_count": len(crawl_res.archetypes),
                        "stopped_reason": crawl_res.stopped_reason,
                        "archetypes": [
                            {
                                "index": idx + 1,
                                "url": a.url,
                                "title": a.title,
                                "similarity_to_previous": a.similarity_to_previous,
                                "matched_selectors_count": len(a.matched_selectors),
                                "screenshot": a.screenshot_path,
                            }
                            for idx, a in enumerate(crawl_res.archetypes)
                        ],
                        "cumulative_matched_count": len(crawl_res.cumulative_matched_selectors),
                        "remaining_dead_count": len(crawl_res.remaining_dead_selectors),
                    }
                finally:
                    context.close()

    def extract_palette(self, url: str) -> Dict[str, Any]:
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
                    return extract_site_palette(page, url)
                finally:
                    context.close()

    def extract_css_colors(self, target: str, output_path: Optional[str | Path] = None) -> str:
        return extract_colors_from_file_or_url(
            target=target,
            output_path=output_path,
            profile_path=self.profile_path,
            use_profile=self.use_profile,
        )

    def check_contrast(self, url: str, css_path: Optional[str | Path] = None) -> Dict[str, Any]:
        css_content = None
        if css_path:
            info = parse_userstyle(css_path)
            css_content = info.get_combined_css_for_url(url)

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
                    res = check_page_contrast(page, css_content)
                    return {"url": url, "contrast_audit": res}
                finally:
                    context.close()

    def preview(
        self,
        url: str,
        style_path: str | Path,
        headful: bool = False,
        screenshot: bool = True,
        output_screenshot: str = "preview.png",
    ) -> None:
        run_live_preview(
            url=url,
            style_path=style_path,
            profile_path=self.profile_path,
            use_profile=self.use_profile,
            headless=not headful,
            screenshot_on_change=screenshot,
            output_screenshot=output_screenshot,
        )
