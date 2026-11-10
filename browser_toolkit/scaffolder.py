"""
Gruvbox Theme Scaffolder: Generates structured, high-quality .user.css boilerplate
prepopulated with site selectors, semantic role mapping, and Gruvbox variables.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .palettes import format_gruvbox_css
from .modernizer import MODERN_CSS_ENHANCEMENT


def format_selector_group(items: List[Dict[str, Any]], indent: str = "    ") -> str:
    selectors = [item["selector"] for item in items if item.get("selector")]
    if not selectors:
        return ""
    return (",\n" + indent).join(selectors)


def scaffold_gruvbox_theme(
    url: str,
    name: Optional[str] = None,
    variant: str = "dark",
    roles_data: Optional[Dict[str, Any]] = None,
    palette_data: Optional[Dict[str, Any]] = None,
    modernize: bool = True,
    output_path: Optional[str | Path] = None,
) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc or "example.com"
    site_slug = domain.split(".")[-2] if len(domain.split(".")) >= 2 else domain
    theme_title = name or site_slug.replace("-", " ").title()

    roles = (roles_data or {}).get("roles", {})
    vars_list = (palette_data or {}).get("site_color_variables", [])

    base_surfaces = format_selector_group(roles.get("baseSurfaces", []))
    elevated_surfaces = format_selector_group(roles.get("elevatedSurfaces", []))
    floating_surfaces = format_selector_group(roles.get("floatingSurfaces", []))
    headings = format_selector_group(roles.get("headings", []))
    meta_text = format_selector_group(roles.get("metaText", []))
    form_controls = format_selector_group(roles.get("formControls", []))
    code_blocks = format_selector_group(roles.get("codeBlocks", []))
    borders = format_selector_group(roles.get("bordersAndDividers", []))
    icons = format_selector_group(roles.get("iconsAndSvg", []))

    # Construct the file content
    lines = [
        "/* ==UserStyle==",
        f"@name         ✦ [{theme_title}] Gruvbox {variant.title()}",
        "@namespace    github.com/koresent/userstyles",
        "@version      1.0.0",
        f"@description  Gruvbox {variant.title()} theme for {theme_title}",
        "@author       Koresent",
        "@license      GPL-3.0",
        "@homepageURL  https://github.com/koresent/userstyles",
        "@supportURL   https://github.com/koresent/userstyles/issues",
        f"@updateURL    https://raw.githubusercontent.com/koresent/userstyles/refs/heads/main/{site_slug}/gruvbox.user.css",
        "==/UserStyle== */",
        "",
        f'@-moz-document domain("{domain}") {{',
        format_gruvbox_css(variant),
        "",
        "    ::selection {",
        "        background-color: color-mix(in srgb, var(--accent) 30%, transparent);",
        "    }",
        "",
        "    input::placeholder,",
        "    textarea::placeholder {",
        "        color: var(--fg-muted) !important;",
        "    }",
    ]

    # If the site defines native CSS variables, add an override block
    if vars_list:
        lines.extend([
            "",
            "    /* --- Native Site CSS Variables Override --- */",
            "    :root {",
        ])
        for v in vars_list[:15]:
            vname = v["name"]
            # Guess Gruvbox mapping
            target_var = "var(--bg0)"
            vname_lower = vname.lower()
            if "text" in vname_lower or "fg" in vname_lower:
                target_var = "var(--fg1)"
            elif "muted" in vname_lower or "secondary" in vname_lower:
                target_var = "var(--fg-muted)"
            elif "border" in vname_lower:
                target_var = "var(--bg1)"
            elif "header" in vname_lower or "nav" in vname_lower:
                target_var = "var(--bg-dark)"
            elif "link" in vname_lower:
                target_var = "var(--blue)"
            lines.append(f"        {vname}: {target_var} !important;")
        lines.append("    }")

    # Surfaces
    lines.extend([
        "",
        "    /* --- Base Surfaces --- */",
        "    body,",
        "    main" + (",\n    " + base_surfaces if base_surfaces else "") + " {",
        "        background-color: var(--bg0) !important;",
        "    }",
    ])

    if elevated_surfaces:
        lines.extend([
            "",
            "    /* --- Elevated Surfaces (Header / Navigation / Sidebar) --- */",
            "    header,",
            "    nav,",
            f"    {elevated_surfaces} {{",
            "        background-color: var(--bg-dark) !important;",
            "    }",
        ])

    if floating_surfaces:
        lines.extend([
            "",
            "    /* --- Floating Surfaces (Cards / Dropdowns / Modals) --- */",
            f"    {floating_surfaces} {{",
            "        background-color: var(--bg1) !important;",
            "    }",
        ])

    # Typography
    headings_sel = ("h1, h2, h3, h4, h5, h6" + (",\n    " + headings if headings else ""))
    lines.extend([
        "",
        "    /* --- Typography & Headings --- */",
        f"    {headings_sel} {{",
        "        color: var(--fg0) !important;",
        "    }",
        "",
        "    /* --- Links --- */",
        "    a {",
        "        color: var(--blue) !important;",
        "    }",
        "",
        "    a:hover {",
        "        color: var(--yellow) !important;",
        "        text-decoration: underline !important;",
        "    }",
    ])

    if meta_text:
        lines.extend([
            "",
            "    /* --- Secondary / Meta Text --- */",
            "    time,",
            f"    {meta_text} {{",
            "        color: var(--fg-muted) !important;",
            "    }",
        ])

    # Form Controls
    controls_sel = ("input, textarea, select, button" + (",\n    " + form_controls if form_controls else ""))
    lines.extend([
        "",
        "    /* --- Form Controls --- */",
        f"    {controls_sel} {{",
        "        background-color: var(--bg1) !important;",
        "        color: var(--fg1) !important;",
        "        border: 1px solid var(--bg3) !important;",
        "    }",
    ])

    # Code Blocks
    if code_blocks:
        lines.extend([
            "",
            "    /* --- Code Blocks --- */",
            "    pre,",
            "    code,",
            f"    {code_blocks} {{",
            "        background-color: var(--bg-dark) !important;",
            "        color: var(--fg1) !important;",
            "    }",
        ])

    # Borders
    if borders:
        lines.extend([
            "",
            "    /* --- Borders & Dividers --- */",
            "    hr,",
            f"    {borders} {{",
            "        border-color: var(--bg1) !important;",
            "    }",
        ])

    # Icons & Filters
    if icons:
        lines.extend([
            "",
            "    /* --- Icons & SVGs --- */",
            f"    {icons} {{",
            "        filter: sepia(1) !important;",
            "    }",
        ])

    if modernize:
        lines.append(MODERN_CSS_ENHANCEMENT)

    lines.extend(["}", ""])
    content = "\n".join(lines)

    if output_path:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    return content
