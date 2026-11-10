"""
CSS Color Extractor: Port and enhancement of Extract-ThemeColors-Universal.ps1.
Extracts strictly hardcoded color definitions from local CSS files or live website stylesheets,
filtering out non-color properties and var() usages to produce a clean color skeleton for theming.
"""

import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .navigation import safe_goto

COLOR_VAL_REGEX = re.compile(
    r"(#[0-9a-fA-F]{3,8}\b|rgba?\s*\(|hsla?\s*\(|color\s*\(|\b(transparent|currentcolor|white|black|red|green|blue|yellow|gray|grey)\b)",
    re.IGNORECASE,
)

COLOR_PROP_REGEX = re.compile(
    r"(^color$|-color$|^background(-color)?$|^fill$|^stroke$|^box-shadow$|^outline(-color)?$|^accent-color$)",
    re.IGNORECASE,
)


def filter_declarations(block_content: str) -> List[str]:
    declarations = block_content.split(";")
    kept: List[str] = []

    for decl in declarations:
        trimmed = decl.strip()
        if not trimmed or ":" not in trimmed:
            continue

        prop, val = [p.strip() for p in trimmed.split(":", 1)]

        # Rule 1: Skip if it references var(), as it is a usage rather than a hardcoded value
        if "var(" in val.lower():
            continue

        # Rule 2: Check for explicit hardcoded color values
        has_color = bool(COLOR_VAL_REGEX.search(val))

        # Rule 3: Check if property is inherently a color property (excluding image urls)
        is_color_prop = bool(COLOR_PROP_REGEX.search(prop))

        if has_color or (is_color_prop and "url(" not in val.lower()):
            kept.append(f"{prop}: {val};")

    return kept


def parse_css_structure(css_content: str) -> str:
    # Remove comments
    cleaned = re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)

    output: List[str] = []
    buffer: List[str] = []
    depth = 0
    selector = ""

    for char in cleaned:
        if char == "{":
            if depth == 0:
                selector = "".join(buffer).strip()
                buffer.clear()
            else:
                buffer.append(char)
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block = "".join(buffer).strip()
                buffer.clear()

                if "{" in block:
                    # Recursive for nested at-rules (@media, @supports)
                    nested = parse_css_structure(block)
                    if nested.strip():
                        indented = "\n".join(f"    {line}" for line in nested.splitlines() if line.strip())
                        output.append(f"{selector} {{\n{indented}\n}}")
                else:
                    kept_decls = filter_declarations(block)
                    if kept_decls:
                        lines_str = "\n".join(f"    {d}" for d in kept_decls)
                        output.append(f"{selector} {{\n{lines_str}\n}}")
            else:
                buffer.append(char)
        else:
            buffer.append(char)

    return "\n\n".join(output)


def extract_colors_from_file_or_url(
    target: str,
    output_path: Optional[str | Path] = None,
    profile_path: Optional[str] = None,
    use_profile: bool = True,
) -> str:
    """
    Accepts either a local .css file path OR a website URL.
    If URL: opens the page via Playwright Gecko and harvests all stylesheet rules.
    Extracts the distilled color skeleton and writes to output_path if specified.
    """
    target_path = Path(target)
    if target_path.exists() and target_path.is_file():
        raw_css = target_path.read_text(encoding="utf-8", errors="replace")
    elif target.startswith(("http://", "https://")):
        with ZenProfileContext(profile_path, use_profile=use_profile) as temp_prof:
            with sync_playwright() as p:
                launch_kwargs = {"headless": True}
                if temp_prof:
                    ctx = p.firefox.launch_persistent_context(user_data_dir=str(temp_prof), **launch_kwargs)
                    page = ctx.new_page() if not ctx.pages else ctx.pages[0]
                else:
                    b = p.firefox.launch(**launch_kwargs)
                    ctx = b.new_context()
                    page = ctx.new_page()

                try:
                    safe_goto(page, target, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2000)
                    raw_css = page.evaluate(
                        """() => {
                            const cssList = [];
                            for (const sheet of document.styleSheets) {
                                try {
                                    for (const r of sheet.cssRules) {
                                        cssList.push(r.cssText);
                                    }
                                } catch(_) {}
                            }
                            return cssList.join('\\n');
                        }"""
                    )
                finally:
                    ctx.close()
    else:
        raise FileNotFoundError(f"Target is neither an existing file nor a valid URL: {target}")

    result = parse_css_structure(raw_css)

    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")

    return result
