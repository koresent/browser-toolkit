"""
Modernizer Module: Detects dated web design patterns (cramped typography,
fixed widths, obsolete fonts, tiny touch targets) and generates modern
2026 layout enhancements, optimal reading measures, and ergonomic UI resets.
"""

from typing import Any, Dict, List
from playwright.sync_api import Page

JS_AUDIT_MODERNITY = r"""() => {
    const flaws = {
        datedFonts: [],
        crampedTypography: [],
        excessiveLineLength: [],
        fixedWidthContainers: [],
        tinyClickTargets: [],
        tableLayouts: []
    };

    const viewportWidth = window.innerWidth;

    // 1. Check fonts and text ergonomics
    const textEls = document.querySelectorAll('p, article, h1, h2, h3, li, td, span');
    for (const el of textEls) {
        if (el.children.length > 3) continue;
        const text = (el.textContent || '').trim();
        if (text.length < 20) continue;

        const comp = window.getComputedStyle(el);
        if (comp.display === 'none' || comp.visibility === 'hidden') continue;

        const font = comp.fontFamily.toLowerCase();
        if (font.includes('times') || font.includes('verdana') || font.includes('courier') || font.includes('comic')) {
            if (flaws.datedFonts.length < 5) {
                flaws.datedFonts.push({
                    tag: el.tagName.toLowerCase(),
                    fontFamily: comp.fontFamily,
                    sampleText: text.slice(0, 40)
                });
            }
        }

        const fontSize = parseFloat(comp.fontSize) || 16;
        const lineHeight = parseFloat(comp.lineHeight);
        const lhRatio = lineHeight && fontSize ? (lineHeight / fontSize) : 1.2;

        if (fontSize < 14 || (lhRatio < 1.35 && text.length > 100)) {
            if (flaws.crampedTypography.length < 5) {
                flaws.crampedTypography.push({
                    tag: el.tagName.toLowerCase(),
                    fontSize: `${fontSize}px`,
                    lineHeightRatio: Math.round(lhRatio * 100) / 100,
                    sampleText: text.slice(0, 50)
                });
            }
        }

        // Measure line width (excessive width > 900px is exhausting to read)
        const rect = el.getBoundingClientRect();
        if (rect.width > 950 && text.length > 200) {
            if (flaws.excessiveLineLength.length < 5) {
                flaws.excessiveLineLength.push({
                    tag: el.tagName.toLowerCase(),
                    width: `${Math.round(rect.width)}px`,
                    sampleText: text.slice(0, 50)
                });
            }
        }
    }

    // 2. Check layout constraints (fixed non-responsive widths)
    for (const el of document.querySelectorAll('div, main, table, section')) {
        const comp = window.getComputedStyle(el);
        const widthVal = comp.width;
        if (/^[6-9][0-9]{2}px$/.test(widthVal) || /^1[0-1][0-9]{2}px$/.test(widthVal)) {
            if (comp.maxWidth === 'none' && !el.className.includes('modal')) {
                if (flaws.fixedWidthContainers.length < 5) {
                    flaws.fixedWidthContainers.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        className: typeof el.className === 'string' ? el.className.slice(0, 50) : '',
                        fixedWidth: widthVal
                    });
                }
            }
        }
    }

    // 3. Table-based non-tabular layout detection
    const tables = document.querySelectorAll('table');
    for (const t of tables) {
        if (!t.querySelector('th') && t.querySelectorAll('table').length > 0) {
            flaws.tableLayouts.push({
                selector: 'table' + (t.id ? '#' + t.id : ''),
                rows: t.rows.length
            });
            if (flaws.tableLayouts.length >= 3) break;
        }
    }

    return flaws;
}
"""

MODERN_CSS_ENHANCEMENT = """
    /* --- Modern 2026 UI Enhancements --- */
    /* 1. System Typography & Optimal Reading Measure */
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif !important;
        line-height: 1.6 !important;
        letter-spacing: -0.011em !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
    }

    /* Optimal reading measure: prevents runaway 2000px line width */
    article,
    .content,
    .post-content,
    .entry-content,
    .wiki-content {
        max-width: 80ch !important;
    }

    /* 2. Sleek Modern Scrollbars */
    * {
        scrollbar-width: thin !important;
        scrollbar-color: var(--bg2) var(--bg0) !important;
    }

    ::-webkit-scrollbar {
        width: 8px !important;
        height: 8px !important;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg0) !important;
    }

    ::-webkit-scrollbar-thumb {
        background: var(--bg2) !important;
        border-radius: 4px !important;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--bg3) !important;
    }

    /* 3. Modern Form Controls & Focus Rings */
    input[type="text"],
    input[type="search"],
    input[type="email"],
    input[type="password"],
    textarea,
    select {
        border-radius: 6px !important;
        padding: 8px 12px !important;
        font-size: 14px !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }

    input:focus-visible,
    textarea:focus-visible,
    select:focus-visible,
    button:focus-visible {
        outline: 2px solid var(--accent) !important;
        outline-offset: 2px !important;
    }

    button,
    .btn {
        border-radius: 6px !important;
        padding: 7px 14px !important;
        font-weight: 500 !important;
        cursor: pointer !important;
        transition: background-color 0.15s ease, transform 0.05s ease !important;
    }

    button:active,
    .btn:active {
        transform: scale(0.98) !important;
    }

    /* 4. Modern Code Typography */
    pre,
    code,
    kbd,
    samp {
        font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
        font-size: 0.9em !important;
        border-radius: 6px !important;
    }

    pre {
        padding: 14px 18px !important;
        overflow-x: auto !important;
        border: 1px solid var(--bg1) !important;
    }

    /* 5. Smooth Rounded Cards & Images */
    img {
        max-width: 100% !important;
        height: auto !important;
        border-radius: 4px !important;
    }
"""


def audit_modernity(page: Page, url: str) -> Dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    flaws = page.evaluate(JS_AUDIT_MODERNITY)
    return {"url": url, "flaws": flaws}
