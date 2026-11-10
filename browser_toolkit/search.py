from typing import Any, Dict, List, Optional
from playwright.sync_api import Page
from .selector_generator import JS_SELECTOR_SYNTHESIZER

JS_SEARCH_DOM = """
(query) => {
    const textQuery = (query.text || '').toLowerCase().trim();
    const keyword = (query.keyword || '').toLowerCase().trim();
    const role = (query.role || '').toLowerCase().trim();
    const tag = (query.tag || '').toLowerCase().trim();

    const allEls = document.querySelectorAll(tag || '*');
    const matched = [];

    for (const el of allEls) {
        if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'NOSCRIPT') continue;

        let match = false;
        let reason = '';

        // Match text content
        if (textQuery) {
            const directText = Array.from(el.childNodes)
                .filter(n => n.nodeType === Node.TEXT_NODE)
                .map(n => n.textContent.trim())
                .join(' ')
                .toLowerCase();

            if (directText.includes(textQuery)) {
                match = true;
                reason = `Direct text contains "${textQuery}"`;
            } else if ((el.textContent || '').toLowerCase().includes(textQuery) && el.children.length < 5) {
                match = true;
                reason = `Content contains "${textQuery}"`;
            }
        }

        // Match keyword in attributes/classes
        if (keyword) {
            const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
            const id = (el.id || '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();

            if (cls.includes(keyword)) {
                match = true;
                reason = `Class contains "${keyword}"`;
            } else if (id.includes(keyword)) {
                match = true;
                reason = `ID contains "${keyword}"`;
            } else if (aria.includes(keyword)) {
                match = true;
                reason = `aria-label contains "${keyword}"`;
            }
        }

        // Match role
        if (role) {
            const elRole = (el.getAttribute('role') || '').toLowerCase();
            if (elRole === role) {
                match = true;
                reason = `Role is "${role}"`;
            }
        }

        if (match) {
            const comp = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const selectors = window._synthesizeSelectorForElement ? window._synthesizeSelectorForElement(el) : [];

            matched.push({
                tagName: el.tagName.toLowerCase(),
                id: el.id || null,
                className: (typeof el.className === 'string' ? el.className.slice(0, 120) : null),
                ariaLabel: el.getAttribute('aria-label') || null,
                role: el.getAttribute('role') || null,
                textSnippet: (el.textContent || '').trim().slice(0, 80),
                reason: reason,
                visible: comp.display !== 'none' && comp.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
                rect: { width: Math.round(rect.width), height: Math.round(rect.height) },
                selectors: selectors.slice(0, 5)
            });

            if (matched.length >= 25) break;
        }
    }

    return matched;
}
"""


def search_dom(
    page: Page,
    text: Optional[str] = None,
    keyword: Optional[str] = None,
    role: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # Ensure selector synthesizer is injected
    page.evaluate(JS_SELECTOR_SYNTHESIZER)

    query = {
        "text": text or "",
        "keyword": keyword or "",
        "role": role or "",
        "tag": tag or "",
    }

    return page.evaluate(JS_SEARCH_DOM, query)
