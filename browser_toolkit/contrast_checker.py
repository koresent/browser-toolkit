from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

JS_CONTRAST_ANALYSIS = r"""() => {
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
            if (parsed && parsed.a > 0.5) {
                return parsed;
            }
            cur = cur.parentElement;
        }
        // Fallback default Gruvbox dark bg if not found
        return { r: 40, g: 40, b: 40, a: 1.0 }; // #282828
    }

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const issues = [];
    const passing = [];
    let checkedCount = 0;

    while (walker.nextNode()) {
        const node = walker.currentNode;
        const text = node.textContent.trim();
        if (!text || text.length < 2) continue;

        const parent = node.parentElement;
        if (!parent) continue;
        const tag = parent.tagName.toLowerCase();
        if (['script', 'style', 'svg', 'noscript'].includes(tag)) continue;

        const comp = window.getComputedStyle(parent);
        if (comp.display === 'none' || comp.visibility === 'hidden') continue;
        const rect = parent.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        const fg = parseRgb(comp.color);
        if (!fg) continue;
        const bg = getEffectiveBg(parent);

        const ratio = getContrastRatio(fg, bg);
        checkedCount++;

        const fontSize = parseFloat(comp.fontSize) || 16;
        const isBold = parseInt(comp.fontWeight) >= 600 || comp.fontWeight === 'bold';
        const isLarge = fontSize >= 24 || (fontSize >= 18.66 && isBold);
        const threshold = isLarge ? 3.0 : 4.5;

        const item = {
            tagName: tag,
            className: typeof parent.className === 'string' ? parent.className.slice(0, 60) : '',
            id: parent.id || '',
            textSnippet: text.slice(0, 50),
            fg: `rgb(${fg.r}, ${fg.g}, ${fg.b})`,
            bg: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
            contrastRatio: Math.round(ratio * 10) / 10,
            requiredRatio: threshold,
            isLargeText: isLarge
        };

        if (ratio < threshold) {
            issues.push(item);
            if (issues.length >= 25) break;
        } else {
            if (passing.length < 5) passing.push(item);
        }
    }

    return {
        totalChecked: checkedCount,
        failedCount: issues.length,
        issues: issues,
        samplePassing: passing
    };
}
"""


def check_page_contrast(page: Page, css_content: Optional[str] = None) -> Dict[str, Any]:
    if css_content:
        page.add_style_tag(content=css_content)
        page.wait_for_timeout(500)

    res = page.evaluate(JS_CONTRAST_ANALYSIS)
    return res
