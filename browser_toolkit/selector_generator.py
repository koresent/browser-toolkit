"""
DOM Selector Synthesizer: Generates resilient, minimal, and unique CSS selectors
for elements based on semantic attributes, ARIA roles, data-test attributes,
and structural hierarchy, avoiding volatile framework hashes (CSS Modules, Tailwind random hashes, etc.).
"""

JS_SELECTOR_SYNTHESIZER = r"""
(() => {
    function isStableId(id) {
        if (!id) return false;
        // Skip auto-generated IDs like react-aria-1234, :r1:, ember123, etc.
        if (/^[a-zA-Z0-9_-]{25,}$/.test(id)) return false;
        if (/^(react-aria|ember|ng-|__|\:r)/i.test(id)) return false;
        if (/[0-9]{4,}/.test(id)) return false;
        return true;
    }

    function getStableClasses(el) {
        if (typeof el.className !== 'string' || !el.className) return [];
        return el.className.split(/\\s+/)
            .filter(c => c && c.length > 2)
            .filter(c => {
                // Filter out volatile hashed classes, e.g. Component-module__hash123
                if (/^[a-zA-Z0-9_-]{20,}$/.test(c)) return false;
                if (/_[a-zA-Z0-9]{5,}$/.test(c)) return false;
                return true;
            });
    }

    function generateCandidateSelectors(el) {
        const candidates = [];
        const tag = el.tagName.toLowerCase();

        for (const attr of ['data-testid', 'data-test', 'data-component', 'data-id', 'data-target', 'data-name']) {
            const val = el.getAttribute(attr);
            if (val) {
                candidates.push(`[${attr}="${val}"]`);
                candidates.push(`${tag}[${attr}="${val}"]`);
            }
        }

        if (isStableId(el.id)) {
            candidates.push(`#${CSS.escape(el.id)}`);
            candidates.push(`${tag}#${CSS.escape(el.id)}`);
        }

        const role = el.getAttribute('role');
        const ariaLabel = el.getAttribute('aria-label');
        if (role && ariaLabel) {
            candidates.push(`[role="${role}"][aria-label="${ariaLabel}"]`);
            candidates.push(`${tag}[role="${role}"][aria-label="${ariaLabel}"]`);
        } else if (ariaLabel) {
            candidates.push(`[aria-label="${ariaLabel}"]`);
            candidates.push(`${tag}[aria-label="${ariaLabel}"]`);
        } else if (role) {
            candidates.push(`${tag}[role="${role}"]`);
        }

        const stableClasses = getStableClasses(el);
        for (const c of stableClasses.slice(0, 3)) {
            candidates.push(`.${CSS.escape(c)}`);
            candidates.push(`${tag}.${CSS.escape(c)}`);
        }

        // Match stable CSS module prefix without the randomized hash suffix
        if (typeof el.className === 'string') {
            const moduleMatches = el.className.match(/([a-zA-Z0-9]+-module)__[a-zA-Z0-9_-]+/g);
            if (moduleMatches) {
                for (const m of moduleMatches) {
                    const prefix = m.split('__')[0];
                    candidates.push(`${tag}[class*="${prefix}__"]`);
                    candidates.push(`[class*="${prefix}__"]`);
                }
            }
        }

        if (el.parentElement && el.parentElement !== document.body) {
            const p = el.parentElement;
            const pTag = p.tagName.toLowerCase();
            const pId = isStableId(p.id) ? `#${CSS.escape(p.id)}` : '';
            const pClasses = getStableClasses(p);
            const pClass = pClasses.length > 0 ? `.${CSS.escape(pClasses[0])}` : '';

            const parentPrefix = pId || (pClass ? `${pTag}${pClass}` : pTag);
            for (const cand of candidates.slice(0, 4)) {
                candidates.push(`${parentPrefix} > ${cand}`);
                candidates.push(`${parentPrefix} ${cand}`);
            }
        }

        return [...new Set(candidates)];
    }

    window._synthesizeSelectorForElement = function(el) {
        const candidates = generateCandidateSelectors(el);

        // Score candidates based on uniqueness and stability
        const scored = [];
        for (const sel of candidates) {
            try {
                const matches = document.querySelectorAll(sel);
                if (matches.length === 1 && matches[0] === el) {
                    // Perfectly unique!
                    let score = 100;
                    if (sel.includes('data-test')) score += 30;
                    if (sel.includes('aria-label')) score += 25;
                    if (sel.includes('#')) score += 20;
                    if (sel.includes('-module')) score -= 10;
                    if (sel.includes(' > ')) score -= 5;
                    scored.push({ selector: sel, count: 1, score: score });
                } else if (matches.length > 1) {
                    let score = 50 - matches.length;
                    scored.push({ selector: sel, count: matches.length, score: score });
                }
            } catch (_) {}
        }

        scored.sort((a, b) => b.score - a.score);
        return scored;
    };
})();
"""
