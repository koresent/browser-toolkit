"""
DOM Semantic Role Mapper: Traverses the live DOM of a target site,
classifying elements into functional UI roles for Gruvbox theme generation.
"""

from typing import Any, Dict, List
from playwright.sync_api import Page
from .selector_generator import JS_SELECTOR_SYNTHESIZER

JS_MAP_SEMANTIC_ROLES = r"""() => {
    const roles = {
        baseSurfaces: [],
        elevatedSurfaces: [],
        floatingSurfaces: [],
        headings: [],
        bodyText: [],
        metaText: [],
        links: [],
        formControls: [],
        codeBlocks: [],
        bordersAndDividers: [],
        iconsAndSvg: []
    };

    function getSelector(el) {
        if (window._synthesizeSelectorForElement) {
            const cands = window._synthesizeSelectorForElement(el);
            if (cands && cands.length > 0) return cands[0].selector;
        }
        const tag = el.tagName.toLowerCase();
        if (el.id && !/[0-9_-]{8,}/.test(el.id)) return `#${CSS.escape(el.id)}`;
        if (typeof el.className === 'string' && el.className.trim()) {
            const first = el.className.trim().split(/\s+/)[0];
            if (first && !/[0-9_-]{8,}/.test(first)) return `.${CSS.escape(first)}`;
        }
        return tag;
    }

    const seenSelectors = new Set();
    function addUnique(bucket, sel, info = {}) {
        if (!sel || seenSelectors.has(sel)) return;
        seenSelectors.add(sel);
        bucket.push({ selector: sel, ...info });
    }

    const allEls = document.querySelectorAll('*');
    for (let i = 0; i < allEls.length; i++) {
        const el = allEls[i];
        const tag = el.tagName.toLowerCase();
        if (['script', 'style', 'noscript', 'meta', 'link'].includes(tag)) continue;

        const comp = window.getComputedStyle(el);
        if (comp.display === 'none' || comp.visibility === 'hidden') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;

        const cls = typeof el.className === 'string' ? el.className.toLowerCase() : '';
        const id = (el.id || '').toLowerCase();
        const role = (el.getAttribute('role') || '').toLowerCase();

        // 1. Base Surfaces (canvas, body, main layout wrappers)
        if (tag === 'body' || tag === 'main' || role === 'main' || cls.includes('layout__body') || cls.includes('page-container') || cls.includes('app-content')) {
            addUnique(roles.baseSurfaces, getSelector(el), { tag, sample: el.tagName });
        }

        // 2. Elevated Surfaces (header, navbar, sidebar, nav)
        if (tag === 'header' || tag === 'nav' || tag === 'aside' || role === 'navigation' || role === 'banner' ||
            cls.includes('header') || cls.includes('navbar') || cls.includes('sidebar') || cls.includes('topbar')) {
            addUnique(roles.elevatedSurfaces, getSelector(el), { tag });
        }

        // 3. Floating Surfaces (modals, dropdowns, popovers, cards)
        if (role === 'dialog' || role === 'menu' || role === 'tooltip' ||
            cls.includes('modal') || cls.includes('dropdown') || cls.includes('popup') || cls.includes('card') || cls.includes('box')) {
            addUnique(roles.floatingSurfaces, getSelector(el), { tag });
        }

        // 4. Headings
        if (/^h[1-6]$/.test(tag) || role === 'heading' || cls.includes('title') || cls.includes('heading')) {
            addUnique(roles.headings, getSelector(el), { tag, text: (el.textContent || '').trim().slice(0, 30) });
        }

        // 5. Meta / Secondary Text
        if (tag === 'time' || cls.includes('date') || cls.includes('meta') || cls.includes('muted') || cls.includes('subtitle') || cls.includes('count')) {
            addUnique(roles.metaText, getSelector(el), { tag });
        }

        // 6. Form Controls
        if (['input', 'textarea', 'select', 'button'].includes(tag) || role === 'button') {
            addUnique(roles.formControls, getSelector(el), { tag });
        }

        // 7. Code Blocks
        if (tag === 'pre' || tag === 'code' || cls.includes('highlight') || cls.includes('code') || cls.includes('syntax')) {
            addUnique(roles.codeBlocks, getSelector(el), { tag });
        }

        // 8. Borders & Dividers
        if (tag === 'hr' || (parseFloat(comp.borderBottomWidth) > 0 && (comp.borderBottomStyle === 'solid' || comp.borderBottomStyle === 'dashed'))) {
            if (cls.includes('divider') || cls.includes('separator') || cls.includes('border') || tag === 'hr') {
                addUnique(roles.bordersAndDividers, getSelector(el), { tag });
            }
        }

        // 9. Icons & SVGs
        if (tag === 'svg' || cls.includes('icon') || cls.includes('octicon')) {
            addUnique(roles.iconsAndSvg, getSelector(el), { tag });
        }
    }

    // Limit counts
    for (const key of Object.keys(roles)) {
        roles[key] = roles[key].slice(0, 15);
    }

    return roles;
}
"""


def map_site_roles(page: Page, url: str) -> Dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    page.evaluate(JS_SELECTOR_SYNTHESIZER)
    roles = page.evaluate(JS_MAP_SEMANTIC_ROLES)
    return {"url": url, "roles": roles}
