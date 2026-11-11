import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .parser import parse_userstyle, parse_userscript
from .css_auditor import audit_css_on_page, CSSAuditResult
from .js_auditor import inject_userscript, setup_js_listeners, JSAuditResult
from .search import search_dom
from .interaction import PageInteractor, execute_action_sequence
from .test_rule import test_rule_impact
from .scanner import scan_directory
from .crawler import discover_sample_subpages
from .archetype_crawler import crawl_site_archetypes, CrawlReport
from .palette_extractor import extract_site_palette
from .contrast_checker import check_page_contrast
from .preview import run_live_preview
from .preview_js import run_live_script_preview
from .spa_checker import check_spa_resilience
from .css_color_extractor import extract_colors_from_file_or_url
from .responsive_checker import ResponsiveChecker
from .theme_flaw_checker import ThemeFlawChecker
from .gm_shim import GM_FULL_SHIM_JS
from .mutation_tracker import attach_mutation_tracker, collect_dom_mutations
from .extension_manager import ExtensionManager
from .sync_server import run_sync_server
from .navigation import safe_goto
from .browser_backend import (
    ensure_playwright_browser,
    safe_launch_persistent_context,
    safe_launch_browser,
)


class AuditorRunner:
    def __init__(self, profile_path: Optional[str] = None, use_profile: bool = True, headless: bool = True):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.headless = headless

    def _launch_browser_context(
        self,
        p: Any,
        temp_profile: Optional[Path],
        viewport: Optional[Dict[str, int]] = None,
        bypass_csp: bool = True,
        **extra_kwargs: Any,
    ) -> Tuple[Any, Any]:
        vp = viewport or {"width": 1440, "height": 900}
        launch_kwargs: Dict[str, Any] = {
            "headless": self.headless,
            **extra_kwargs,
        }
        if bypass_csp:
            launch_kwargs["bypass_csp"] = True

        if temp_profile:
            context = safe_launch_persistent_context(
                p,
                user_data_dir=str(temp_profile),
                viewport=vp,
                **launch_kwargs,
            )
            page = context.new_page() if not context.pages else context.pages[0]
        else:
            browser = safe_launch_browser(p, headless=self.headless, **extra_kwargs)
            context = browser.new_context(viewport=vp, bypass_csp=bypass_csp)
            page = context.new_page()

        return context, page

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

        default_out = Path(tempfile.gettempdir()) / "browser-toolkit" / "audit-results" / info.filepath.stem
        out_path = Path(output_dir).resolve() if output_dir else default_out
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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

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
                    safe_goto(page, base_url, wait_until="domcontentloaded", timeout=30000)
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
                            safe_goto(page, p_url, wait_until="domcontentloaded", timeout=30000)
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

        default_out = Path(tempfile.gettempdir()) / "browser-toolkit" / "audit-results" / info.filepath.stem
        out_path = Path(output_dir).resolve() if output_dir else default_out
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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    js_result = JSAuditResult()
                    setup_js_listeners(page, js_result)
                    page.add_init_script(GM_FULL_SHIM_JS)
                    attach_mutation_tracker(page)

                    if info.run_at == "document-start":
                        page.add_init_script(info.raw_js)

                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)

                    if info.run_at != "document-start":
                        page.wait_for_timeout(1000)
                        try:
                            page.evaluate(info.raw_js)
                            js_result.executed = True
                        except Exception as e:
                            js_result.eval_error = str(e)
                            js_result.errors.append(f"Eval error: {e}")

                    page.wait_for_timeout(1500)

                    # Extract commands, network, clipboard, mutations
                    try:
                        cmds = page.evaluate("() => Object.keys(window._gm_commands || {})")
                        js_result.registered_commands = cmds
                    except Exception:
                        pass

                    try:
                        js_result.network_requests = page.evaluate("() => window._gm_network_log || []")
                    except Exception:
                        pass

                    js_result.mutations = collect_dom_mutations(page)

                    screenshot_path = out_path / "script_applied.png"
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    report["screenshot"] = str(screenshot_path)

                    report["js_audit"] = {
                        "executed": js_result.executed,
                        "eval_error": js_result.eval_error,
                        "errors": js_result.errors,
                        "registered_commands": js_result.registered_commands,
                        "network_requests": js_result.network_requests,
                        "dom_mutations": {
                            "added_count": len(js_result.mutations.added_nodes),
                            "added_nodes": [
                                {
                                    "selector": n.selector,
                                    "tag_name": n.tag_name,
                                    "text_snippet": n.text_snippet,
                                }
                                for n in js_result.mutations.added_nodes[:15]
                            ],
                            "removed_count": len(js_result.mutations.removed_nodes),
                            "attributes_modified_count": len(js_result.mutations.attribute_mutations),
                        },
                        "console_messages": js_result.console_messages[-30:],
                    }
                finally:
                    context.close()

        return report

    def inspect_element(
        self,
        url: str,
        selector: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        properties: Optional[List[str]] = None,
        include_rules: bool = False,
        css: Optional[str] = None,
        pseudo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Inspects an element on a live page using the Zen profile,
        returning its HTML, computed styles, CSS custom properties, and matched stylesheet rules.
        """
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=False)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1000)

                    if css:
                        css_content = css
                        p_css = Path(css)
                        if p_css.exists():
                            info = parse_userstyle(p_css)
                            css_content = info.get_combined_css_for_url(url)
                        page.add_style_tag(content=css_content)

                    if actions:
                        execute_action_sequence(page, actions)

                    eval_opts = {
                        "properties": properties or [],
                        "includeRules": bool(include_rules),
                        "pseudo": pseudo,
                    }

                    data = page.evaluate(
                        """
                        ([sel, opts]) => {
                            const els = document.querySelectorAll(sel);
                            if (els.length === 0) return { count: 0, items: [] };

                            const reqProps = opts.properties || [];
                            const includeRules = Boolean(opts.includeRules);
                            const pseudo = opts.pseudo || null;

                            function getMatchedRules(el) {
                                const matched = [];
                                for (const sheet of document.styleSheets) {
                                    try {
                                        const rules = sheet.cssRules || sheet.rules;
                                        if (!rules) continue;
                                        for (const rule of rules) {
                                            if (rule.type === CSSRule.STYLE_RULE && rule.selectorText) {
                                                try {
                                                    if (el.matches(rule.selectorText)) {
                                                        const decl = {};
                                                        for (let i = 0; i < rule.style.length; i++) {
                                                            const p = rule.style[i];
                                                            decl[p] = rule.style.getPropertyValue(p);
                                                        }
                                                        matched.push({
                                                            selector: rule.selectorText,
                                                            properties: decl,
                                                            source: sheet.href ? sheet.href.split('/').pop().split('?')[0] : 'inline'
                                                        });
                                                    }
                                                } catch (_) {}
                                            }
                                        }
                                    } catch (_) {}
                                }
                                return matched;
                            }

                            function getCustomVars(comp) {
                                const vars = {};
                                for (let i = 0; i < comp.length; i++) {
                                    const p = comp[i];
                                    if (p.startsWith('--')) {
                                        vars[p] = comp.getPropertyValue(p).trim();
                                    }
                                }
                                return vars;
                            }

                            const items = [];
                            for (let i = 0; i < Math.min(els.length, 5); i++) {
                                const el = els[i];
                                const comp = window.getComputedStyle(el, pseudo);
                                const rect = el.getBoundingClientRect();

                                const attrs = {};
                                for (const a of el.attributes) {
                                    attrs[a.name] = a.value;
                                }

                                const computed = {};
                                if (reqProps.length > 0) {
                                    for (const p of reqProps) {
                                        computed[p] = comp.getPropertyValue(p) || comp[p] || '';
                                    }
                                } else {
                                    computed.display = comp.display;
                                    computed.visibility = comp.visibility;
                                    computed.opacity = comp.opacity;
                                    computed.color = comp.color;
                                    computed.backgroundColor = comp.backgroundColor;
                                    computed.backgroundImage = comp.backgroundImage;
                                    computed.borderRadius = comp.borderRadius;
                                    computed.boxShadow = comp.boxShadow;
                                    computed.border = comp.border;
                                    computed.fill = comp.fill;
                                }

                                const item = {
                                    tagName: el.tagName.toLowerCase(),
                                    attributes: attrs,
                                    rect: { width: Math.round(rect.width), height: Math.round(rect.height) },
                                    computed: computed,
                                    customProperties: getCustomVars(comp),
                                    outerHTML: el.outerHTML.slice(0, 500)
                                };

                                if (includeRules) {
                                    item.matchedRules = getMatchedRules(el);
                                }

                                items.push(item);
                            }
                            return { count: els.length, items: items };
                        }
                        """,
                        [selector, eval_opts],
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
        wait: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1000)
                    results = search_dom(page, text=text, keyword=keyword, role=role, tag=tag, wait=wait, actions=actions)
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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)

                    interactor = PageInteractor(page)
                    if wait_selector:
                        s_str = str(wait_selector).strip()
                        if s_str.isdigit():
                            page.wait_for_timeout(int(s_str))
                        else:
                            interactor.wait_for(s_str)
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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
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

        default_out = Path(tempfile.gettempdir()) / "browser-toolkit" / "site-map"
        out_path = Path(output_dir).resolve() if output_dir else default_out
        out_path.mkdir(parents=True, exist_ok=True)

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

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
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)
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

    def check_responsive(
        self,
        url: str,
        css_path: Optional[str | Path] = None,
        viewports: Optional[List[Tuple[int, int, str]]] = None,
        screenshot_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        css_content = None
        if css_path:
            info = parse_userstyle(css_path)
            css_content = info.get_combined_css_for_url(url)

        checker = ResponsiveChecker(viewports=viewports, custom_css=css_content)

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=False)

                try:
                    s_dir = Path(screenshot_dir) if screenshot_dir else None
                    report = checker.audit(page, url=url, screenshot_dir=s_dir)

                    return {
                        "url": report.url,
                        "has_any_issues": report.has_any_issues,
                        "viewports": [
                            {
                                "viewport": list(r.viewport),
                                "label": r.label,
                                "has_horizontal_overflow": r.has_horizontal_overflow,
                                "page_scroll_width": r.page_scroll_width,
                                "viewport_width": r.viewport_width,
                                "overflow_elements": [
                                    {
                                        "selector": e.selector,
                                        "tag_name": e.tag_name,
                                        "class_name": e.class_name,
                                        "overflow_px": e.overflow_px,
                                        "bounds": e.bounds,
                                        "computed_styles": e.computed_styles,
                                        "text_snippet": e.text_snippet,
                                    }
                                    for e in r.overflow_elements
                                ],
                                "touch_target_issues": [
                                    {
                                        "selector": t.selector,
                                        "tag_name": t.tag_name,
                                        "width": t.width,
                                        "height": t.height,
                                        "text_snippet": t.text_snippet,
                                    }
                                    for t in r.touch_target_issues
                                ],
                                "text_clipping_issues": [
                                    {
                                        "selector": tc.selector,
                                        "tag_name": tc.tag_name,
                                        "scroll_width": tc.scroll_width,
                                        "client_width": tc.client_width,
                                        "text_snippet": tc.text_snippet,
                                    }
                                    for tc in r.text_clipping_issues
                                ],
                                "sticky_coverage_issues": [
                                    {
                                        "selector": sc.selector,
                                        "position": sc.position,
                                        "height_ratio_pct": sc.height_ratio_pct,
                                        "bounds": sc.bounds,
                                    }
                                    for sc in r.sticky_coverage_issues
                                ],
                                "screenshot_path": r.screenshot_path,
                            }
                            for r in report.results
                        ],
                    }
                finally:
                    context.close()

    def check_theme(
        self,
        url: str,
        target_theme: str = "dark",
        css_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        css_content = None
        if css_path:
            info = parse_userstyle(css_path)
            css_content = info.get_combined_css_for_url(url)

        checker = ThemeFlawChecker(target_theme=target_theme, custom_css=css_content)

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    report = checker.audit(page, url=url)
                    return {
                        "url": report.url,
                        "theme_mode": report.theme_mode,
                        "has_any_issues": report.has_any_issues,
                        "has_custom_scrollbar": report.has_custom_scrollbar,
                        "total_elements_checked": report.total_elements_checked,
                        "bleedthrough_issues": [
                            {
                                "selector": b.selector,
                                "tag_name": b.tag_name,
                                "property_name": b.property_name,
                                "color": b.color,
                                "bounds": b.bounds,
                                "text_snippet": b.text_snippet,
                            }
                            for b in report.bleedthrough_issues
                        ],
                        "invisible_text_issues": [
                            {
                                "selector": t.selector,
                                "tag_name": t.tag_name,
                                "text": t.text,
                                "color": t.color,
                                "bg_color": t.bg_color,
                                "contrast_ratio": t.contrast_ratio,
                            }
                            for t in report.invisible_text_issues
                        ],
                        "unstyled_input_issues": [
                            {
                                "selector": u.selector,
                                "tag_name": u.tag_name,
                                "input_type": u.input_type,
                                "bg_color": u.bg_color,
                                "text_color": u.text_color,
                                "contrast_ratio": u.contrast_ratio,
                                "description": u.description,
                            }
                            for u in report.unstyled_input_issues
                        ],
                        "invisible_icon_issues": [
                            {
                                "selector": ic.selector,
                                "tag_name": ic.tag_name,
                                "fill_or_stroke": ic.fill_or_stroke,
                                "parent_bg": ic.parent_bg,
                                "contrast_ratio": ic.contrast_ratio,
                            }
                            for ic in report.invisible_icon_issues
                        ],
                    }
                finally:
                    context.close()

    def test_script(
        self,
        script_path: str | Path,
        target_url: Optional[str] = None,
        invoke_command: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        info = parse_userscript(script_path)
        url = target_url or info.get_target_url()

        default_out = Path(tempfile.gettempdir()) / "browser-toolkit" / "audit-results" / info.filepath.stem
        out_path = Path(output_dir).resolve() if output_dir else default_out
        out_path.mkdir(parents=True, exist_ok=True)

        report: Dict[str, Any] = {
            "type": "userscript_test",
            "name": info.name or info.filepath.name,
            "version": info.version,
            "target_url": url,
            "script_file": str(info.filepath),
            "output_dir": str(out_path),
        }

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    js_result = JSAuditResult()
                    setup_js_listeners(page, js_result)
                    page.add_init_script(GM_FULL_SHIM_JS)
                    attach_mutation_tracker(page)

                    if info.run_at == "document-start":
                        page.add_init_script(info.raw_js)

                    safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)

                    if info.run_at != "document-start":
                        page.wait_for_timeout(1000)
                        try:
                            page.evaluate(info.raw_js)
                            js_result.executed = True
                        except Exception as e:
                            js_result.eval_error = str(e)
                            js_result.errors.append(f"Eval error: {e}")

                    page.wait_for_timeout(1000)

                    # Extract commands
                    try:
                        cmds = page.evaluate("() => Object.keys(window._gm_commands || {})")
                        js_result.registered_commands = cmds
                    except Exception:
                        pass

                    # Invoke command if requested
                    if invoke_command:
                        try:
                            cmd_res = page.evaluate(f"window._gm_invoke_command({invoke_command!r})")
                            js_result.command_invocation_result = cmd_res
                            if not cmd_res.get("success"):
                                js_result.errors.append(f"Command '{invoke_command}' error: {cmd_res.get('error')}")
                            page.wait_for_timeout(500)
                        except Exception as e:
                            js_result.command_invocation_result = {"success": False, "error": str(e)}
                            js_result.errors.append(f"Failed to invoke '{invoke_command}': {e}")

                    # Execute interactive actions if provided
                    if actions:
                        interactor = PageInteractor(page)
                        execute_action_sequence(interactor, actions)
                        page.wait_for_timeout(500)

                    # Extract network requests
                    try:
                        js_result.network_requests = page.evaluate("() => window._gm_network_log || []")
                    except Exception:
                        pass

                    # Extract clipboard & notifications
                    try:
                        js_result.clipboard_log = page.evaluate("() => window._gm_clipboard_log || []")
                        js_result.notifications_log = page.evaluate("() => window._gm_notifications_log || []")
                    except Exception:
                        pass

                    # Extract mutations
                    js_result.mutations = collect_dom_mutations(page)

                    screenshot_path = out_path / "script_test.png"
                    page.screenshot(path=str(screenshot_path), full_page=False)

                    report["executed"] = js_result.executed
                    report["errors"] = js_result.errors
                    report["registered_commands"] = js_result.registered_commands
                    report["command_invocation_result"] = js_result.command_invocation_result
                    report["network_requests"] = js_result.network_requests
                    report["clipboard_log"] = js_result.clipboard_log
                    report["notifications_log"] = js_result.notifications_log
                    report["dom_mutations"] = {
                        "added_nodes": [
                            {
                                "selector": n.selector,
                                "tag_name": n.tag_name,
                                "id": n.id,
                                "class_name": n.class_name,
                                "text_snippet": n.text_snippet,
                                "html_snippet": n.html_snippet,
                            }
                            for n in js_result.mutations.added_nodes
                        ],
                        "removed_nodes": [
                            {
                                "tag_name": r.tag_name,
                                "id": r.id,
                                "class_name": r.class_name,
                            }
                            for r in js_result.mutations.removed_nodes
                        ],
                        "attribute_mutations": [
                            {
                                "selector": a.selector,
                                "attribute_name": a.attribute_name,
                                "old_value": a.old_value,
                                "new_value": a.new_value,
                            }
                            for a in js_result.mutations.attribute_mutations
                        ],
                    }
                    report["console_messages"] = js_result.console_messages[-30:]
                    report["screenshot"] = str(screenshot_path)
                    return report
                finally:
                    context.close()

    def check_spa(
        self,
        script_path: str | Path,
        initial_url: Optional[str] = None,
        target_spa_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        info = parse_userscript(script_path)
        i_url = initial_url or info.get_target_url()
        t_url = target_spa_url or i_url

        with ZenProfileContext(self.profile_path, use_profile=self.use_profile) as temp_profile:
            with sync_playwright() as p:
                context, page = self._launch_browser_context(p, temp_profile, bypass_csp=True)

                try:
                    rep = check_spa_resilience(
                        page=page,
                        initial_url=i_url,
                        target_spa_url=t_url,
                        raw_js=info.raw_js,
                        run_at=info.run_at or "document-end",
                    )
                    return {
                        "script": info.name or info.filepath.name,
                        "initial_url": rep.initial_url,
                        "target_url": rep.target_url,
                        "survived": rep.survived,
                        "initial_added_elements_count": rep.initial_added_elements_count,
                        "post_navigation_elements_count": rep.post_navigation_elements_count,
                        "retained_selectors": rep.retained_selectors,
                        "lost_selectors": rep.lost_selectors,
                        "errors": rep.errors_during_navigation,
                    }
                finally:
                    context.close()

    def preview_script(
        self,
        url: str,
        script_path: str | Path,
        headful: bool = True,
        screenshot: bool = True,
        output_screenshot: str = "preview_js.png",
    ) -> None:
        run_live_script_preview(
            url=url,
            script_path=script_path,
            profile_path=self.profile_path,
            use_profile=self.use_profile,
            headless=not headful,
            screenshot_on_change=screenshot,
            output_screenshot=output_screenshot,
        )

    def get_extension_manager(self) -> ExtensionManager:
        return ExtensionManager(self.profile_path)

    def ext_status(self) -> Dict[str, Any]:
        mgr = self.get_extension_manager()
        styles = mgr.list_styles()
        scripts = mgr.list_scripts()
        return {
            "profile_dir": str(mgr.profile_dir),
            "stylus_db": str(mgr.get_stylus_db_path() or "Not found"),
            "violentmonkey_db": str(mgr.get_violentmonkey_db_path() or "Not found"),
            "stylus_installed_count": len(styles),
            "violentmonkey_installed_count": len(scripts),
            "active_styles_count": sum(1 for s in styles if s.enabled),
            "active_scripts_count": sum(1 for sc in scripts if sc.enabled),
        }

    def ext_list_styles(self) -> List[Dict[str, Any]]:
        mgr = self.get_extension_manager()
        return [
            {
                "id": s.id,
                "name": s.name,
                "enabled": s.enabled,
                "sections_count": len(s.sections),
                "domains": [d for sec in s.sections for d in sec.domains],
            }
            for s in mgr.list_styles()
        ]

    def ext_list_scripts(self) -> List[Dict[str, Any]]:
        mgr = self.get_extension_manager()
        return [
            {
                "id": sc.id,
                "name": sc.name,
                "version": sc.version,
                "enabled": sc.enabled,
                "matches": sc.matches,
                "code_size": len(sc.code),
            }
            for sc in mgr.list_scripts()
        ]

    def ext_export_styles(self, output_dir: str | Path) -> int:
        mgr = self.get_extension_manager()
        return mgr.export_styles(output_dir)

    def ext_export_scripts(self, output_dir: str | Path) -> int:
        mgr = self.get_extension_manager()
        return mgr.export_scripts(output_dir)

    def ext_diff_styles(self, local_dir: str | Path) -> Dict[str, Any]:
        mgr = self.get_extension_manager()
        return mgr.diff_styles(local_dir)

    def ext_diff_scripts(self, local_dir: str | Path) -> Dict[str, Any]:
        mgr = self.get_extension_manager()
        return mgr.diff_scripts(local_dir)

    def ext_build_stylus_backup(self, styles_dir: str | Path, output_file: str | Path) -> int:
        mgr = self.get_extension_manager()
        return mgr.build_stylus_backup_json(styles_dir, output_file)

    def ext_build_vm_backup(self, scripts_dir: str | Path, output_file: str | Path) -> int:
        mgr = self.get_extension_manager()
        return mgr.build_violentmonkey_backup_zip(scripts_dir, output_file)

    def ext_serve(
        self,
        port: int = 8080,
        styles_dir: Optional[str | Path] = None,
        scripts_dir: Optional[str | Path] = None,
    ) -> None:
        run_sync_server(
            port=port,
            styles_dir=styles_dir,
            scripts_dir=scripts_dir,
            profile_path=self.profile_path,
        )

    def ext_find_style(self, target: str | int) -> Optional[Dict[str, Any]]:
        mgr = self.get_extension_manager()
        s = mgr.find_style(target)
        if not s:
            return None
        return {
            "id": s.id,
            "name": s.name,
            "enabled": s.enabled,
            "sections_count": len(s.sections),
            "domains": [d for sec in s.sections for d in sec.domains],
        }

    def ext_set_style_enabled(self, target: str | int, enabled: bool) -> bool:
        mgr = self.get_extension_manager()
        return mgr.set_style_enabled(target, enabled)

    def ext_toggle_style(self, target: str | int) -> bool:
        mgr = self.get_extension_manager()
        return mgr.toggle_style(target)

    def ext_delete_style(self, target: str | int) -> bool:
        mgr = self.get_extension_manager()
        return mgr.delete_style(target)

    def ext_install_or_update_style(self, style_path: str | Path, enabled: bool = True) -> Dict[str, Any]:
        mgr = self.get_extension_manager()
        return mgr.install_or_update_style(style_path, enabled=enabled)

    def ext_find_script(self, target: str | int) -> Optional[Dict[str, Any]]:
        mgr = self.get_extension_manager()
        sc = mgr.find_script(target)
        if not sc:
            return None
        return {
            "id": sc.id,
            "name": sc.name,
            "version": sc.version,
            "enabled": sc.enabled,
            "matches": sc.matches,
            "code_size": len(sc.code),
        }

    def ext_set_script_enabled(self, target: str | int, enabled: bool) -> bool:
        mgr = self.get_extension_manager()
        return mgr.set_script_enabled(target, enabled)

    def ext_toggle_script(self, target: str | int) -> bool:
        mgr = self.get_extension_manager()
        return mgr.toggle_script(target)

    def ext_delete_script(self, target: str | int) -> bool:
        mgr = self.get_extension_manager()
        return mgr.delete_script(target)

    def ext_install_or_update_script(self, script_path: str | Path, enabled: bool = True) -> Dict[str, Any]:
        mgr = self.get_extension_manager()
        return mgr.install_or_update_script(script_path, enabled=enabled)
