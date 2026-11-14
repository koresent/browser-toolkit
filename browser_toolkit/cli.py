import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .formatters import get_default_format, output_result, set_default_format
from .profile import find_zen_profile
from .runner import AuditorRunner
from .scanner import scan_directory
from .session_client import (
    is_session_alive,
    list_active_sessions,
    send_session_command,
    start_session,
    stop_session,
)


def _safe_is_file(path_str: Optional[str]) -> bool:
    if not path_str:
        return False
    try:
        return Path(path_str).is_file()
    except OSError:
        return False


def print_style_summary(report: Dict[str, Any]) -> None:
    audit = report.get("css_audit", {})
    total = audit.get("total_selectors", 0)
    matched = audit.get("cumulative_matched_count", audit.get("matched_count", 0))
    dead = audit.get("dead_count", 0)
    invalid = audit.get("invalid_count", 0)
    pages = report.get("tested_pages", [])

    print(f"UserStyle Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"Base Target:    {report.get('target_url')}")
    print(f"Source file:    {report.get('style_file')}")
    print(f"Screenshots:    {report.get('output_dir')}/")
    if pages:
        print(f"Tested Pages ({len(pages)}):")
        for p in pages:
            print(f"  • {p['url']} ({p.get('matched_count', 0)} selectors matched)")
    print(f"Cumulative Summary: {total} total | {matched} matched | {dead} unconfirmed/dead | {invalid} invalid")

    if dead > 0:
        print("Unmatched / Dead Selectors on Visited Pages:")
        for item in audit.get("dead", [])[:15]:
            sel = item["selector"]
            print(f"  • {sel}")
            suggestions = item.get("suggestions", [])
            if suggestions:
                print("    Potential candidates found in DOM:")
                for s in suggestions[:2]:
                    cls_str = f".{s['className']}" if s.get("className") else ""
                    id_str = f"#{s['id']}" if s.get("id") else ""
                    kw = s.get("matchedKeyword", "")
                    print(f"       - <{s.get('tagName')}{id_str}{cls_str}> (matched '{kw}')")
        if dead > 15:
            print(f"  ... and {dead - 15} more unconfirmed selectors.")

    if matched > 0:
        print("Matched Selectors (Sample):")
        for item in audit.get("matched", [])[:8]:
            pages_found = len(item.get("found_on_pages", []))
            pages_suffix = f" (on {pages_found} page{'s' if pages_found > 1 else ''})" if pages_found else ""
            print(f"  • {item['selector']} -> {item.get('total_count', item.get('count', 0))} elements{pages_suffix}")
        if matched > 8:
            print(f"  ... and {matched - 8} more matched selectors.")


def print_script_summary(report: Dict[str, Any]) -> None:
    audit = report.get("js_audit", {})
    executed = audit.get("executed", False)
    errors = audit.get("errors", [])
    commands = audit.get("registered_commands", [])
    console = audit.get("console_messages", [])
    mutations = audit.get("dom_mutations", {})
    net_reqs = audit.get("network_requests", [])

    print(f"UserScript Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"Target URL:     {report.get('target_url')}")
    print(f"Source file:    {report.get('script_file')}")
    print(f"Screenshot:     {report.get('screenshot')}")
    print(f"Execution: {'Success' if executed and not errors else 'Issues Detected'}")
    if commands:
        print(f"Menu Commands ({len(commands)}): {', '.join(commands)}")

    added_cnt = mutations.get("added_count", 0)
    if added_cnt > 0:
        print(f"DOM Mutations: {added_cnt} elements added")
        for node in mutations.get("added_nodes", [])[:5]:
            snippet = f" (\"{node['text_snippet']}\")" if node.get("text_snippet") else ""
            print(f"  • <{node.get('tag_name')}> {node.get('selector')}{snippet}")
        if added_cnt > 5:
            print(f"    ... and {added_cnt - 5} more added elements.")

    if net_reqs:
        print(f"Network Requests ({len(net_reqs)}):")
        for req in net_reqs[:5]:
            print(f"  • [{req.get('method', 'GET')}] {req.get('url')} (Status: {req.get('status') or req.get('error')})")

    if errors:
        print("Script Errors:")
        for err in errors:
            print(f"  • {err}")

    if console:
        print(f"Recent Console Messages ({len(console)}):")
        for msg in console[-10:]:
            print(f"  [{msg.get('type', 'log')}] {msg.get('text', '')}")


def print_script_test_summary(report: Dict[str, Any]) -> None:
    executed = report.get("executed", False)
    errors = report.get("errors", [])
    commands = report.get("registered_commands", [])
    cmd_res = report.get("command_invocation_result")
    mutations = report.get("dom_mutations", {})
    added_nodes = mutations.get("added_nodes", [])
    net_reqs = report.get("network_requests", [])
    clip = report.get("clipboard_log", [])
    notifs = report.get("notifications_log", [])
    console = report.get("console_messages", [])

    print(f"Interactive UserScript Test: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"Target:         {report.get('target_url')}")
    print(f"Script:         {report.get('script_file')}")
    print(f"Screenshot:     {report.get('screenshot')}")
    print(f"Status: {'OK' if executed and not errors else 'Errors Detected'}")

    if commands:
        print(f"Registered Menu Commands: {', '.join(commands)}")

    if cmd_res:
        succ = cmd_res.get("success")
        print(f"Menu Command Trigger: {'Succeeded' if succ else 'Failed: ' + str(cmd_res.get('error'))}")

    if added_nodes:
        print(f"DOM Elements Inserted by Script ({len(added_nodes)}):")
        for n in added_nodes[:8]:
            snippet = f" (\"{n['text_snippet']}\")" if n.get("text_snippet") else ""
            print(f"  • <{n['tag_name']}> {n['selector']}{snippet}")
        if len(added_nodes) > 8:
            print(f"    ... and {len(added_nodes) - 8} more elements.")

    if net_reqs:
        print(f"Network Requests Sent ({len(net_reqs)}):")
        for req in net_reqs:
            st = req.get("status") if req.get("status") is not None else req.get("error")
            print(f"  • [{req.get('method')}] {req.get('url')} -> {st} ({req.get('durationMs', 0)}ms)")

    if clip:
        print(f"Clipboard Writes ({len(clip)}):")
        for c in clip:
            print(f"  • \"{c.get('text', '')[:60]}\"")

    if notifs:
        print(f"Notifications ({len(notifs)}):")
        for n in notifs:
            print(f"  • [{n.get('title')}] {n.get('text')}")

    if errors:
        print(f"Uncaught Errors ({len(errors)}):")
        for err in errors:
            print(f"  • {err}")

    if console:
        print(f"Console Output ({len(console)}):")
        for msg in console[-10:]:
            print(f"  [{msg.get('type')}] {msg.get('text')}")


def print_spa_summary(report: Dict[str, Any]) -> None:
    survived = report.get("survived", False)
    retained = report.get("retained_selectors", [])
    lost = report.get("lost_selectors", [])
    errors = report.get("errors", [])

    print(f"SPA Route Resilience Audit: {report.get('script')}")
    print(f"Initial: {report.get('initial_url')}")
    print(f"Target:  {report.get('target_url')}")
    status_str = "SURVIVED SPA TRANSITION" if survived else "BROKEN IN SPA ROUTING"
    print(f"Verdict: {status_str}")
    print(f"Inserted Elements: {report.get('initial_added_elements_count', 0)} initial -> {report.get('post_navigation_elements_count', 0)} retained")

    if retained:
        print("Elements Retained After Transition:")
        for sel in retained[:5]:
            print(f"  • {sel}")

    if lost:
        print("Elements Wiped Out During Transition:")
        for sel in lost[:5]:
            print(f"  • {sel}")
        print("  Tip: Listen to 'turbo:load', 'popstate', or 'yt-navigate-finish' to re-mount UI elements.")

    if errors:
        print(f"Errors during transition ({len(errors)}):")
        for err in errors:
            print(f"  • {err}")


def print_search_results(data: Dict[str, Any]) -> None:
    matches = data.get("matches", [])
    print(f"DOM Search on {data.get('url')}")
    print(f"Matched Elements: {len(matches)}")

    for idx, m in enumerate(matches):
        print(f"#{idx + 1} <{m['tagName']}> | Visible: {'yes' if m.get('visible') else 'no'} | Dimensions: {m.get('rect', {}).get('width')}x{m.get('rect', {}).get('height')}px")
        if m.get("textSnippet"):
            print(f"   Text: \"{m['textSnippet']}\"")
        if m.get("className"):
            print(f"   Class: {m['className']}")
        if m.get("ariaLabel"):
            print(f"   aria-label: {m['ariaLabel']}")

        selectors = m.get("selectors", [])
        if selectors:
            print("   Suggested Stable Selectors:")
            for s in selectors[:3]:
                unique_badge = "Unique (1 element)" if s.get("count") == 1 else f"({s.get('count')} elements)"
                print(f"      • {s['selector']}  [{unique_badge}]")


def print_scan_summary(data: Dict[str, Any]) -> None:
    total = data.get("total_scanned", 0)
    broken = data.get("broken_count", 0)
    healthy = total - broken

    print(f"Batch Scan Report: {data.get('root_dir')}")
    print(f"Total Files: {total} | Healthy: {healthy} | Broken / Errors: {broken}")

    for r in data.get("results", []):
        st = r.get("status")
        badge = "OK" if st == "OK" else "BROKEN"
        rel_file = r.get("file")
        if r.get("type") == "userstyle":
            details = f"{r.get('matched', 0)}/{r.get('total_selectors', 0)} matched"
            if st != "OK" and r.get("dead_selectors"):
                details += f" (Dead: {', '.join(r['dead_selectors'][:2])})"
        else:
            errs = r.get("errors", [])
            details = f"{len(errs)} errors" if errs else "Executed cleanly"

        print(f" {badge:<10} | {rel_file:<35} | {details}")


def print_responsive_summary(report: Dict[str, Any]) -> None:
    print(f"Responsive Layout Audit: {report.get('url')}")
    print(f"Status: {'Potential Issues Found' if report.get('has_any_issues') else 'Perfect Responsive Layout'}")

    for vp in report.get("viewports", []):
        w, h = vp.get("viewport", [0, 0])
        label = vp.get("label", f"{w}x{h}")
        has_h_overflow = vp.get("has_horizontal_overflow", False)
        doc_w = vp.get("page_scroll_width", 0)
        win_w = vp.get("viewport_width", w)
        overflow_els = vp.get("overflow_elements", [])
        touch_issues = vp.get("touch_target_issues", [])
        text_issues = vp.get("text_clipping_issues", [])
        sticky_issues = vp.get("sticky_coverage_issues", [])

        status_label = "FAIL" if has_h_overflow or len(touch_issues) > 3 else ("WARN" if (touch_issues or text_issues or sticky_issues) else "OK")
        print(f"[{status_label}] Viewport: {label}")

        if has_h_overflow:
            print(f"  HORIZONTAL OVERFLOW DETECTED: Page width {doc_w}px exceeds viewport {win_w}px (diff: +{doc_w - win_w}px)")
            print("     Elements causing layout blowout:")
            for el in overflow_els[:5]:
                print(f"       • <{el['tag_name']}> {el['selector']} (overflow: +{el['overflow_px']}px)")
                if el.get("text_snippet"):
                    print(f"         Text: \"{el['text_snippet']}\"")
                styles = el.get("computed_styles", {})
                print(f"         CSS: width={styles.get('width')}, max-width={styles.get('maxWidth')}, overflow-x={styles.get('overflowX')}")
        else:
            print(f"  No horizontal scroll (Page width fits within {win_w}px)")

        if touch_issues:
            print(f"  Touch targets < 24x24px ({len(touch_issues)} found):")
            for t in touch_issues[:4]:
                snippet = f" (\"{t['text_snippet']}\")" if t.get("text_snippet") else ""
                print(f"       • {t['selector']} [{t['width']}x{t['height']}px]{snippet}")

        if text_issues:
            print(f"  Text clipping / cut-off ({len(text_issues)} found):")
            for tc in text_issues[:3]:
                print(f"       • {tc['selector']} (scrollWidth: {tc['scroll_width']}px > clientWidth: {tc['client_width']}px) \"{tc['text_snippet']}\"")

        if sticky_issues:
            print(f"  Large Fixed/Sticky screen coverage ({len(sticky_issues)} found):")
            for sc in sticky_issues[:2]:
                print(f"       • {sc['selector']} covers {sc['height_ratio_pct']}% of screen height ({sc['position']})")

        if vp.get("screenshot_path"):
            print(f"  Screenshot: {vp['screenshot_path']}")


def print_theme_flaws_summary(report: Dict[str, Any]) -> None:
    mode = report.get("theme_mode", "dark").upper()
    bleed = report.get("bleedthrough_issues", [])
    invis_text = report.get("invisible_text_issues", [])
    inputs = report.get("unstyled_input_issues", [])
    icons = report.get("invisible_icon_issues", [])
    has_scrollbar = report.get("has_custom_scrollbar", False)
    total_checked = report.get("total_elements_checked", 0)

    print(f"Theme Quality & Visual Flaw Audit: {report.get('url')} (Mode: {mode})")
    print(f"Checked DOM Elements: {total_checked}")

    if bleed:
        print(f"Unstyled Bleedthrough Containers ({len(bleed)} found):")
        for b in bleed[:8]:
            snippet = f" (\"{b['text_snippet']}\")" if b.get("text_snippet") else ""
            print(f"  • {b['selector']} [{b['bounds']['width']}x{b['bounds']['height']}px] -> {b['color']}{snippet}")
        if len(bleed) > 8:
            print(f"    ... and {len(bleed) - 8} more bright containers.")

    if invis_text:
        print(f"Invisible / Blended Text ({len(invis_text)} found):")
        for t in invis_text[:8]:
            print(f"  • {t['selector']}: \"{t['text']}\"")
            print(f"    Ratio: {t['contrast_ratio']}:1 | color: {t['color']} on bg: {t['bg_color']}")
        if len(invis_text) > 8:
            print(f"    ... and {len(invis_text) - 8} more low-contrast text elements.")

    if inputs:
        print(f"Unstyled / Broken Form Inputs ({len(inputs)} found):")
        for inp in inputs[:6]:
            print(f"  • <{inp['tag_name']} type=\"{inp['input_type']}\"> {inp['selector']}")
            print(f"    Issue: {inp['description']} (bg: {inp['bg_color']}, color: {inp['text_color']})")

    if icons:
        print(f"Hidden / Low-Contrast SVG Icons ({len(icons)} found):")
        for ic in icons[:5]:
            print(f"  • {ic['selector']} ({ic['fill_or_stroke']} against {ic['parent_bg']}, ratio: {ic['contrast_ratio']}:1)")

    surfaces = report.get("dominant_surfaces", [])
    if surfaces:
        print(f"Dominant Surface Colors ({len(surfaces)}):")
        for s in surfaces[:8]:
            samples = ", ".join(s.get("samples", []))
            print(f"  • {s['property']}: {s['color']} ({s['count']}x) [{samples}]")

    scrollbar_str = "Custom scrollbar applied" if has_scrollbar else "Native default scrollbars (consider adding scrollbar-color: #504945 #282828)"
    print(f"Scrollbar: {scrollbar_str}")

    if not (bleed or invis_text or inputs or icons):
        if has_scrollbar:
            print("Flawless! No bleedthrough, invisible text, or broken form inputs detected.")
        else:
            print("Colors & contrast are clean! No bleedthrough, invisible text, or broken form inputs detected.")



def print_rule_summary(data: Dict[str, Any]) -> None:
    impact = data.get("impact", {})
    matched = impact.get("matched", [])
    print(f"Rule Impact Test on {data.get('css_rule')}")
    print(f"Matched elements: {len(matched)}")
    print(f"High-impact (>25% viewport) elements: {impact.get('highImpactCount', 0)}")
    print(f"Screenshots: {data.get('screenshot_before')} -> {data.get('screenshot_after')}")
    for m in matched[:5]:
        print(f" • <{m['tagName']}> | {m['dimensions']['width']}x{m['dimensions']['height']}px ({m['viewportRatioPercent']}% viewport) | Text: \"{m['textSnippet']}\"")


def print_map_summary(data: Dict[str, Any]) -> None:
    archs = data.get("archetypes", [])
    print(f"Site Template Archetypes: {data.get('base_url')}")
    print(f"Scanned {data.get('pages_visited')} pages | Discovered {len(archs)} unique structural layouts")
    print(f"Termination: {data.get('stopped_reason')}")
    for a in archs:
        matched_str = f" | {a['matched_selectors_count']} selectors" if a.get("matched_selectors_count") else ""
        sim_str = f" (similarity: {a['similarity_to_previous']})" if a["similarity_to_previous"] > 0 else " (root)"
        print(f" #{a['index']} [{a.get('title', 'No title')[:40]}]{sim_str}{matched_str}")
        print(f"    URL: {a['url']}")
        if a.get("screenshot"):
            print(f"    {a['screenshot']}")
    if data.get("cumulative_matched_count"):
        print(f"Total Selectors Matched: {data['cumulative_matched_count']} | Remaining dead: {data.get('remaining_dead_count', 0)}")


def print_palette_summary(data: Dict[str, Any]) -> None:
    print(f"Palette Reverse Engineering: {data.get('url', '')}")
    vars_list = data.get("site_color_variables", [])
    print(f"Native Site Color Variables Found ({len(vars_list)}):")
    for v in vars_list[:10]:
        print(f"  • {v['name']}: {v['value']}")
    if len(vars_list) > 10:
        print(f"  ... and {len(vars_list) - 10} more.")
    print("Top Computed Background Colors:")
    for bg in data.get("background_colors", [])[:5]:
        print(f"  • {bg['color']} ({bg['count']} elements, e.g. {', '.join(bg['samples'])})")
    print("Top Computed Text Colors:")
    for fg in data.get("text_colors", [])[:5]:
        print(f"  • {fg['color']} ({fg['count']} elements, e.g. {', '.join(fg['samples'])})")
    print(f"SVGs & Icons: {data.get('svg_count', 0)} SVG icons found on page.")


def print_contrast_summary(data: Dict[str, Any]) -> None:
    audit = data.get("contrast_audit", {})
    issues = audit.get("issues", [])
    total = audit.get("totalChecked", 0)
    failed = audit.get("failedCount", 0)
    print(f"WCAG Contrast Audit on {data.get('url', '')}")
    print(f"Checked Text Nodes: {total} | Issues: {failed} | Passing: {total - failed}")
    if issues:
        print("Low Contrast Elements (Needs adjustment):")
        for iss in issues[:10]:
            print(f"  • <{iss['tagName']}> \"{iss['textSnippet']}\"")
            print(f"    Ratio: {iss['contrastRatio']}:1 (Required: {iss['requiredRatio']}:1) | fg: {iss['fg']}, bg: {iss['bg']}")
        if len(issues) > 10:
            print(f"    ... and {len(issues) - 10} more low-contrast elements.")
    else:
        print("Excellent! All visible text elements meet WCAG contrast thresholds!")


def print_interact_summary(data: Dict[str, Any]) -> None:
    print(f"Action Sequence executed on {data.get('url', '')}:")
    for res in data.get("action_results", []):
        print(f" Step #{res['step']}: {res['action']} -> {res['status']} {res.get('saved_to', '')}")


def parse_actions_arg(raw: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    try:
        p = Path(raw)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(raw)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to parse actions JSON: {e}\n")
        return None


def print_inspect_summary(data: Dict[str, Any]) -> None:
    res = data.get("result", {})
    count = res.get("count", 0)
    print(f"Inspecting selector '{data.get('selector', '')}' on {data.get('url', '')}")
    print(f"Found elements: {count}")
    for idx, item in enumerate(res.get("items", [])):
        print(f"\nElement #{idx + 1} <{item['tagName']}>:")
        comp = item.get("computed", {})
        if comp:
            print("  Computed styles:")
            for k, v in comp.items():
                if v:
                    print(f"    {k}: {v}")
        cv = item.get("customProperties", {})
        if cv:
            print(f"  Custom CSS variables ({len(cv)}):")
            for k, v in list(cv.items())[:15]:
                print(f"    {k}: {v}")
        rules = item.get("matchedRules", [])
        if rules:
            print(f"  Matched CSS rules ({len(rules)}):")
            for r in rules[:10]:
                props_str = "; ".join(f"{k}: {v}" for k, v in list(r.get("properties", {}).items())[:4])
                print(f"    {r.get('selector')} [{r.get('source')}] -> {props_str}")
        print(f"  HTML snippet: {item.get('outerHTML', '')[:160]}...")


def print_ext_status(st: Dict[str, Any]) -> None:
    print("Zen Browser Extension Status")
    print(f"Profile directory:  {st['profile_dir']}")
    print(f"Stylus DB:          {st['stylus_db']}")
    print(f"Violentmonkey DB:   {st['violentmonkey_db']}")
    print(f"Stylus Styles:        {st['stylus_installed_count']} installed ({st['active_styles_count']} active)")
    print(f"Violentmonkey Scripts: {st['violentmonkey_installed_count']} installed ({st['active_scripts_count']} active)")


def print_ext_styles(styles: list) -> None:
    print(f"Stylus Installed Styles ({len(styles)}):")
    for s in styles:
        status_badge = "[ON]" if s["enabled"] else "[OFF]"
        doms = ", ".join(s["domains"][:2]) if s["domains"] else "all sites"
        print(f"  {status_badge} [{s['id']:<3}] {s['name']:<42} -> {doms}")


def print_ext_scripts(scripts: list) -> None:
    print(f"Violentmonkey Installed Scripts ({len(scripts)}):")
    for sc in scripts:
        status_badge = "[ON]" if sc["enabled"] else "[OFF]"
        matches = ", ".join(sc["matches"][:2]) if sc["matches"] else "*://*/*"
        print(f"  {status_badge} [{sc['id']:<3}] {sc['name']:<40} (v{sc['version']}) -> {matches}")


def print_diff_styles(diff: Dict[str, Any]) -> None:
    print("UserStyles Sync Diff: Local vs Stylus DB")
    print(f"Local files: {diff['total_local']} | Installed in Stylus: {diff['total_installed']} | In Sync: {diff['in_sync']}")
    if diff.get("modified"):
        print(f"Modified / Out of Sync ({len(diff['modified'])}):")
        for m in diff["modified"]:
            print(f"  • {m['name']} ({m['file']}) [Local: {m['local_size']}B, Stylus: {m['installed_size']}B]")
    if diff.get("only_local"):
        print(f"Only Local (Not in Stylus) ({len(diff['only_local'])}):")
        for ol in diff["only_local"][:10]:
            print(f"  • {ol['name']} ({ol['file']})")
    if diff.get("only_installed"):
        print(f"Only in Stylus (Missing in git repo) ({len(diff['only_installed'])}):")
        for oi in diff["only_installed"][:10]:
            print(f"  • [{oi['id']}] {oi['name']}")


def print_diff_scripts(diff: Dict[str, Any]) -> None:
    print("UserScripts Sync Diff: Local vs Violentmonkey DB")
    print(f"Local files: {diff['total_local']} | Installed in VM: {diff['total_installed']} | In Sync: {diff['in_sync']}")
    if diff.get("modified"):
        print(f"Modified / Out of Sync ({len(diff['modified'])}):")
        for m in diff["modified"]:
            print(f"  • {m['name']} ({m['file']}) [Local: {m['local_size']}B, VM: {m['installed_size']}B]")
    if diff.get("only_local"):
        print(f"Only Local (Not in VM) ({len(diff['only_local'])}):")
        for ol in diff["only_local"][:10]:
            print(f"  • {ol['name']} ({ol['file']})")
    if diff.get("only_installed"):
        print(f"Only in Violentmonkey (Missing in git repo) ({len(diff['only_installed'])}):")
        for oi in diff["only_installed"][:10]:
            print(f"  • [{oi['id']}] {oi['name']} (v{oi['version']})")


TEMP_TOOLKIT_DIR = Path(tempfile.gettempdir()) / "browser-toolkit"


def add_output_args(p: argparse.ArgumentParser, is_root: bool = False) -> None:
    default_flag = False if is_root else argparse.SUPPRESS
    default_format = None if is_root else argparse.SUPPRESS
    p.add_argument("--toon", action="store_true", default=default_flag, help="Output result as TOON (Token-Oriented Object Notation)")
    p.add_argument("--json", action="store_true", default=default_flag, help="Output result as compact JSON")
    p.add_argument("--format", choices=["text", "json", "json-pretty", "toon"], default=default_format, help="Explicit output format")

def add_profile_args(p: argparse.ArgumentParser, with_clean_styles: bool = True) -> None:
    p.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    p.add_argument("--profile", help="Path to custom profile directory")
    p.add_argument("--headful", action="store_true", help="Run with visible window")
    if with_clean_styles:
        p.add_argument("--clean-styles", action="store_true", help="Strip Stylus storage in temporary profile clone while keeping cookies")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-toolkit",
        description="Audit, inspect, and test UserStyles and UserScripts using Zen Browser profile and Playwright Gecko.",
    )
    add_output_args(parser, is_root=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: audit
    audit_parser = subparsers.add_parser("audit", help="Audit a .user.css or .user.js file")
    audit_parser.add_argument("file", help="Path to .user.css or .user.js file")
    audit_parser.add_argument("--url", help="Override target base URL")
    audit_parser.add_argument("--urls", help="Comma-separated list of multiple URLs to audit across")
    audit_parser.add_argument("--sample-pages", type=int, default=2, help="Number of representative subpages to auto-discover and test (default: 2)")
    audit_parser.add_argument("--deep-hunt", action="store_true", help="Crawl site for unique DOM archetypes until 100% selectors are satisfied or limit reached")
    add_profile_args(audit_parser)
    audit_parser.add_argument("--output", help="Directory to save screenshots and report")
    add_output_args(audit_parser)

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Batch scan directory of styles/scripts")
    scan_parser.add_argument("dir", help="Directory path to scan")
    scan_parser.add_argument("--only-broken", action="store_true", help="Only report broken files")
    scan_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    scan_parser.add_argument("--profile", help="Path to custom profile")
    scan_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(scan_parser)

    def add_search_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--text", help="Search by visible text")
        p.add_argument("--keyword", help="Search keyword in class, id, aria attributes")
        p.add_argument("--role", help="Search by ARIA role")
        p.add_argument("--tag", help="Filter by HTML tag")
        p.add_argument("--wait", help="Wait for selector or ms before searching")
        p.add_argument("--actions", help="JSON string or file path containing user actions before searching")

    def add_inspect_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--selector", required=True, help="CSS selector to inspect")
        p.add_argument("--actions", help="JSON string or file path containing user actions before inspecting")
        p.add_argument("--properties", help="Comma-separated CSS properties to inspect (e.g. 'color,border-radius')")
        p.add_argument("--rules", action="store_true", help="Inspect all matching CSS rules from stylesheets")
        p.add_argument("--css", help="Optional CSS rule string or .user.css path to inject before inspecting")
        p.add_argument("--pseudo", help="Pseudo-element to inspect (e.g. '::before', '::after')")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Search DOM by text/keyword and synthesize selectors")
    search_parser.add_argument("url", help="Target URL")
    add_search_args(search_parser)
    search_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    search_parser.add_argument("--profile", help="Path to custom profile")
    search_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(search_parser)

    # Command: test-rule
    rule_parser = subparsers.add_parser("test-rule", help="Test candidate CSS rule on live page with impact analysis")
    rule_parser.add_argument("url", help="Target URL")
    rule_parser.add_argument("--css", required=True, help="CSS rule to test, e.g. '.foo { display: none; }'")
    rule_parser.add_argument("--output", help="Output directory for before/after screenshots")
    add_profile_args(rule_parser)
    add_output_args(rule_parser)

    # Command: screenshot
    shot_parser = subparsers.add_parser("screenshot", help="Capture page or element screenshot with hover/wait")
    shot_parser.add_argument("url", help="Target URL")
    shot_parser.add_argument("--output", help="Output image file path (default: unique timestamped PNG in /tmp/browser-toolkit/screenshots/)")
    shot_parser.add_argument("--selector", help="Capture only this element")
    shot_parser.add_argument("--hover", help="Hover over selector before screenshot")
    shot_parser.add_argument("--wait", help="Wait for selector or millisecond timeout before screenshot")
    shot_parser.add_argument("--full-page", action="store_true", help="Capture full page height")
    add_profile_args(shot_parser)
    add_output_args(shot_parser)

    # Command: interact
    interact_parser = subparsers.add_parser("interact", help="Perform sequence of user actions (click, hover, fill)")
    interact_parser.add_argument("url", help="Target URL")
    interact_parser.add_argument("--actions", required=True, help="JSON string or file path containing list of actions")
    add_profile_args(interact_parser)
    add_output_args(interact_parser)

    # Command: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect element computed styles, custom properties, and CSS rules on a live URL")
    inspect_parser.add_argument("url", help="Target URL to open")
    add_inspect_args(inspect_parser)
    add_profile_args(inspect_parser)
    add_output_args(inspect_parser)

    # Command: map-site
    map_parser = subparsers.add_parser("map-site", help="Crawl site for structurally unique page templates (archetypes)")
    map_parser.add_argument("url", help="Starting base URL")
    map_parser.add_argument("--css", help="Optional UserStyle file to guide selector hunting")
    map_parser.add_argument("--max-archetypes", type=int, default=8, help="Maximum unique archetypes to discover (default: 8)")
    map_parser.add_argument("--max-pages", type=int, default=25, help="Maximum total pages to visit (default: 25)")
    map_parser.add_argument("--output", help="Directory to save archetype screenshots")
    map_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    map_parser.add_argument("--profile", help="Path to custom profile")
    map_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(map_parser)

    # Command: extract-palette
    pal_parser = subparsers.add_parser("extract-palette", help="Reverse engineer colors and CSS variables of target site")
    pal_parser.add_argument("url", help="Target URL")
    pal_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    pal_parser.add_argument("--profile", help="Path to custom profile")
    pal_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(pal_parser)

    # Command: check-contrast
    contrast_parser = subparsers.add_parser("check-contrast", help="Audit WCAG text contrast across styled page")
    contrast_parser.add_argument("url", help="Target URL")
    contrast_parser.add_argument("--css", help="Path to .user.css file to test")
    contrast_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    contrast_parser.add_argument("--profile", help="Path to custom profile")
    contrast_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(contrast_parser)

    # Command: preview
    preview_parser = subparsers.add_parser("preview", help="Live hot-reload preview server watching .user.css")
    preview_parser.add_argument("url", help="Target URL")
    preview_parser.add_argument("css", help="Path to .user.css file to watch")
    preview_parser.add_argument("--headful", action="store_true", default=True, help="Run with visible Zen window (default)")
    preview_parser.add_argument("--headless", action="store_true", help="Run headless taking screenshots on change")
    preview_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    preview_parser.add_argument("--profile", help="Path to custom profile")
    preview_parser.add_argument("--output", default=str(TEMP_TOOLKIT_DIR / "preview.png"), help="Path to save preview screenshot (default: in /tmp/browser-toolkit)")

    # Command: extract-colors
    extract_colors_parser = subparsers.add_parser("extract-colors", help="Extract pure color skeleton from CSS file, URL, or stdin")
    extract_colors_parser.add_argument("target", nargs="?", default="-", help="Local .css file path, website URL, or '-' for stdin (default: '-')")
    extract_colors_parser.add_argument("--output", "-o", help="Path to write output CSS skeleton")
    extract_colors_parser.add_argument("-c", "--clipboard", action="store_true", help="Copy extracted CSS colors to system clipboard")
    extract_colors_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    extract_colors_parser.add_argument("--profile", help="Path to custom profile")
    add_output_args(extract_colors_parser)

    # Command: check-responsive
    resp_parser = subparsers.add_parser("check-responsive", help="Audit responsive layout (horizontal overflow, touch targets, text clipping)")
    resp_parser.add_argument("url", help="Target URL")
    resp_parser.add_argument("--css", help="Optional path to .user.css to apply before testing")
    resp_parser.add_argument("--viewports", help="Comma-separated viewports, e.g. '390x844,768x1024,1440x900'")
    resp_parser.add_argument("--screenshots-dir", help="Directory to save viewport screenshots")
    resp_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    resp_parser.add_argument("--profile", help="Path to custom profile")
    resp_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(resp_parser)

    def add_theme_check_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--css", help="Optional path to .user.css or CSS string to apply before testing")
        p.add_argument("--theme", choices=["dark", "light"], default="dark", help="Expected theme palette mode (default: dark)")
        p.add_argument("--exclude-colors", help="Comma-separated palette colors (e.g. '#282828,#3c3836') to exclude from dominant surface report")

    # Command: check-theme
    theme_parser = subparsers.add_parser("check-theme", help="Audit theme flaws (bright bleedthrough, invisible text, unstyled inputs, hidden SVGs)")
    theme_parser.add_argument("url", help="Target URL")
    add_theme_check_args(theme_parser)
    add_profile_args(theme_parser)
    add_output_args(theme_parser)

    # Command: test-script
    test_script_parser = subparsers.add_parser("test-script", help="Interactive UserScript testing with DOM mutations, network log, and menu command triggers")
    test_script_parser.add_argument("file", help="Path to .user.js file")
    test_script_parser.add_argument("--url", help="Override target URL")
    test_script_parser.add_argument("--command", dest="menu_command", help="Invoke a registered GM_registerMenuCommand by name")
    test_script_parser.add_argument("--actions", help="JSON string or file path containing user actions (click, hover, fill)")
    test_script_parser.add_argument("--output", help="Output directory for screenshots and reports")
    test_script_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    test_script_parser.add_argument("--profile", help="Path to custom profile")
    test_script_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(test_script_parser)

    # Command: check-spa
    check_spa_parser = subparsers.add_parser("check-spa", help="Verify UserScript resilience across client-side SPA route transitions (Turbo, YouTube, etc.)")
    check_spa_parser.add_argument("file", help="Path to .user.js file")
    check_spa_parser.add_argument("target_url", help="Target SPA URL to navigate to (e.g. /watch?v=... or /tree/...)")
    check_spa_parser.add_argument("--initial-url", help="Initial starting URL (defaults to script's first @match)")
    check_spa_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    check_spa_parser.add_argument("--profile", help="Path to custom profile")
    check_spa_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    add_output_args(check_spa_parser)

    # Command: preview-js
    preview_js_parser = subparsers.add_parser("preview-js", help="Live hot-reload preview server watching .user.js")
    preview_js_parser.add_argument("file", help="Path to .user.js file to watch")
    preview_js_parser.add_argument("--url", help="Target URL (defaults to script @match)")
    preview_js_parser.add_argument("--headful", action="store_true", default=True, help="Run with visible Zen window (default)")
    preview_js_parser.add_argument("--headless", action="store_true", help="Run headless taking screenshots on change")
    preview_js_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    preview_js_parser.add_argument("--profile", help="Path to custom profile")
    preview_js_parser.add_argument("--output", default=str(TEMP_TOOLKIT_DIR / "preview_js.png"), help="Path to save preview screenshot (default: in /tmp/browser-toolkit)")

    # Command: ext (Extension management)
    ext_parser = subparsers.add_parser("ext", help="Manage Stylus and Violentmonkey extensions, styles, scripts, and sync")
    ext_subparsers = ext_parser.add_subparsers(dest="ext_action", required=True)

    # ext status
    status_p = ext_subparsers.add_parser("status", help="Show installed extensions, active profiles, and database stats")
    status_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(status_p)

    # ext list-styles
    ls_styles_p = ext_subparsers.add_parser("list-styles", help="List all styles installed in Stylus")
    ls_styles_p.add_argument("--search", help="Filter styles by name or domain keyword")
    ls_styles_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(ls_styles_p)

    # ext list-scripts
    ls_scripts_p = ext_subparsers.add_parser("list-scripts", help="List all scripts installed in Violentmonkey")
    ls_scripts_p.add_argument("--search", help="Filter scripts by name or match keyword")
    ls_scripts_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(ls_scripts_p)

    # ext export-styles
    exp_styles_p = ext_subparsers.add_parser("export-styles", help="Export all styles from Stylus DB as clean .user.css files")
    exp_styles_p.add_argument("out_dir", help="Directory to save .user.css files")
    exp_styles_p.add_argument("--profile", help="Path to custom profile")

    # ext export-scripts
    exp_scripts_p = ext_subparsers.add_parser("export-scripts", help="Export all scripts from Violentmonkey DB as .user.js files")
    exp_scripts_p.add_argument("out_dir", help="Directory to save .user.js files")
    exp_scripts_p.add_argument("--profile", help="Path to custom profile")

    # ext diff-styles
    diff_styles_p = ext_subparsers.add_parser("diff-styles", help="Compare local .user.css files with active Stylus database")
    diff_styles_p.add_argument("local_dir", help="Path to local folder with userstyles")
    diff_styles_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(diff_styles_p)

    # ext diff-scripts
    diff_scripts_p = ext_subparsers.add_parser("diff-scripts", help="Compare local .user.js files with active Violentmonkey database")
    diff_scripts_p.add_argument("local_dir", help="Path to local folder with userscripts")
    diff_scripts_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(diff_scripts_p)

    # ext backup
    backup_p = ext_subparsers.add_parser("backup", help="Build ready-to-import backup bundles for Stylus and Violentmonkey")
    backup_p.add_argument(
        "--styles-dir",
        default=str(Path.home() / "Projects" / "personal" / "userstyles"),
        help="Local userstyles directory",
    )
    backup_p.add_argument(
        "--scripts-dir",
        default=str(Path.home() / "Projects" / "personal" / "userscripts"),
        help="Local userscripts directory",
    )
    backup_p.add_argument("--out-stylus", default=str(TEMP_TOOLKIT_DIR / "stylus-backup.json"), help="Path for Stylus backup JSON (default: in /tmp/browser-toolkit)")
    add_output_args(backup_p)
    backup_p.add_argument("--out-vm", default=str(TEMP_TOOLKIT_DIR / "vm-backup.zip"), help="Path for Violentmonkey backup ZIP (default: in /tmp/browser-toolkit)")

    # ext serve
    serve_p = ext_subparsers.add_parser("serve", help="Launch interactive 1-click install & sync server hub")
    serve_p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    serve_p.add_argument("--styles-dir", help="Custom userstyles directory")
    serve_p.add_argument("--scripts-dir", help="Custom userscripts directory")
    serve_p.add_argument("--profile", help="Path to custom profile")

    # ext enable-style
    en_style_p = ext_subparsers.add_parser("enable-style", help="Enable an installed Stylus style by ID or name")
    en_style_p.add_argument("target", help="Numeric ID or style name")
    add_output_args(en_style_p)
    en_style_p.add_argument("--profile", help="Path to custom profile")

    # ext disable-style
    dis_style_p = ext_subparsers.add_parser("disable-style", help="Disable an installed Stylus style by ID or name")
    dis_style_p.add_argument("target", help="Numeric ID or style name")
    add_output_args(dis_style_p)
    dis_style_p.add_argument("--profile", help="Path to custom profile")

    # ext toggle-style
    tog_style_p = ext_subparsers.add_parser("toggle-style", help="Toggle an installed Stylus style on/off")
    tog_style_p.add_argument("target", help="Numeric ID or style name")
    add_output_args(tog_style_p)
    tog_style_p.add_argument("--profile", help="Path to custom profile")

    # ext delete-style
    del_style_p = ext_subparsers.add_parser("delete-style", help="Delete an installed style from Stylus DB")
    del_style_p.add_argument("target", help="Numeric ID or style name")
    add_output_args(del_style_p)
    del_style_p.add_argument("--profile", help="Path to custom profile")

    # ext install-style
    inst_style_p = ext_subparsers.add_parser("install-style", help="Install or update a .user.css file in Stylus DB")
    inst_style_p.add_argument("file", help="Path to .user.css file")
    add_output_args(inst_style_p)
    inst_style_p.add_argument("--disabled", action="store_true", help="Install as disabled")
    inst_style_p.add_argument("--profile", help="Path to custom profile")

    # ext enable-script
    en_script_p = ext_subparsers.add_parser("enable-script", help="Enable an installed Violentmonkey script by ID or name")
    en_script_p.add_argument("target", help="Numeric ID or script name")
    add_output_args(en_script_p)
    en_script_p.add_argument("--profile", help="Path to custom profile")

    # ext disable-script
    dis_script_p = ext_subparsers.add_parser("disable-script", help="Disable an installed Violentmonkey script by ID or name")
    dis_script_p.add_argument("target", help="Numeric ID or script name")
    add_output_args(dis_script_p)
    dis_script_p.add_argument("--profile", help="Path to custom profile")

    # ext toggle-script
    tog_script_p = ext_subparsers.add_parser("toggle-script", help="Toggle an installed Violentmonkey script on/off")
    tog_script_p.add_argument("target", help="Numeric ID or script name")
    add_output_args(tog_script_p)
    tog_script_p.add_argument("--profile", help="Path to custom profile")

    # ext delete-script
    del_script_p = ext_subparsers.add_parser("delete-script", help="Delete an installed script from Violentmonkey DB")
    del_script_p.add_argument("target", help="Numeric ID or script name")
    add_output_args(del_script_p)
    del_script_p.add_argument("--profile", help="Path to custom profile")

    # ext install-script
    inst_script_p = ext_subparsers.add_parser("install-script", help="Install or update a .user.js file in Violentmonkey DB")
    inst_script_p.add_argument("file", help="Path to .user.js file")
    add_output_args(inst_script_p)
    inst_script_p.add_argument("--disabled", action="store_true", help="Install as disabled")
    inst_script_p.add_argument("--profile", help="Path to custom profile")

    # ext sync
    sync_p = ext_subparsers.add_parser("sync", help="Synchronize all local styles and scripts into Stylus and Violentmonkey databases")
    sync_p.add_argument("--styles-dir", help="Path to userstyles directory (default: ~/Projects/personal/userstyles)")
    sync_p.add_argument("--scripts-dir", help="Path to userscripts directory (default: ~/Projects/personal/userscripts)")
    sync_p.add_argument("--profile", help="Path to custom profile")
    add_output_args(sync_p)

    # Command: profile-info
    prof_p = subparsers.add_parser("profile-info", help="Show detected Zen profile location")
    add_output_args(prof_p)

    # Command: config
    cfg_parser = subparsers.add_parser("config", help="Manage persistent browser-toolkit settings (e.g. default format)")
    cfg_parser.add_argument("--set-format", choices=["toon", "json", "json-pretty", "text"], help="Set persistent default output format")
    cfg_parser.add_argument("key", nargs="?", choices=["format"], help="Setting key (e.g. 'format')")
    cfg_parser.add_argument("value", nargs="?", help="Value to set for key")
    add_output_args(cfg_parser)

    # Command: session
    session_parser = subparsers.add_parser("session", help="Manage persistent Playwright browser session")
    session_parser.add_argument("--name", "--session", dest="session_parent_name", help="Session identifier (default: 'default' or BROWSER_TOOLKIT_SESSION env var)")
    session_sub = session_parser.add_subparsers(dest="session_command", required=True)

    def add_session_name_arg(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument("--name", "--session", help="Session identifier (default: 'default' or BROWSER_TOOLKIT_SESSION env var)")

    def add_frame_arg(sub_p: argparse.ArgumentParser) -> None:
        sub_p.add_argument("--frame", help="Target child iframe by name or URL substring (e.g. 'account' or 'ogs.google.com')")

    # session list
    s_list = session_sub.add_parser("list", help="List all running browser sessions")
    add_output_args(s_list)

    # session start [url] [--name NAME] [--no-profile] [--profile PATH] [--headful] [--clean-styles] [--force] [--random]
    s_start = session_sub.add_parser("start", help="Start background session daemon or navigate to URL")
    s_start.add_argument("url", nargs="?", help="Initial URL to navigate")
    add_profile_args(s_start)
    add_session_name_arg(s_start)
    s_start.add_argument("--force", action="store_true", help="Force reuse or navigation of active session even if open on a different URL")
    s_start.add_argument("--random", "--auto", dest="random_name", action="store_true", help="Generate an isolated unique session name (e.g. sess-a1b2c3d4)")
    add_output_args(s_start)

    # session status [--name NAME]
    s_status = session_sub.add_parser("status", help="Get status of active session daemon")
    add_session_name_arg(s_status)
    add_output_args(s_status)

    # session frames [--name NAME]
    s_frames = session_sub.add_parser("frames", help="List all page and iframe targets in active session")
    add_session_name_arg(s_frames)
    add_output_args(s_frames)

    # session goto <url> [--name NAME]
    s_goto = session_sub.add_parser("goto", help="Navigate active session to a URL")
    s_goto.add_argument("url", help="Target URL")
    add_session_name_arg(s_goto)
    add_output_args(s_goto)

    # session eval [script] [--file PATH] [--frame FRAME] [--name NAME]
    s_eval = session_sub.add_parser("eval", help="Evaluate JavaScript expression in active session")
    s_eval.add_argument("script", nargs="?", help="JavaScript code to evaluate (or '-' to read from stdin)")
    s_eval.add_argument("--file", "-f", help="Path to JavaScript file to evaluate")
    add_frame_arg(s_eval)
    add_session_name_arg(s_eval)
    add_output_args(s_eval)

    # session eval-many <scripts> [--frame FRAME] [--name NAME]
    s_eval_many = session_sub.add_parser("eval-many", help="Evaluate batch of JavaScript expressions")
    s_eval_many.add_argument("scripts", help="JSON dictionary of scripts or path to JSON file")
    add_frame_arg(s_eval_many)
    add_session_name_arg(s_eval_many)
    add_output_args(s_eval_many)

    # session inspect --selector SEL [...] [--frame FRAME] [--name NAME]
    s_inspect = session_sub.add_parser("inspect", help="Inspect elements, computed styles, and CSS rules in active session")
    add_inspect_args(s_inspect)
    add_frame_arg(s_inspect)
    add_session_name_arg(s_inspect)
    add_output_args(s_inspect)

    # session search [...] [--frame FRAME] [--name NAME]
    s_search = session_sub.add_parser("search", help="Search DOM and synthesize selectors in active session")
    add_search_args(s_search)
    add_frame_arg(s_search)
    add_session_name_arg(s_search)
    add_output_args(s_search)

    # session inject-css <css_or_file> [--frame FRAME] [--name NAME]
    s_inj_css = session_sub.add_parser("inject-css", help="Inject CSS string or .user.css file into active session")
    s_inj_css.add_argument("css", help="CSS code or path to .css/.user.css file")
    add_frame_arg(s_inj_css)
    add_session_name_arg(s_inj_css)
    add_output_args(s_inj_css)

    # session check-theme [...] [--frame FRAME] [--name NAME]
    s_check_theme = session_sub.add_parser("check-theme", help="Audit theme flaws and dominant surface colors inside active session")
    add_theme_check_args(s_check_theme)
    add_frame_arg(s_check_theme)
    add_session_name_arg(s_check_theme)
    add_output_args(s_check_theme)

    # session inject-script <file_or_js> [--settle-ms MS] [--name NAME]
    s_inj_js = session_sub.add_parser("inject-script", help="Inject .user.js or JavaScript file into active session with GM polyfills")
    s_inj_js.add_argument("file", help="Path to .user.js or .js file (or inline JS string)")
    s_inj_js.add_argument("--settle-ms", type=int, default=500, help="Wait time in ms after injection (default: 500)")
    add_session_name_arg(s_inj_js)
    add_output_args(s_inj_js)

    # session interact --actions <json_or_file> [--frame FRAME] [--name NAME]
    s_interact = session_sub.add_parser("interact", help="Perform sequence of user actions in active session")
    s_interact.add_argument("--actions", required=True, help="JSON list of actions or path to JSON file")
    add_frame_arg(s_interact)
    add_session_name_arg(s_interact)
    add_output_args(s_interact)

    # session screenshot [--output PATH] [--selector SEL] [--full-page] [--name NAME]
    s_shot = session_sub.add_parser("screenshot", help="Capture screenshot in active session")
    s_shot.add_argument("--output", help="Output image file path (default: unique timestamped PNG in /tmp/browser-toolkit/screenshots/)")
    s_shot.add_argument("--selector", help="Capture only this element")
    s_shot.add_argument("--full-page", action="store_true", help="Capture full page height")
    add_session_name_arg(s_shot)
    add_output_args(s_shot)

    # session stop [--name NAME]
    s_stop = session_sub.add_parser("stop", help="Stop background session daemon and close browser")
    add_session_name_arg(s_stop)
    add_output_args(s_stop)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "profile-info":
        prof = find_zen_profile()
        data = {
            "profile_found": bool(prof),
            "profile_dir": str(prof) if prof else None,
        }
        output_result(
            data,
            args,
            lambda d: print(f"Zen profile found: {d['profile_dir']}" if d["profile_found"] else "Zen profile not found."),
        )
        sys.exit(0 if prof else 1)

    if args.command == "config":
        new_fmt = getattr(args, "set_format", None)
        if not new_fmt and getattr(args, "key", None) == "format" and getattr(args, "value", None):
            new_fmt = args.value

        if new_fmt:
            set_default_format(new_fmt)
            current_fmt = new_fmt
            action = "set"
        else:
            current_fmt = get_default_format() or "not set (default: text)"
            action = "get"
        data = {"status": "ok", "action": action, "default_format": current_fmt}
        output_result(
            data,
            args,
            lambda d: print(f"Persistent default format: {d['default_format']}"),
        )
        sys.exit(0)

    if args.command == "session":
        session_cmd = getattr(args, "session_command", None)
        session_name = (
            getattr(args, "name", None)
            or getattr(args, "session", None)
            or getattr(args, "session_parent_name", None)
        )

        if session_cmd == "list":
            sessions = list_active_sessions()
            data = {"total_sessions": len(sessions), "sessions": sessions}
            output_result(
                data,
                args,
                lambda d: print(
                    f"Active sessions ({d['total_sessions']}):\n"
                    + "\n".join(
                        f"  • [{s.get('session_name', 'default')}] {s.get('url', 'none')} ('{s.get('title', '')}') - uptime: {s.get('uptime_seconds', 0)}s"
                        for s in d.get("sessions", [])
                    )
                    if d["total_sessions"]
                    else "No active sessions found."
                ),
            )
            sys.exit(0)

        elif session_cmd == "start":
            is_random = getattr(args, "random_name", False) or (session_name and session_name.strip().lower() in ("auto", "random"))
            res = start_session(
                url=getattr(args, "url", None),
                session_name=None if is_random else session_name,
                random_name=is_random,
                profile_path=getattr(args, "profile", None),
                no_profile=getattr(args, "no_profile", False),
                headful=getattr(args, "headful", False),
                clean_styles=getattr(args, "clean_styles", False),
                force=getattr(args, "force", False),
            )
            output_result(
                res,
                args,
                lambda d: print(f"Session '{d.get('session_name', 'default')}' active: URL={d.get('url')} Title='{d.get('title')}'"),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "frames":
            res = send_session_command({"action": "frames"}, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(
                    f"Frames ({d.get('frames_count', 0)}):\n"
                    + "\n".join(
                        f"  [{f['index']}] name='{f['name']}' url={f['url']}" + (" (main)" if f.get("is_main") else "")
                        for f in d.get("frames", [])
                    )
                ),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "status":
            alive = is_session_alive(session_name)
            if not alive:
                res = {"status": "inactive", "session_name": session_name or "default", "message": "No active session"}
            else:
                res = send_session_command({"action": "status"}, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Session status: {d.get('status')} [{d.get('session_name', 'default')}] | URL: {d.get('url', 'none')} | Uptime: {d.get('uptime_seconds', 0)}s"),
            )
            sys.exit(0 if alive else 1)

        elif session_cmd == "goto":
            res = send_session_command({"action": "goto", "url": args.url}, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Navigated to: {d.get('url')} ('{d.get('title')}')"),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "eval":
            script_code = args.script
            if getattr(args, "file", None):
                script_code = Path(args.file).read_text(encoding="utf-8")
            elif script_code == "-":
                script_code = sys.stdin.read()
            elif not script_code:
                sys.stderr.write("Error: Provide a JavaScript expression, '-' for stdin, or '--file <path>'.\n")
                sys.exit(2)
            res = send_session_command({
                "action": "eval",
                "script": script_code,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(d.get("result")),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "eval-many":
            script_raw = args.scripts.strip()
            if _safe_is_file(script_raw):
                script_raw = Path(script_raw).read_text(encoding="utf-8")
            scripts = json.loads(script_raw)
            res = send_session_command({
                "action": "eval_many",
                "scripts": scripts,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(d.get("results")),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "inspect":
            props_list = [p.strip() for p in args.properties.split(",") if p.strip()] if args.properties else None
            actions_list = parse_actions_arg(args.actions)
            css_val = str(Path(args.css).resolve()) if _safe_is_file(args.css) else args.css
            res = send_session_command({
                "action": "inspect",
                "selector": args.selector,
                "actions": actions_list,
                "properties": props_list,
                "rules": args.rules,
                "css": css_val,
                "pseudo": args.pseudo,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(res, args, print_inspect_summary)
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "search":
            actions_list = parse_actions_arg(args.actions)
            res = send_session_command({
                "action": "search",
                "text": args.text,
                "keyword": args.keyword,
                "role": args.role,
                "tag": args.tag,
                "wait": args.wait,
                "actions": actions_list,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(res, args, print_search_results)
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "inject-css":
            css_arg = args.css
            if _safe_is_file(css_arg):
                css_arg = str(Path(css_arg).resolve())
            res = send_session_command({
                "action": "inject_css",
                "css": css_arg,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(res, args, lambda d: print(f"CSS injected into session '{d.get('session_name')}'"))
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "check-theme":
            css_arg = getattr(args, "css", None)
            if _safe_is_file(css_arg):
                css_arg = str(Path(css_arg).resolve())
            excl = [c.strip() for c in args.exclude_colors.split(",") if c.strip()] if getattr(args, "exclude_colors", None) else None
            res = send_session_command({
                "action": "check_theme",
                "theme": args.theme,
                "css": css_arg,
                "exclude_colors": excl,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(res, args, print_theme_flaws_summary)
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "inject-script":
            payload: Dict[str, Any] = {"action": "inject_script", "settle_ms": args.settle_ms}
            if _safe_is_file(args.file):
                payload["file"] = str(Path(args.file).resolve())
            else:
                payload["raw_js"] = args.file
            res = send_session_command(payload, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Script injected (executed={d.get('executed')}, added_nodes={d.get('added_count', 0)})"),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "interact":
            actions_list = parse_actions_arg(args.actions) or []
            res = send_session_command({
                "action": "interact",
                "actions": actions_list,
                "frame": getattr(args, "frame", None),
            }, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Interaction steps executed: {len(d.get('results', []))}"),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "screenshot":
            res = send_session_command({
                "action": "screenshot",
                "output": args.output,
                "selector": args.selector,
                "full_page": args.full_page,
            }, session_name=session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Screenshot saved to: {d.get('saved_to')}"),
            )
            sys.exit(0 if res.get("status") == "ok" else 1)

        elif session_cmd == "stop":
            res = stop_session(session_name)
            output_result(
                res,
                args,
                lambda d: print(f"Session '{session_name or 'default'}' stopped."),
            )
            sys.exit(0)

    runner = AuditorRunner(
        profile_path=getattr(args, "profile", None),
        use_profile=not getattr(args, "no_profile", False),
        headless=not getattr(args, "headful", False),
        clean_styles=getattr(args, "clean_styles", False),
    )

    if args.command == "audit":
        target_path = Path(args.file).resolve()
        if not target_path.exists():
            sys.stderr.write(f"Error: File not found: {target_path}\n")
            sys.exit(1)

        is_css = target_path.suffix == ".css" or ".user.css" in target_path.name
        is_js = target_path.suffix == ".js" or ".user.js" in target_path.name

        if is_css:
            urls_list = [u.strip() for u in args.urls.split(",") if u.strip()] if getattr(args, "urls", None) else None
            report = runner.audit_style(
                target_path,
                target_url=args.url,
                urls=urls_list,
                sample_pages=getattr(args, "sample_pages", 2),
                deep_hunt=getattr(args, "deep_hunt", False),
                output_dir=args.output,
            )
            output_result(report, args, print_style_summary)
        elif is_js:
            report = runner.audit_script(target_path, target_url=args.url, output_dir=args.output)
            output_result(report, args, print_script_summary)
        else:
            sys.stderr.write(f"Error: Unknown file type. Must be .user.css or .user.js: {target_path}\n")
            sys.exit(1)

    elif args.command == "scan":
        data = scan_directory(
            root_dir=args.dir,
            profile_path=getattr(args, "profile", None),
            use_profile=not getattr(args, "no_profile", False),
            only_broken=getattr(args, "only_broken", False),
            headless=not getattr(args, "headful", False),
        )
        output_result(data, args, print_scan_summary)

    elif args.command == "search":
        actions_list = parse_actions_arg(getattr(args, "actions", None))
        data = runner.search(
            url=args.url,
            text=args.text,
            keyword=args.keyword,
            role=args.role,
            tag=args.tag,
            wait=getattr(args, "wait", None),
            actions=actions_list,
        )
        output_result(data, args, print_search_results)

    elif args.command == "test-rule":
        data = runner.test_rule(
            url=args.url,
            css_rule=args.css,
            output_dir=args.output,
        )
        output_result(data, args, print_rule_summary)

    elif args.command == "screenshot":
        data = runner.screenshot(
            url=args.url,
            output_path=args.output,
            selector=args.selector,
            hover_selector=args.hover,
            wait_selector=args.wait,
            full_page=args.full_page,
        )
        output_result(data, args, lambda d: print(f"Screenshot captured and saved to: {d.get('saved_to')}"))

    elif args.command == "interact":
        actions_list = parse_actions_arg(args.actions) or []
        data = runner.interact(url=args.url, actions=actions_list)
        output_result(data, args, print_interact_summary)

    elif args.command == "inspect":
        actions_list = parse_actions_arg(getattr(args, "actions", None))
        props = [p.strip() for p in args.properties.split(",") if p.strip()] if getattr(args, "properties", None) else None
        data = runner.inspect_element(
            url=args.url,
            selector=args.selector,
            actions=actions_list,
            properties=props,
            include_rules=getattr(args, "rules", False),
            css=getattr(args, "css", None),
            pseudo=getattr(args, "pseudo", None),
        )
        output_result(data, args, print_inspect_summary)

    elif args.command == "map-site":
        data = runner.map_site(
            url=args.url,
            css_path=getattr(args, "css", None),
            max_archetypes=getattr(args, "max_archetypes", 8),
            max_pages=getattr(args, "max_pages", 25),
            output_dir=args.output,
        )
        output_result(data, args, print_map_summary)

    elif args.command == "extract-palette":
        data = runner.extract_palette(args.url)
        output_result(data, args, print_palette_summary)

    elif args.command == "check-contrast":
        data = runner.check_contrast(args.url, css_path=args.css)
        output_result(data, args, print_contrast_summary)

    elif args.command == "preview":
        headful_mode = not getattr(args, "headless", False)
        runner.preview(
            url=args.url,
            style_path=args.css,
            headful=headful_mode,
            screenshot=True,
            output_screenshot=args.output,
        )

    elif args.command == "extract-colors":
        res = runner.extract_css_colors(
            args.target,
            output_path=args.output,
            clipboard=getattr(args, "clipboard", False),
        )

        def print_extract_colors_summary(d: Dict[str, Any]) -> None:
            if d.get("copied_to_clipboard"):
                sys.stderr.write("Done! Extracted CSS colors copied to clipboard.\n")
            if args.output:
                print(f"Extracted color skeleton saved to: {args.output} ({len(d.get('skeleton', ''))} bytes)")
            else:
                print(d.get("skeleton", ""))
            swatches = d.get("swatches", [])
            if swatches and sys.stdout.isatty() and not args.output:
                print(f"\nColor Swatches ({d.get('total_swatches', len(swatches))} total):")
                for sw in swatches[:15]:
                    print(f"  • {sw['token']} ({sw['hex']}): {sw['count']} occurrences")
                if len(swatches) > 15:
                    print(f"  ... and {len(swatches) - 15} more colors.")

        output_result(res, args, print_extract_colors_summary)

    elif args.command == "check-responsive":
        viewports_list = None
        if getattr(args, "viewports", None):
            viewports_list = []
            for item in args.viewports.split(","):
                item = item.strip()
                if not item:
                    continue
                if "x" in item:
                    parts = item.split("x")
                    viewports_list.append((int(parts[0]), int(parts[1]), f"Custom ({item})"))

        data = runner.check_responsive(
            url=args.url,
            css_path=getattr(args, "css", None),
            viewports=viewports_list,
            screenshot_dir=getattr(args, "screenshots_dir", None),
        )
        output_result(data, args, print_responsive_summary)

    elif args.command == "check-theme":
        excl = [c.strip() for c in args.exclude_colors.split(",") if c.strip()] if getattr(args, "exclude_colors", None) else None
        data = runner.check_theme(
            url=args.url,
            target_theme=getattr(args, "theme", "dark"),
            css_path=getattr(args, "css", None),
            exclude_colors=excl,
        )
        output_result(data, args, print_theme_flaws_summary)

    elif args.command == "test-script":
        actions_list = None
        if getattr(args, "actions", None):
            try:
                actions_list = json.loads(args.actions)
            except Exception:
                p = Path(args.actions)
                if p.exists():
                    actions_list = json.loads(p.read_text(encoding="utf-8"))

        data = runner.test_script(
            script_path=args.file,
            target_url=getattr(args, "url", None),
            invoke_command=getattr(args, "menu_command", None),
            actions=actions_list,
            output_dir=getattr(args, "output", None),
        )
        output_result(data, args, print_script_test_summary)

    elif args.command == "check-spa":
        data = runner.check_spa(
            script_path=args.file,
            initial_url=getattr(args, "initial_url", None),
            target_spa_url=args.target_url,
        )
        output_result(data, args, print_spa_summary)

    elif args.command == "preview-js":
        headful_mode = not getattr(args, "headless", False)
        runner.preview_script(
            url=getattr(args, "url", None),
            script_path=args.file,
            headful=headful_mode,
            screenshot=True,
            output_screenshot=args.output,
        )

    elif args.command == "ext":
        action = args.ext_action
        if action == "status":
            st = runner.ext_status()
            output_result(st, args, print_ext_status)

        elif action == "list-styles":
            styles = runner.ext_list_styles()
            if getattr(args, "search", None):
                q = args.search.lower()
                styles = [s for s in styles if q in s["name"].lower() or any(q in d.lower() for d in s["domains"])]
            output_result(styles, args, print_ext_styles)

        elif action == "list-scripts":
            scripts = runner.ext_list_scripts()
            if getattr(args, "search", None):
                q = args.search.lower()
                scripts = [sc for sc in scripts if q in sc["name"].lower() or any(q in m.lower() for m in sc["matches"])]
            output_result(scripts, args, print_ext_scripts)

        elif action == "export-styles":
            count = runner.ext_export_styles(args.out_dir)
            output_result({"action": "export-styles", "count": count, "dir": args.out_dir}, args, lambda d: print(f"Exported {count} styles from Stylus DB to: {args.out_dir}"))

        elif action == "export-scripts":
            count = runner.ext_export_scripts(args.out_dir)
            output_result({"action": "export-scripts", "count": count, "dir": args.out_dir}, args, lambda d: print(f"Exported {count} scripts from Violentmonkey DB to: {args.out_dir}"))

        elif action == "diff-styles":
            diff = runner.ext_diff_styles(args.local_dir)
            output_result(diff, args, print_diff_styles)

        elif action == "diff-scripts":
            diff = runner.ext_diff_scripts(args.local_dir)
            output_result(diff, args, print_diff_scripts)

        elif action == "backup":
            styles_cnt = runner.ext_build_stylus_backup(args.styles_dir, args.out_stylus)
            vm_cnt = runner.ext_build_vm_backup(args.scripts_dir, args.out_vm)
            b_data = {"styles_bundled": styles_cnt, "scripts_bundled": vm_cnt, "stylus_backup": args.out_stylus, "vm_backup": args.out_vm}
            output_result(b_data, args, lambda d: print(f"Extension Backup Bundles Built: Stylus JSON: {args.out_stylus} ({styles_cnt} styles) | Violentmonkey ZIP: {args.out_vm} ({vm_cnt} scripts)"))

        elif action == "serve":
            runner.ext_serve(
                port=args.port,
                styles_dir=getattr(args, "styles_dir", None),
                scripts_dir=getattr(args, "scripts_dir", None),
            )

        elif action in ("enable-style", "disable-style"):
            enable = action == "enable-style"
            ok = runner.ext_set_style_enabled(args.target, enable)
            if ok:
                st = runner.ext_find_style(args.target)
                status_label = "Enabled" if enable else "Disabled"
                name = st["name"] if st else args.target
                res_data = {"status": "ok", "action": action, "name": name, "id": st["id"] if st else None, "enabled": enable}
                output_result(res_data, args, lambda d: print(f"Style successfully {status_label}: {name} (ID: {d[id]})"))
            else:
                sys.stderr.write(f"Style not found: {args.target}\n")
                sys.exit(1)

        elif action == "toggle-style":
            ok = runner.ext_toggle_style(args.target)
            if ok:
                st = runner.ext_find_style(args.target)
                status_label = "Enabled" if st and st["enabled"] else "Disabled"
                name = st["name"] if st else args.target
                res_data = {"status": "ok", "action": "toggle-style", "name": name, "id": st["id"] if st else None, "enabled": st["enabled"] if st else None}
                output_result(res_data, args, lambda d: print(f"Style toggled to {status_label}: {name} (ID: {d[id]})"))
            else:
                sys.stderr.write(f"Style not found: {args.target}\n")
                sys.exit(1)

        elif action == "delete-style":
            st = runner.ext_find_style(args.target)
            ok = runner.ext_delete_style(args.target)
            if ok:
                name = st["name"] if st else args.target
                res_data = {"status": "ok", "action": "delete-style", "name": name}
                output_result(res_data, args, lambda d: print(f"Style successfully deleted from Stylus: {name}"))
            else:
                sys.stderr.write(f"Style not found: {args.target}\n")
                sys.exit(1)

        elif action == "install-style":
            res = runner.ext_install_or_update_style(args.file, enabled=not args.disabled)
            act = "Updated" if res["action"] == "updated" else "Installed"
            output_result(res, args, lambda d: print(f"Style successfully {act} in Stylus: {res[name]} (ID: {res[id]}, Status: {'Enabled' if res['enabled'] else 'Disabled'})"))

        elif action in ("enable-script", "disable-script"):
            enable = action == "enable-script"
            ok = runner.ext_set_script_enabled(args.target, enable)
            if ok:
                sc = runner.ext_find_script(args.target)
                status_label = "Enabled" if enable else "Disabled"
                name = sc["name"] if sc else args.target
                res_data = {"status": "ok", "action": action, "name": name, "id": sc["id"] if sc else None, "enabled": enable}
                output_result(res_data, args, lambda d: print(f"Script successfully {status_label}: {name} (ID: {d[id]})"))
            else:
                sys.stderr.write(f"Script not found: {args.target}\n")
                sys.exit(1)

        elif action == "toggle-script":
            ok = runner.ext_toggle_script(args.target)
            if ok:
                sc = runner.ext_find_script(args.target)
                status_label = "Enabled" if sc and sc["enabled"] else "Disabled"
                name = sc["name"] if sc else args.target
                res_data = {"status": "ok", "action": "toggle-script", "name": name, "id": sc["id"] if sc else None, "enabled": sc["enabled"] if sc else None}
                output_result(res_data, args, lambda d: print(f"Script toggled to {status_label}: {name} (ID: {d[id]})"))
            else:
                sys.stderr.write(f"Script not found: {args.target}\n")
                sys.exit(1)

        elif action == "delete-script":
            sc = runner.ext_find_script(args.target)
            ok = runner.ext_delete_script(args.target)
            if ok:
                name = sc["name"] if sc else args.target
                res_data = {"status": "ok", "action": "delete-script", "name": name}
                output_result(res_data, args, lambda d: print(f"Script successfully deleted from Violentmonkey: {name}"))
            else:
                sys.stderr.write(f"Script not found: {args.target}\n")
                sys.exit(1)

        elif action == "install-script":
            res = runner.ext_install_or_update_script(args.file, enabled=not args.disabled)
            act = "Updated" if res["action"] == "updated" else "Installed"
            output_result(res, args, lambda d: print(f"Script successfully {act} in Violentmonkey: {res['name']} (ID: {res['id']}, Status: {'Enabled' if res['enabled'] else 'Disabled'})"))

        elif action == "sync":
            res = runner.ext_sync(args.styles_dir, args.scripts_dir)

            def print_sync(d: Dict[str, Any]) -> None:
                st = d["styles"]
                sc = d["scripts"]
                print(f"UserStyles Sync: {st['in_sync']} in sync, {len(st['installed'])} installed, {len(st['updated'])} updated (of {st['total']} local)")
                for item in st["installed"]:
                    print(f"  + Installed: {item['name']} ({item['file']})")
                for item in st["updated"]:
                    print(f"  ~ Updated:   {item['name']} ({item['file']})")
                print(f"UserScripts Sync: {sc['in_sync']} in sync, {len(sc['installed'])} installed, {len(sc['updated'])} updated (of {sc['total']} local)")
                for item in sc["installed"]:
                    print(f"  + Installed: {item['name']} ({item['file']})")
                for item in sc["updated"]:
                    print(f"  ~ Updated:   {item['name']} ({item['file']})")

            output_result(res, args, print_sync)


if __name__ == "__main__":
    main()
