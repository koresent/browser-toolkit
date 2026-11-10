"""
Gruvbox Color Palette definitions and token formatting.
Focuses strictly on Gruvbox (Medium, Hard, Soft, Light) matching the userstyles repository conventions.
"""

from typing import Dict

GRUVBOX_PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg0": "#282828",
        "bg-dark": "#1d2021",
        "bg1": "#3c3836",
        "bg2": "#504945",
        "bg3": "#665c54",
        "fg0": "#fbf1c7",
        "fg1": "#ebdbb2",
        "fg-muted": "#a89984",
        "accent": "#b8bb26",
        "red": "#fb4934",
        "orange": "#fe8019",
        "yellow": "#fabd2f",
        "green": "#b8bb26",
        "aqua": "#8ec07c",
        "blue": "#83a598",
        "purple": "#d3869b",
    },
    "dark-hard": {
        "bg0": "#1d2021",
        "bg-dark": "#141617",
        "bg1": "#282828",
        "bg2": "#3c3836",
        "bg3": "#504945",
        "fg0": "#fbf1c7",
        "fg1": "#ebdbb2",
        "fg-muted": "#a89984",
        "accent": "#b8bb26",
        "red": "#fb4934",
        "orange": "#fe8019",
        "yellow": "#fabd2f",
        "green": "#b8bb26",
        "aqua": "#8ec07c",
        "blue": "#83a598",
        "purple": "#d3869b",
    },
    "dark-soft": {
        "bg0": "#32302f",
        "bg-dark": "#282828",
        "bg1": "#3c3836",
        "bg2": "#504945",
        "bg3": "#665c54",
        "fg0": "#fbf1c7",
        "fg1": "#ebdbb2",
        "fg-muted": "#a89984",
        "accent": "#b8bb26",
        "red": "#fb4934",
        "orange": "#fe8019",
        "yellow": "#fabd2f",
        "green": "#b8bb26",
        "aqua": "#8ec07c",
        "blue": "#83a598",
        "purple": "#d3869b",
    },
    "light": {
        "bg0": "#fbf1c7",
        "bg-dark": "#f2e5bc",
        "bg1": "#ebdbb2",
        "bg2": "#d5c4a1",
        "bg3": "#bdae93",
        "fg0": "#282828",
        "fg1": "#3c3836",
        "fg-muted": "#7c6f64",
        "accent": "#98971a",
        "red": "#cc241d",
        "orange": "#d65d0e",
        "yellow": "#d79921",
        "green": "#98971a",
        "aqua": "#689d6a",
        "blue": "#458588",
        "purple": "#b16286",
    },
}


def get_gruvbox(variant: str = "dark") -> Dict[str, str]:
    normalized = variant.lower().replace("gruvbox-", "").replace("gruvbox", "").strip("-")
    return GRUVBOX_PALETTES.get(normalized or "dark", GRUVBOX_PALETTES["dark"])


def format_gruvbox_css(variant: str = "dark") -> str:
    palette = get_gruvbox(variant)
    lines = [
        "    :root {",
        "        color-scheme: dark;" if "dark" in variant else "        color-scheme: light;",
        "",
        f"        /* Gruvbox {variant.title()} */",
    ]
    for k, v in palette.items():
        lines.append(f"        --{k}: {v};")
    lines.append("    }")
    return "\n".join(lines)
