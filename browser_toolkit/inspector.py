from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

from .interaction import execute_action_sequence
from .parser import parse_userstyle

JS_INSPECT_ELEMENTS = r"""
([sel, opts]) => {
    const els = document.querySelectorAll(sel);
    if (els.length === 0) return { count: 0, items: [] };

    const reqProps = opts.properties || [];
    const includeRules = Boolean(opts.includeRules);
    const pseudo = opts.pseudo || null;

    function selectorMatchesElement(el, selectorText) {
        try {
            if (el.matches(selectorText)) return true;
        } catch (_) {}

        // Strip trailing pseudo-element suffix because Element.matches() rejects ::before/::after.
        if (pseudo) {
            const normPseudo = pseudo.startsWith('::') ? pseudo : `::${pseudo.replace(/^:/, '')}`;
            const altPseudo = `:${normPseudo.slice(2)}`;
            for (const part of selectorText.split(',')) {
                const trimmed = part.trim();
                let base = null;
                if (trimmed.endsWith(normPseudo)) {
                    base = trimmed.slice(0, -normPseudo.length).trim() || '*';
                } else if (trimmed.endsWith(altPseudo)) {
                    base = trimmed.slice(0, -altPseudo.length).trim() || '*';
                }
                if (base) {
                    try {
                        if (el.matches(base)) return true;
                    } catch (_) {}
                }
            }
        }
        return false;
    }

    function getMatchedRules(el) {
        const matched = [];
        for (const sheet of document.styleSheets) {
            try {
                const rules = sheet.cssRules || sheet.rules;
                if (!rules) continue;
                for (const rule of rules) {
                    if (rule.type === CSSRule.STYLE_RULE && rule.selectorText) {
                        if (selectorMatchesElement(el, rule.selectorText)) {
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
"""


def inject_css_or_file(page: Page, css: str, target_url: Optional[str] = None) -> None:
    """Injects raw CSS or compiled UserStyle rules matching the active page URL."""
    css_content = css
    p_css = Path(css)
    if p_css.exists() and p_css.is_file():
        info = parse_userstyle(p_css)
        css_content = info.get_combined_css_for_url(target_url or page.url)
    page.add_style_tag(content=css_content)


def inspect_page_selector(
    page: Page,
    selector: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    properties: Optional[List[str]] = None,
    include_rules: bool = False,
    css: Optional[str] = None,
    pseudo: Optional[str] = None,
    target_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspects live elements matching selector, returning styles, custom vars, and optional CSS rules."""
    if css:
        inject_css_or_file(page, css, target_url=target_url)

    if actions:
        execute_action_sequence(page, actions)

    eval_opts = {
        "properties": properties or [],
        "includeRules": bool(include_rules),
        "pseudo": pseudo,
    }
    return page.evaluate(JS_INSPECT_ELEMENTS, [selector, eval_opts])
