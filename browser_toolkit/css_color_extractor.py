"""
CSS Color Extractor: Port and enhancement of Extract-ThemeColors-Universal.ps1 and ecss.
Extracts strictly hardcoded color definitions from local CSS files, stdin, or live website stylesheets,
filtering out non-color properties and var() usages to produce a clean color skeleton and swatch counts for theming.
"""

from collections import Counter
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .navigation import safe_goto
from .browser_backend import safe_launch_persistent_context, safe_launch_browser

COLOR_VAL_REGEX = re.compile(
    r"(#[0-9a-fA-F]{3,8}\b|rgba?\s*\(|hsla?\s*\(|color\s*\(|\b(transparent|currentcolor|white|black|red|green|blue|yellow|gray|grey)\b)",
    re.IGNORECASE,
)

COLOR_PROP_REGEX = re.compile(
    r"(^color$|-color$|^background(-color)?$|^fill$|^stroke$|^box-shadow$|^outline(-color)?$|^accent-color$)",
    re.IGNORECASE,
)

SWATCH_HEX_REGEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
SWATCH_RGB_REGEX = re.compile(r"rgba?\(\s*(\d{1,3})\s*[,\s]\s*(\d{1,3})\s*[,\s]\s*(\d{1,3})")

NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "red": "#ff0000",
    "green": "#008000",
    "blue": "#0000ff",
    "yellow": "#ffff00",
    "gray": "#808080",
    "grey": "#808080",
}


def normalize_swatch_color(token: str) -> Optional[str]:
    """Converts #RGB / #RRGGBB / #RRGGBBAA / rgb(...) / named color into a normalized #rrggbb string."""
    token = token.strip().lower()
    if token in NAMED_COLORS:
        return NAMED_COLORS[token]
    if token.startswith("#"):
        hex_part = token[1:]
        if len(hex_part) in (3, 4):
            r, g, b = hex_part[0] * 2, hex_part[1] * 2, hex_part[2] * 2
            return f"#{r}{g}{b}".lower()
        if len(hex_part) in (6, 8):
            return f"#{hex_part[:6]}".lower()
        return None
    m = SWATCH_RGB_REGEX.match(token)
    if m:
        r, g, b = (max(0, min(255, int(m.group(i)))) for i in (1, 2, 3))
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def extract_color_swatches(css_text: str) -> List[Dict[str, Any]]:
    """Returns list of swatches sorted by frequency."""
    counts: Counter[str] = Counter()
    norm_map: Dict[str, str] = {}

    for m in SWATCH_HEX_REGEX.finditer(css_text):
        raw = m.group(0)
        norm = normalize_swatch_color(raw)
        if norm:
            low = raw.lower()
            counts[low] += 1
            norm_map[low] = norm

    for m in SWATCH_RGB_REGEX.finditer(css_text):
        raw = m.group(0) + ")"
        norm = normalize_swatch_color(raw)
        if norm:
            counts[raw] += 1
            norm_map[raw] = norm

    return [
        {"token": tok, "hex": norm_map[tok], "count": cnt}
        for tok, cnt in counts.most_common()
    ]


def copy_to_clipboard(content: str) -> bool:
    """Copies text to system clipboard via Wayland wl-copy, X11 xclip or xsel."""
    payload = content.encode("utf-8")
    if shutil.which("wl-copy"):
        try:
            subprocess.run(
                ["wl-copy"],
                input=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            pass
    if shutil.which("xclip"):
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            pass
    if shutil.which("xsel"):
        try:
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=payload,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.SubprocessError, OSError):
            pass
    return False


def filter_declarations(block_content: str) -> List[str]:
    declarations = block_content.split(";")
    kept: List[str] = []

    for decl in declarations:
        trimmed = decl.strip()
        if not trimmed or ":" not in trimmed:
            continue

        prop, val = [p.strip() for p in trimmed.split(":", 1)]

        # Skip if it references var(), as it is a usage rather than a hardcoded value
        if "var(" in val.lower():
            continue

        has_color = bool(COLOR_VAL_REGEX.search(val))
        is_color_prop = bool(COLOR_PROP_REGEX.search(prop))

        if has_color or (is_color_prop and "url(" not in val.lower()):
            kept.append(f"{prop}: {val};")

    return kept


def parse_css_structure(css_content: str) -> str:
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
    target: Optional[str] = "-",
    output_path: Optional[str | Path] = None,
    profile_path: Optional[str] = None,
    use_profile: bool = True,
    clipboard: bool = False,
) -> Dict[str, Any]:
    """
    Accepts a local .css file path, a website URL, or '-' to read from stdin.
    Extracts strictly hardcoded color declarations and swatch frequency stats.
    Optionally copies to system clipboard and writes to output_path.
    """
    target_str = (target or "-").strip()

    if target_str == "-" or not target_str:
        raw_css = sys.stdin.read()
        target_desc = "stdin"
    elif target_str.startswith(("http://", "https://")):
        with ZenProfileContext(profile_path, use_profile=use_profile) as temp_prof:
            with sync_playwright() as p:
                launch_kwargs = {"headless": True}
                if temp_prof:
                    ctx = safe_launch_persistent_context(p, user_data_dir=str(temp_prof), **launch_kwargs)
                    page = ctx.new_page() if not ctx.pages else ctx.pages[0]
                else:
                    b = safe_launch_browser(p, **launch_kwargs)
                    ctx = b.new_context()
                    page = ctx.new_page()

                try:
                    safe_goto(page, target_str, wait_until="domcontentloaded", timeout=30000)
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
        target_desc = target_str
    else:
        target_path = Path(target_str).resolve()
        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Target is neither an existing file nor a valid URL: {target_str}")
        raw_css = target_path.read_text(encoding="utf-8", errors="replace")
        target_desc = str(target_path)

    result = parse_css_structure(raw_css)
    swatches = extract_color_swatches(result)

    copied = False
    if clipboard and result:
        copied = copy_to_clipboard(result)

    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")

    return {
        "target": target_desc,
        "total_swatches": len(swatches),
        "swatches": swatches,
        "copied_to_clipboard": copied,
        "skeleton": result,
    }
