from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

JS_TEST_RULE_IMPACT = """
(cssText) => {
    // 1. Parse rule to extract selectors
    const sheet = new CSSStyleSheet();
    try {
        sheet.replaceSync(cssText);
    } catch (e) {
        return { parseError: e.message, matchedElements: [] };
    }

    const selectors = [];
    for (const r of sheet.cssRules) {
        if (r.selectorText) selectors.push(r.selectorText);
    }

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const viewportArea = viewportWidth * viewportHeight;

    const matched = [];
    let highImpactCount = 0;

    for (const sel of selectors) {
        try {
            const els = document.querySelectorAll(sel);
            for (let i = 0; i < Math.min(els.length, 10); i++) {
                const el = els[i];
                const rect = el.getBoundingClientRect();
                const area = rect.width * rect.height;
                const ratio = viewportArea > 0 ? (area / viewportArea) : 0;

                const isBig = ratio > 0.25; // occupies > 25% of viewport
                if (isBig) highImpactCount++;

                matched.push({
                    selector: sel,
                    tagName: el.tagName.toLowerCase(),
                    id: el.id || null,
                    className: (typeof el.className === 'string' ? el.className.slice(0, 100) : null),
                    textSnippet: (el.textContent || '').trim().slice(0, 60),
                    dimensions: { width: Math.round(rect.width), height: Math.round(rect.height) },
                    viewportRatioPercent: Math.round(ratio * 100),
                    isLargeElement: isBig
                });
            }
        } catch (_) {}
    }

    return {
        parseError: null,
        totalMatchedCount: matched.length,
        highImpactCount: highImpactCount,
        matched: matched
    };
}
"""


def test_rule_impact(
    page: Page,
    css_rule: str,
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    # 1. Analyze target elements before injection
    pre_analysis = page.evaluate(JS_TEST_RULE_IMPACT, css_rule)

    out_path = Path(output_dir or "./audit-results/rule-test").resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    before_img = out_path / "before_rule.png"
    page.screenshot(path=str(before_img))

    # 2. Inject CSS rule
    page.add_style_tag(content=css_rule)
    page.wait_for_timeout(500)

    after_img = out_path / "after_rule.png"
    page.screenshot(path=str(after_img))

    return {
        "css_rule": css_rule,
        "impact": pre_analysis,
        "screenshot_before": str(before_img),
        "screenshot_after": str(after_img),
    }
