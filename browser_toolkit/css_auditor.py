import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page


@dataclass
class SelectorMatch:
    selector: str
    count: int
    samples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DeadSelector:
    selector: str
    suggestions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CSSAuditResult:
    total_selectors: int = 0
    matched: List[SelectorMatch] = field(default_factory=list)
    dead: List[DeadSelector] = field(default_factory=list)
    invalid: List[Dict[str, str]] = field(default_factory=list)
    parse_error: Optional[str] = None


JS_AUDIT_CSS = """
(cssText) => {
    const sheet = new CSSStyleSheet();
    try {
        sheet.replaceSync(cssText);
    } catch (e) {
        return { parseError: e.message, results: [] };
    }

    const rawSelectors = [];
    function walk(rules) {
        for (const r of rules) {
            if (r.selectorText) {
                rawSelectors.push(r.selectorText);
            }
            if (r.cssRules) {
                walk(r.cssRules);
            }
        }
    }
    walk(sheet.cssRules);

    // Split selector lists (taking care of parentheses like :has(), :is())
    function splitSelectorList(listStr) {
        const parts = [];
        let current = '';
        let depth = 0;
        let inQuotes = false;
        let quoteChar = '';

        for (let i = 0; i < listStr.length; i++) {
            const char = listStr[i];
            if ((char === '"' || char === "'") && listStr[i-1] !== '\\\\') {
                if (!inQuotes) {
                    inQuotes = true;
                    quoteChar = char;
                } else if (quoteChar === char) {
                    inQuotes = false;
                }
            }
            if (!inQuotes) {
                if (char === '(' || char === '[') depth++;
                else if (char === ')' || char === ']') depth--;
                else if (char === ',' && depth === 0) {
                    if (current.trim()) parts.push(current.trim());
                    current = '';
                    continue;
                }
            }
            current += char;
        }
        if (current.trim()) parts.push(current.trim());
        return parts;
    }

    const uniqueSelectors = new Set();
    for (const raw of rawSelectors) {
        for (const sub of splitSelectorList(raw)) {
            uniqueSelectors.add(sub);
        }
    }

    const results = [];
    for (const sel of uniqueSelectors) {
        try {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
                const samples = [];
                for (let i = 0; i < Math.min(els.length, 3); i++) {
                    const el = els[i];
                    const comp = window.getComputedStyle(el);
                    samples.push({
                        tagName: el.tagName.toLowerCase(),
                        id: el.id || null,
                        className: (typeof el.className === 'string') ? el.className.slice(0, 100) : null,
                        display: comp.display,
                        visibility: comp.visibility,
                        text: (el.textContent || '').trim().slice(0, 60)
                    });
                }
                results.push({
                    selector: sel,
                    count: els.length,
                    status: 'matched',
                    samples: samples
                });
            } else {
                // Selector is dead. Try to find potential candidate elements.
                const suggestions = [];
                
                // Extract keywords from selector (classes, IDs, attributes)
                const keywords = sel.match(/[a-zA-Z0-9_-]{4,}/g) || [];
                const searchKeys = [...new Set(keywords)].filter(k => 
                    !['div', 'span', 'true', 'false', 'none', 'block', 'flex', 'module', 'hover', 'container', 'has', 'not'].includes(k.toLowerCase())
                );

                for (const kw of searchKeys.slice(0, 3)) {
                    try {
                        const candidates = document.querySelectorAll(`[class*="${kw}" i], [id*="${kw}" i], [aria-label*="${kw}" i]`);
                        for (let j = 0; j < Math.min(candidates.length, 3); j++) {
                            const c = candidates[j];
                            suggestions.push({
                                matchedKeyword: kw,
                                tagName: c.tagName.toLowerCase(),
                                className: (typeof c.className === 'string') ? c.className.slice(0, 100) : null,
                                id: c.id || null,
                                ariaLabel: c.getAttribute('aria-label') || null
                            });
                        }
                    } catch (_) {}
                }

                results.push({
                    selector: sel,
                    count: 0,
                    status: 'dead',
                    suggestions: suggestions
                });
            }
        } catch (err) {
            results.push({
                selector: sel,
                count: 0,
                status: 'invalid',
                error: err.message
            });
        }
    }

    return { parseError: null, results: results };
}
"""


def audit_css_on_page(page: Page, css_content: str) -> CSSAuditResult:
    """
    Applies the CSS on the page and tests all selectors for presence in the DOM.
    """
    # First inject the style tag so styles take visual effect
    page.add_style_tag(content=css_content)

    # Run the in-page auditor script
    raw = page.evaluate(JS_AUDIT_CSS, css_content)

    result = CSSAuditResult()
    if raw.get("parseError"):
        result.parse_error = raw["parseError"]
        return result

    results = raw.get("results", [])
    result.total_selectors = len(results)

    for item in results:
        status = item.get("status")
        sel = item.get("selector", "")
        if status == "matched":
            result.matched.append(
                SelectorMatch(
                    selector=sel,
                    count=item.get("count", 0),
                    samples=item.get("samples", []),
                )
            )
        elif status == "dead":
            result.dead.append(
                DeadSelector(
                    selector=sel,
                    suggestions=item.get("suggestions", []),
                )
            )
        elif status == "invalid":
            result.invalid.append({"selector": sel, "error": item.get("error", "Unknown error")})

    return result
