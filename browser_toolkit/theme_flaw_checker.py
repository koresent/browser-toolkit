"""
Theme flaw auditor: detects bright bleedthrough in dark themes, invisible text,
unstyled form inputs, low-contrast SVG icons, and missing scrollbar theming.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page
from .navigation import safe_goto


def _extract_rgb_strings_from_css(css_text: str) -> List[str]:
    """Extracts hex and rgb/rgba colors from CSS text normalized as 'rgb(r, g, b)'."""
    colors: set[str] = set()
    for hex_match in re.findall(r"#([0-9a-fA-F]{3,8})\b", css_text):
        h = hex_match.lower()
        if len(h) == 3:
            r, g, b = int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16)
            colors.add(f"rgb({r}, {g}, {b})")
        elif len(h) in (6, 8):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            colors.add(f"rgb({r}, {g}, {b})")
    for r_str, g_str, b_str in re.findall(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", css_text):
        colors.add(f"rgb({int(r_str)}, {int(g_str)}, {int(b_str)})")
    return sorted(colors)


@dataclass
class BrightBleedthroughIssue:
    selector: str
    tag_name: str
    property_name: str  # 'background-color' or 'border-color'
    color: str
    bounds: Dict[str, float]
    text_snippet: str = ""


@dataclass
class UnstyledInputIssue:
    selector: str
    tag_name: str
    input_type: str
    bg_color: str
    text_color: str
    contrast_ratio: float
    description: str


@dataclass
class InvisibleIconIssue:
    selector: str
    tag_name: str
    fill_or_stroke: str
    parent_bg: str
    contrast_ratio: float


@dataclass
class BlindspotTextIssue:
    selector: str
    tag_name: str
    text: str
    color: str
    bg_color: str
    contrast_ratio: float


@dataclass
class ThemeFlawReport:
    url: str
    theme_mode: str  # 'dark' or 'light'
    bleedthrough_issues: List[BrightBleedthroughIssue] = field(default_factory=list)
    invisible_text_issues: List[BlindspotTextIssue] = field(default_factory=list)
    unstyled_input_issues: List[UnstyledInputIssue] = field(default_factory=list)
    invisible_icon_issues: List[InvisibleIconIssue] = field(default_factory=list)
    has_custom_scrollbar: bool = False
    total_elements_checked: int = 0
    dominant_surfaces: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_any_issues(self) -> bool:
        return bool(
            self.bleedthrough_issues
            or self.invisible_text_issues
            or self.unstyled_input_issues
            or self.invisible_icon_issues
            or not self.has_custom_scrollbar
        )


JS_THEME_FLAW_AUDIT = r"""(arg) => {
    const expectedMode = typeof arg === 'string' ? arg : (arg && arg.mode ? arg.mode : 'dark');
    const excludeSet = new Set(Array.isArray(arg && arg.excludeColors) ? arg.excludeColors : []);
    function parseRgb(rgbStr) {
        if (!rgbStr || rgbStr === 'transparent') return null;
        const m = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
        if (!m) return null;
        const a = m[4] !== undefined ? parseFloat(m[4]) : 1.0;
        if (a === 0) return null;
        return { r: parseInt(m[1]), g: parseInt(m[2]), b: parseInt(m[3]), a: a };
    }

    function sRgbToLin(c) {
        const v = c / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }

    function getLuminance(rgb) {
        return 0.2126 * sRgbToLin(rgb.r) + 0.7152 * sRgbToLin(rgb.g) + 0.0722 * sRgbToLin(rgb.b);
    }

    function getContrastRatio(fgRgb, bgRgb) {
        const l1 = getLuminance(fgRgb);
        const l2 = getLuminance(bgRgb);
        const brightest = Math.max(l1, l2);
        const darkest = Math.min(l1, l2);
        return (brightest + 0.05) / (darkest + 0.05);
    }

    function getEffectiveBg(el) {
        let cur = el;
        while (cur && cur !== document.documentElement) {
            const comp = window.getComputedStyle(cur);
            const parsed = parseRgb(comp.backgroundColor);
            if (parsed && parsed.a > 0.4) {
                return parsed;
            }
            cur = cur.parentElement;
        }
        return expectedMode === 'dark' ? { r: 40, g: 40, b: 40, a: 1.0 } : { r: 251, g: 241, b: 199, a: 1.0 };
    }

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

    const isDark = (expectedMode === 'dark');
    const bleedthroughIssues = [];
    const invisibleTextIssues = [];
    const unstyledInputIssues = [];
    const invisibleIconIssues = [];
    const surfaceBuckets = {};

    function recordSurface(propName, rgbObj, el) {
        if (!rgbObj || rgbObj.a <= 0.1) return;
        const norm = `rgb(${rgbObj.r}, ${rgbObj.g}, ${rgbObj.b})`;
        if (excludeSet.has(norm)) return;
        const key = `${propName}:${norm}`;
        if (!surfaceBuckets[key]) {
            surfaceBuckets[key] = { property: propName, color: norm, count: 0, samples: [] };
        }
        surfaceBuckets[key].count++;
        if (surfaceBuckets[key].samples.length < 2) {
            const sel = getSelector(el);
            if (sel && !surfaceBuckets[key].samples.includes(sel)) {
                surfaceBuckets[key].samples.push(sel);
            }
        }
    }

    const elements = document.querySelectorAll('*');
    let checkedCount = 0;

    for (let i = 0; i < elements.length; i++) {
        const el = elements[i];
        const tag = el.tagName.toLowerCase();
        if (['script', 'style', 'meta', 'link', 'head', 'noscript'].includes(tag)) continue;

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        const comp = window.getComputedStyle(el);
        if (comp.display === 'none' || comp.visibility === 'hidden' || comp.opacity === '0') continue;
        checkedCount++;

        // Detect bright bleedthrough in dark mode (or dark bleedthrough in light mode)
        const bgRgb = parseRgb(comp.backgroundColor);
        recordSurface('background-color', bgRgb, el);
        if (comp.borderTopWidth !== '0px' && comp.borderTopStyle !== 'none') {
            recordSurface('border-color', parseRgb(comp.borderTopColor), el);
        }
        if (bgRgb && bgRgb.a > 0.6) {
            const lum = getLuminance(bgRgb);
            // In dark mode, background luminance > 0.5 is jarring bleedthrough
            if (isDark && lum > 0.5) {
                // Ignore small badge icons or buttons if intended, but flag cards and boxes
                if (rect.width > 30 && rect.height > 15) {
                    bleedthroughIssues.push({
                        selector: getSelector(el),
                        tagName: tag,
                        propertyName: 'background-color',
                        color: comp.backgroundColor,
                        bounds: { width: Math.round(rect.width), height: Math.round(rect.height) },
                        textSnippet: (el.innerText || '').trim().slice(0, 40)
                    });
                }
            } else if (!isDark && lum < 0.15) {
                if (rect.width > 30 && rect.height > 15) {
                    bleedthroughIssues.push({
                        selector: getSelector(el),
                        tagName: tag,
                        propertyName: 'background-color',
                        color: comp.backgroundColor,
                        bounds: { width: Math.round(rect.width), height: Math.round(rect.height) },
                        textSnippet: (el.innerText || '').trim().slice(0, 40)
                    });
                }
            }
        }

        // Inspect native form controls for contrast and unstyled backgrounds
        if (['input', 'textarea', 'select'].includes(tag)) {
            const inputType = el.getAttribute('type') || (tag === 'textarea' ? 'textarea' : 'text');
            if (!['hidden', 'submit', 'button', 'image'].includes(inputType)) {
                const effectiveInputBg = bgRgb || getEffectiveBg(el);
                const inputFg = parseRgb(comp.color);
                if (inputFg && effectiveInputBg) {
                    const ratio = getContrastRatio(inputFg, effectiveInputBg);
                    const bgLum = getLuminance(effectiveInputBg);
                    if (isDark && bgLum > 0.5) {
                        unstyledInputIssues.push({
                            selector: getSelector(el),
                            tagName: tag,
                            inputType: inputType,
                            bgColor: comp.backgroundColor,
                            textColor: comp.color,
                            contrastRatio: Math.round(ratio * 10) / 10,
                            description: 'Bright unstyled input background in dark theme'
                        });
                    } else if (ratio < 2.5) {
                        unstyledInputIssues.push({
                            selector: getSelector(el),
                            tagName: tag,
                            inputType: inputType,
                            bgColor: comp.backgroundColor || `rgb(${effectiveInputBg.r}, ${effectiveInputBg.g}, ${effectiveInputBg.b})`,
                            textColor: comp.color,
                            contrastRatio: Math.round(ratio * 10) / 10,
                            description: 'Critical low contrast / invisible text inside input field'
                        });
                    }
                }
            }
        }

        // Detect low-contrast SVG icons
        if (tag === 'svg') {
            const svgFill = parseRgb(comp.fill);
            const parentBg = getEffectiveBg(el);
            if (svgFill && parentBg) {
                const ratio = getContrastRatio(svgFill, parentBg);
                if (ratio < 1.8) {
                    invisibleIconIssues.push({
                        selector: getSelector(el),
                        tagName: tag,
                        fillOrStroke: `fill: ${comp.fill}`,
                        parentBg: `rgb(${parentBg.r}, ${parentBg.g}, ${parentBg.b})`,
                        contrastRatio: Math.round(ratio * 10) / 10
                    });
                }
            }
        }

        // Flag text with contrast ratio under 1.8:1
        if (['p', 'span', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td', 'th', 'li', 'label', 'button'].includes(tag)) {
            const text = (el.innerText || '').trim();
            if (text.length >= 2 && el.children.length <= 1) {
                const fg = parseRgb(comp.color);
                const bg = getEffectiveBg(el);
                if (fg && bg) {
                    const ratio = getContrastRatio(fg, bg);
                    if (ratio < 1.8) {
                        invisibleTextIssues.push({
                            selector: getSelector(el),
                            tagName: tag,
                            text: text.slice(0, 40),
                            color: comp.color,
                            bgColor: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
                            contrastRatio: Math.round(ratio * 10) / 10
                        });
                    }
                }
            }
        }

        if (bleedthroughIssues.length >= 20 && invisibleTextIssues.length >= 20) break;
    }

    // Check for scrollbar-color property on root (frames fall back cleanly if documentElement is missing).
    const rootStyle = document.documentElement ? window.getComputedStyle(document.documentElement) : null;
    const bodyStyle = document.body ? window.getComputedStyle(document.body) : null;
    const hasCustomScrollbar = (
        (rootStyle && rootStyle.scrollbarColor && rootStyle.scrollbarColor !== 'auto') ||
        (bodyStyle && bodyStyle.scrollbarColor && bodyStyle.scrollbarColor !== 'auto')
    );

    const dominantSurfaces = Object.values(surfaceBuckets)
        .sort((a, b) => b.count - a.count)
        .slice(0, 12);

    return {
        totalChecked: checkedCount,
        hasCustomScrollbar: !!hasCustomScrollbar,
        bleedthroughIssues: bleedthroughIssues.slice(0, 15),
        invisibleTextIssues: invisibleTextIssues.slice(0, 15),
        unstyledInputIssues: unstyledInputIssues.slice(0, 10),
        invisibleIconIssues: invisibleIconIssues.slice(0, 10),
        dominantSurfaces: dominantSurfaces
    };
};
"""


class ThemeFlawChecker:
    """Audits page for visual flaws: bright bleedthrough in dark mode,
    invisible text, unstyled inputs, hidden icons, and unstyled surface colors.
    """

    def __init__(
        self,
        target_theme: str = "dark",
        custom_css: Optional[str] = None,
        exclude_colors: Optional[List[str]] = None,
    ):
        self.target_theme = target_theme
        self.custom_css = custom_css
        self.exclude_colors = exclude_colors

    def audit_page(self, page: Any, url: Optional[str] = None) -> ThemeFlawReport:
        """Audits the currently loaded Page or Frame without navigating."""
        if self.custom_css:
            page.add_style_tag(content=self.custom_css)
            page.wait_for_timeout(200)

        exclude_list: List[str] = []
        if self.exclude_colors:
            exclude_list = _extract_rgb_strings_from_css(" ".join(self.exclude_colors))
        elif self.custom_css:
            exclude_list = _extract_rgb_strings_from_css(self.custom_css)

        raw = page.evaluate(
            JS_THEME_FLAW_AUDIT,
            {"mode": self.target_theme, "excludeColors": exclude_list},
        )

        bleedthrough = [
            BrightBleedthroughIssue(
                selector=item["selector"],
                tag_name=item["tagName"],
                property_name=item["propertyName"],
                color=item["color"],
                bounds=item["bounds"],
                text_snippet=item.get("textSnippet", ""),
            )
            for item in raw.get("bleedthroughIssues", [])
        ]

        invisible_text = [
            BlindspotTextIssue(
                selector=item["selector"],
                tag_name=item["tagName"],
                text=item["text"],
                color=item["color"],
                bg_color=item["bgColor"],
                contrast_ratio=item["contrastRatio"],
            )
            for item in raw.get("invisibleTextIssues", [])
        ]

        unstyled_inputs = [
            UnstyledInputIssue(
                selector=item["selector"],
                tag_name=item["tagName"],
                input_type=item["inputType"],
                bg_color=item["bgColor"],
                text_color=item["textColor"],
                contrast_ratio=item["contrastRatio"],
                description=item["description"],
            )
            for item in raw.get("unstyledInputIssues", [])
        ]

        invisible_icons = [
            InvisibleIconIssue(
                selector=item["selector"],
                tag_name=item["tagName"],
                fill_or_stroke=item["fillOrStroke"],
                parent_bg=item["parentBg"],
                contrast_ratio=item["contrastRatio"],
            )
            for item in raw.get("invisibleIconIssues", [])
        ]

        return ThemeFlawReport(
            url=url or getattr(page, "url", ""),
            theme_mode=self.target_theme,
            bleedthrough_issues=bleedthrough,
            invisible_text_issues=invisible_text,
            unstyled_input_issues=unstyled_inputs,
            invisible_icon_issues=invisible_icons,
            has_custom_scrollbar=raw.get("hasCustomScrollbar", False),
            total_elements_checked=raw.get("totalChecked", 0),
            dominant_surfaces=raw.get("dominantSurfaces", []),
        )

    def audit(
        self,
        page: Page,
        url: str,
        wait_network_idle: bool = True,
    ) -> ThemeFlawReport:
        """Navigates to URL, applies custom CSS if provided, and audits for theme flaws."""
        if wait_network_idle:
            safe_goto(page, url, wait_until="networkidle", timeout=30000)
        else:
            safe_goto(page, url, wait_until="domcontentloaded", timeout=30000)

        return self.audit_page(page, url=url)


def theme_report_to_dict(report: ThemeFlawReport) -> Dict[str, Any]:
    """Serializes ThemeFlawReport into a compact dictionary for CLI/TOON output."""
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
        "dominant_surfaces": report.dominant_surfaces,
    }
