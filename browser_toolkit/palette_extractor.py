import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

JS_EXTRACT_PAGE_PALETTE = r"""() => {
    // 1. Extract CSS custom properties (variables) defined on the page
    const cssVars = {};
    for (const sheet of document.styleSheets) {
        try {
            for (const rule of sheet.cssRules) {
                if (rule.style) {
                    for (let i = 0; i < rule.style.length; i++) {
                        const prop = rule.style[i];
                        if (prop.startsWith('--')) {
                            const val = rule.style.getPropertyValue(prop).trim();
                            if (val && !cssVars[prop]) {
                                cssVars[prop] = {
                                    selector: rule.selectorText || ':root',
                                    value: val
                                };
                            }
                        }
                    }
                }
            }
        } catch(_) {}
    }

    // Classify CSS variables into color-related
    const colorVars = [];
    const colorRegex = /(color|bg|background|canvas|surface|border|text|fg|fill|stroke|theme|dark|light)/i;
    for (const [varName, data] of Object.entries(cssVars)) {
        if (colorRegex.test(varName) || /^(#|rgb|hsl)/i.test(data.value)) {
            colorVars.push({
                name: varName,
                value: data.value,
                selector: data.selector
            });
        }
    }

    // Helper: rgb to hex
    function rgbToHex(rgbStr) {
        if (!rgbStr || rgbStr === 'transparent' || rgbStr === 'rgba(0, 0, 0, 0)') return null;
        const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!match) return rgbStr;
        const r = parseInt(match[1]).toString(16).padStart(2, '0');
        const g = parseInt(match[2]).toString(16).padStart(2, '0');
        const b = parseInt(match[3]).toString(16).padStart(2, '0');
        return `#${r}${g}${b}`.toLowerCase();
    }

    // 2. Scan computed styles across DOM
    const bgFreq = {};
    const textFreq = {};
    const borderFreq = {};

    const allEls = document.querySelectorAll('*');
    for (let i = 0; i < allEls.length; i++) {
        const el = allEls[i];
        const tag = el.tagName.toLowerCase();
        if (['script', 'style', 'svg', 'path', 'noscript'].includes(tag)) continue;

        const comp = window.getComputedStyle(el);
        if (comp.display === 'none' || comp.visibility === 'hidden') continue;

        const clsStr = typeof el.className === 'string' && el.className ? el.className.trim().split(/\s+/)[0] : '';
        const sampleName = tag + (clsStr ? '.' + clsStr : '');

        // Background
        const bgHex = rgbToHex(comp.backgroundColor);
        if (bgHex) {
            if (!bgFreq[bgHex]) bgFreq[bgHex] = { count: 0, samples: [] };
            bgFreq[bgHex].count++;
            if (bgFreq[bgHex].samples.length < 3) {
                bgFreq[bgHex].samples.push(sampleName);
            }
        }

        // Text color
        if (el.textContent && el.textContent.trim().length > 0 && el.children.length === 0) {
            const fgHex = rgbToHex(comp.color);
            if (fgHex) {
                if (!textFreq[fgHex]) textFreq[fgHex] = { count: 0, samples: [] };
                textFreq[fgHex].count++;
                if (textFreq[fgHex].samples.length < 3) {
                    textFreq[fgHex].samples.push(sampleName);
                }
            }
        }

        // Border color
        if (parseFloat(comp.borderWidth) > 0) {
            const bHex = rgbToHex(comp.borderColor);
            if (bHex) {
                if (!borderFreq[bHex]) borderFreq[bHex] = { count: 0, samples: [] };
                borderFreq[bHex].count++;
                if (borderFreq[bHex].samples.length < 3) {
                    borderFreq[bHex].samples.push(sampleName);
                }
            }
        }
    }

    function sortFreq(dict) {
        return Object.entries(dict)
            .map(([color, data]) => ({ color, count: data.count, samples: data.samples }))
            .sort((a, b) => b.count - a.count);
    }

    // 3. Detect Icons / SVGs that need inversion
    const svgCount = document.querySelectorAll('svg').length;
    const imgIcons = [];
    for (const img of document.querySelectorAll('img')) {
        const rect = img.getBoundingClientRect();
        if (rect.width > 0 && rect.width <= 32 && rect.height <= 32) {
            imgIcons.push({
                src: img.src.slice(0, 100),
                dimensions: `${Math.round(rect.width)}x${Math.round(rect.height)}`
            });
            if (imgIcons.length >= 5) break;
        }
    }

    return {
        siteColorVariables: colorVars,
        backgroundColors: sortFreq(bgFreq).slice(0, 10),
        textColors: sortFreq(textFreq).slice(0, 10),
        borderColors: sortFreq(borderFreq).slice(0, 10),
        svgCount: svgCount,
        monochromeImgIcons: imgIcons
    };
}
"""


def extract_site_palette(page: Page, url: str) -> Dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    raw = page.evaluate(JS_EXTRACT_PAGE_PALETTE)
    return {
        "url": url,
        "site_color_variables": raw.get("siteColorVariables", []),
        "background_colors": raw.get("backgroundColors", []),
        "text_colors": raw.get("textColors", []),
        "border_colors": raw.get("borderColors", []),
        "svg_count": raw.get("svgCount", 0),
        "monochrome_img_icons": raw.get("monochromeImgIcons", []),
    }
