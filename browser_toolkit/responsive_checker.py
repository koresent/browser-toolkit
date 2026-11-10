"""
Responsive layout auditor: checks for horizontal overflows, touch target sizing,
text clipping, and fixed element obscuration across viewports.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.sync_api import Page


@dataclass
class OverflowElement:
    selector: str
    tag_name: str
    class_name: str
    overflow_px: float
    bounds: Dict[str, float]
    computed_styles: Dict[str, str]
    text_snippet: str = ""


@dataclass
class TouchTargetIssue:
    selector: str
    tag_name: str
    width: float
    height: float
    text_snippet: str = ""


@dataclass
class TextClippingIssue:
    selector: str
    tag_name: str
    scroll_width: float
    client_width: float
    text_snippet: str = ""


@dataclass
class StickyCoverageIssue:
    selector: str
    position: str
    height_ratio_pct: float
    bounds: Dict[str, float]


@dataclass
class ViewportAuditResult:
    viewport: Tuple[int, int]
    label: str
    has_horizontal_overflow: bool
    page_scroll_width: float
    viewport_width: float
    overflow_elements: List[OverflowElement] = field(default_factory=list)
    touch_target_issues: List[TouchTargetIssue] = field(default_factory=list)
    text_clipping_issues: List[TextClippingIssue] = field(default_factory=list)
    sticky_coverage_issues: List[StickyCoverageIssue] = field(default_factory=list)
    screenshot_path: Optional[str] = None


@dataclass
class ResponsiveAuditReport:
    url: str
    results: List[ViewportAuditResult] = field(default_factory=list)

    @property
    def has_any_issues(self) -> bool:
        for r in self.results:
            if (
                r.has_horizontal_overflow
                or r.touch_target_issues
                or r.text_clipping_issues
                or r.sticky_coverage_issues
            ):
                return True
        return False


JS_RESPONSIVE_AUDIT = r"""() => {
    function getSelector(el) {
        if (!el || el.nodeType !== 1) return '';
        if (el.id) return '#' + el.id;
        let name = el.tagName.toLowerCase();
        let cls = '';
        if (typeof el.className === 'string' && el.className.trim()) {
            const firstClass = el.className.trim().split(/\s+/)[0];
            if (firstClass && !firstClass.includes(':') && !firstClass.includes('[')) {
                cls = '.' + CSS.escape(firstClass);
            }
        }
        let parent = el.parentElement;
        if (parent && parent !== document.body && parent !== document.documentElement) {
            let parentName = parent.tagName.toLowerCase();
            if (parent.id) {
                parentName = '#' + parent.id;
            } else if (typeof parent.className === 'string' && parent.className.trim()) {
                const pCls = parent.className.trim().split(/\s+/)[0];
                if (pCls && !pCls.includes(':') && !pCls.includes('[')) {
                    parentName += '.' + CSS.escape(pCls);
                }
            }
            return `${parentName} > ${name}${cls}`;
        }
        return `${name}${cls}`;
    }

    const winW = window.innerWidth;
    const winH = window.innerHeight;
    const docW = Math.max(
        document.documentElement.scrollWidth,
        document.body ? document.body.scrollWidth : 0
    );
    const hasHorizontalOverflow = docW > winW + 1;

    // Detect elements exceeding viewport width
    const overflowElements = [];
    if (hasHorizontalOverflow) {
        const all = document.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            const el = all[i];
            const tag = el.tagName.toLowerCase();
            if (['script', 'style', 'meta', 'link', 'head', 'html'].includes(tag)) continue;

            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;

            // Bleeds past right viewport boundary
            if (rect.right > winW + 2) {
                const overflowPx = Math.round(rect.right - winW);
                const text = (el.innerText || el.textContent || '').trim().slice(0, 50);
                overflowElements.push({
                    selector: getSelector(el),
                    tagName: tag,
                    className: typeof el.className === 'string' ? el.className.slice(0, 80) : '',
                    overflowPx: overflowPx,
                    bounds: {
                        left: Math.round(rect.left),
                        right: Math.round(rect.right),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    },
                    computedStyles: {
                        width: style.width,
                        maxWidth: style.maxWidth,
                        minWidth: style.minWidth,
                        overflowX: style.overflowX,
                        boxSizing: style.boxSizing
                    },
                    textSnippet: text
                });
            }
        }
        // Sort descending by overflow extent and limit to top 15
        overflowElements.sort((a, b) => b.overflowPx - a.overflowPx);
    }

    // Validate interactive target sizes per WCAG 2.5.8 on mobile viewports
    const touchTargetIssues = [];
    if (winW <= 820) {
        const interactives = document.querySelectorAll('a, button, input, select, textarea, [role="button"], [onclick]');
        for (let i = 0; i < interactives.length; i++) {
            const el = interactives[i];
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

            // WCAG 2.5.8 target size minimum (24x24px)
            if (rect.width < 24 || rect.height < 24) {
                touchTargetIssues.push({
                    selector: getSelector(el),
                    tagName: el.tagName.toLowerCase(),
                    width: Math.round(rect.width * 10) / 10,
                    height: Math.round(rect.height * 10) / 10,
                    textSnippet: (el.innerText || el.getAttribute('aria-label') || el.title || '').trim().slice(0, 40)
                });
                if (touchTargetIssues.length >= 15) break;
            }
        }
    }

    // Detect clipped text nodes without ellipsis
    const textClippingIssues = [];
    const textNodes = document.querySelectorAll('p, h1, h2, h3, h4, h5, h6, span, li, a');
    for (let i = 0; i < textNodes.length; i++) {
        const el = textNodes[i];
        if (el.children.length > 2) continue; // Focus on leaf-ish text nodes
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.display === 'inline') continue;
        if (el.clientWidth === 0) continue;
        if (style.overflowX === 'hidden' && style.textOverflow !== 'ellipsis') {
            if (el.scrollWidth > el.clientWidth + 4) {
                textClippingIssues.push({
                    selector: getSelector(el),
                    tagName: el.tagName.toLowerCase(),
                    scrollWidth: Math.round(el.scrollWidth),
                    clientWidth: Math.round(el.clientWidth),
                    textSnippet: (el.innerText || '').trim().slice(0, 50)
                });
                if (textClippingIssues.length >= 10) break;
            }
        }
    }

    // Check for fixed or sticky elements covering more than 30% of viewport height
    const stickyCoverageIssues = [];
    const fixedSticky = document.querySelectorAll('*');
    for (let i = 0; i < fixedSticky.length; i++) {
        const el = fixedSticky[i];
        const style = window.getComputedStyle(el);
        if (style.position === 'fixed' || style.position === 'sticky') {
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const heightRatio = rect.height / winH;
            // Covers > 30% of screen height
            if (heightRatio > 0.30 && rect.width > winW * 0.5) {
                stickyCoverageIssues.push({
                    selector: getSelector(el),
                    position: style.position,
                    heightRatioPct: Math.round(heightRatio * 100),
                    bounds: {
                        top: Math.round(rect.top),
                        bottom: Math.round(rect.bottom),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height)
                    }
                });
            }
        }
    }

    return {
        viewportWidth: winW,
        pageScrollWidth: docW,
        hasHorizontalOverflow: hasHorizontalOverflow,
        overflowElements: overflowElements.slice(0, 10),
        touchTargetIssues: touchTargetIssues,
        textClippingIssues: textClippingIssues,
        stickyCoverageIssues: stickyCoverageIssues
    };
};
"""


class ResponsiveChecker:
    """Audits page layout across standard or custom breakpoints."""

    DEFAULT_VIEWPORTS = [
        (390, 844, "Mobile (390x844)"),
        (768, 1024, "Tablet (768x1024)"),
        (1440, 900, "Desktop (1440x900)"),
    ]

    def __init__(
        self,
        viewports: Optional[List[Tuple[int, int, str]]] = None,
        custom_css: Optional[str] = None,
    ):
        self.viewports = viewports or self.DEFAULT_VIEWPORTS
        self.custom_css = custom_css

    def audit(
        self,
        page: Page,
        url: str,
        screenshot_dir: Optional[Path] = None,
        wait_network_idle: bool = True,
    ) -> ResponsiveAuditReport:
        """Navigates to URL, checks each viewport, and returns an audit report."""
        if wait_network_idle:
            page.goto(url, wait_until="networkidle", timeout=30000)
        else:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Inject custom CSS if provided
        if self.custom_css:
            page.add_style_tag(content=self.custom_css)
            page.wait_for_timeout(200)

        results: List[ViewportAuditResult] = []

        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)

        for w, h, label in self.viewports:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(400)  # Wait for media queries to settle

            raw = page.evaluate(JS_RESPONSIVE_AUDIT)

            overflow_elements = [
                OverflowElement(
                    selector=item["selector"],
                    tag_name=item["tagName"],
                    class_name=item["className"],
                    overflow_px=item["overflowPx"],
                    bounds=item["bounds"],
                    computed_styles=item["computedStyles"],
                    text_snippet=item.get("textSnippet", ""),
                )
                for item in raw.get("overflowElements", [])
            ]

            touch_issues = [
                TouchTargetIssue(
                    selector=item["selector"],
                    tag_name=item["tagName"],
                    width=item["width"],
                    height=item["height"],
                    text_snippet=item.get("textSnippet", ""),
                )
                for item in raw.get("touchTargetIssues", [])
            ]

            text_clipping = [
                TextClippingIssue(
                    selector=item["selector"],
                    tag_name=item["tagName"],
                    scroll_width=item["scrollWidth"],
                    client_width=item["clientWidth"],
                    text_snippet=item.get("textSnippet", ""),
                )
                for item in raw.get("textClippingIssues", [])
            ]

            sticky_issues = [
                StickyCoverageIssue(
                    selector=item["selector"],
                    position=item["position"],
                    height_ratio_pct=item["heightRatioPct"],
                    bounds=item["bounds"],
                )
                for item in raw.get("stickyCoverageIssues", [])
            ]

            screenshot_path = None
            if screenshot_dir:
                shot_file = screenshot_dir / f"responsive_{w}x{h}.png"
                page.screenshot(path=str(shot_file), full_page=False)
                screenshot_path = str(shot_file)

            results.append(
                ViewportAuditResult(
                    viewport=(w, h),
                    label=label,
                    has_horizontal_overflow=raw.get("hasHorizontalOverflow", False),
                    page_scroll_width=raw.get("pageScrollWidth", 0),
                    viewport_width=raw.get("viewportWidth", w),
                    overflow_elements=overflow_elements,
                    touch_target_issues=touch_issues,
                    text_clipping_issues=text_clipping,
                    sticky_coverage_issues=sticky_issues,
                    screenshot_path=screenshot_path,
                )
            )

        return ResponsiveAuditReport(url=url, results=results)
