import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .profile import find_zen_profile
from .runner import AuditorRunner
from .scanner import scan_directory


def print_style_summary(report: Dict[str, Any]) -> None:
    audit = report.get("css_audit", {})
    total = audit.get("total_selectors", 0)
    matched = audit.get("cumulative_matched_count", audit.get("matched_count", 0))
    dead = audit.get("dead_count", 0)
    invalid = audit.get("invalid_count", 0)
    pages = report.get("tested_pages", [])

    print("\n" + "=" * 60)
    print(f"🎨 UserStyle Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"🌐 Base Target:    {report.get('target_url')}")
    print(f"📁 Source file:    {report.get('style_file')}")
    print(f"📸 Screenshots:    {report.get('output_dir')}/")
    if pages:
        print(f"📑 Tested Pages ({len(pages)}):")
        for p in pages:
            print(f"   • {p['url']} ({p.get('matched_count', 0)} selectors matched)")
    print("-" * 60)
    print(f"📊 Cumulative Summary: {total} total | ✅ {matched} matched | ❌ {dead} unconfirmed/dead | ⚠️ {invalid} invalid")
    print("-" * 60)

    if dead > 0:
        print("\n❌ Unmatched / Dead Selectors on Visited Pages:")
        for item in audit.get("dead", [])[:15]:
            sel = item["selector"]
            print(f"  • {sel}")
            suggestions = item.get("suggestions", [])
            if suggestions:
                print("    💡 Potential candidates found in DOM:")
                for s in suggestions[:2]:
                    cls_str = f".{s['className']}" if s.get("className") else ""
                    id_str = f"#{s['id']}" if s.get("id") else ""
                    kw = s.get("matchedKeyword", "")
                    print(f"       - <{s.get('tagName')}{id_str}{cls_str}> (matched '{kw}')")
        if dead > 15:
            print(f"  ... and {dead - 15} more unconfirmed selectors (may belong to other subpages).")

    if matched > 0:
        print("\n✅ Matched Selectors (Sample):")
        for item in audit.get("matched", [])[:8]:
            pages_found = len(item.get("found_on_pages", []))
            pages_suffix = f" (on {pages_found} page{'s' if pages_found > 1 else ''})" if pages_found else ""
            print(f"  • {item['selector']} -> {item.get('total_count', item.get('count', 0))} elements{pages_suffix}")
        if matched > 8:
            print(f"  ... and {matched - 8} more matched selectors.")

    print("=" * 60 + "\n")


def print_script_summary(report: Dict[str, Any]) -> None:
    audit = report.get("js_audit", {})
    executed = audit.get("executed", False)
    errors = audit.get("errors", [])
    commands = audit.get("registered_commands", [])
    console = audit.get("console_messages", [])
    mutations = audit.get("dom_mutations", {})
    net_reqs = audit.get("network_requests", [])

    print("\n" + "=" * 60)
    print(f"⚙️ UserScript Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"🌐 Target URL:     {report.get('target_url')}")
    print(f"📁 Source file:    {report.get('script_file')}")
    print(f"📸 Screenshot:     {report.get('screenshot')}")
    print("-" * 60)
    print(f"Execution: {'✅ Success' if executed and not errors else '❌ Issues Detected'}")
    if commands:
        print(f"Menu Commands ({len(commands)}): {', '.join(commands)}")

    added_cnt = mutations.get("added_count", 0)
    if added_cnt > 0:
        print(f"DOM Mutations: ➕ {added_cnt} elements added")
        for node in mutations.get("added_nodes", [])[:5]:
            snippet = f" (\"{node['text_snippet']}\")" if node.get("text_snippet") else ""
            print(f"  • <{node.get('tag_name')}> {node.get('selector')}{snippet}")
        if added_cnt > 5:
            print(f"    ... and {added_cnt - 5} more added elements.")

    if net_reqs:
        print(f"\n🌐 Network Requests ({len(net_reqs)}):")
        for req in net_reqs[:5]:
            print(f"  • [{req.get('method', 'GET')}] {req.get('url')} (Status: {req.get('status') or req.get('error')})")

    print("-" * 60)

    if errors:
        print("\n❌ Script Errors:")
        for err in errors:
            print(f"  • {err}")

    if console:
        print(f"\n💬 Recent Console Messages ({len(console)}):")
        for msg in console[-10:]:
            print(f"  [{msg.get('type', 'log')}] {msg.get('text', '')}")

    print("=" * 60 + "\n")


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

    print("\n" + "=" * 70)
    print(f"⚡ Interactive UserScript Test: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"🌐 Target:         {report.get('target_url')}")
    print(f"📁 Script:         {report.get('script_file')}")
    print(f"📸 Screenshot:     {report.get('screenshot')}")
    print("-" * 70)
    print(f"Status: {'✅ OK' if executed and not errors else '❌ Errors Detected'}")

    if commands:
        print(f"Registered Menu Commands: {', '.join(commands)}")

    if cmd_res:
        succ = cmd_res.get("success")
        print(f"Menu Command Trigger: {'✅ Succeeded' if succ else '❌ Failed: ' + str(cmd_res.get('error'))}")

    if added_nodes:
        print(f"\n➕ DOM Elements Inserted by Script ({len(added_nodes)}):")
        for n in added_nodes[:8]:
            snippet = f" (\"{n['text_snippet']}\")" if n.get("text_snippet") else ""
            print(f"  • <{n['tag_name']}> {n['selector']}{snippet}")
        if len(added_nodes) > 8:
            print(f"    ... and {len(added_nodes) - 8} more elements.")

    if net_reqs:
        print(f"\n🌐 Network Requests Sent ({len(net_reqs)}):")
        for req in net_reqs:
            st = req.get("status") if req.get("status") is not None else req.get("error")
            print(f"  • [{req.get('method')}] {req.get('url')} -> {st} ({req.get('durationMs', 0)}ms)")

    if clip:
        print(f"\n📋 Clipboard Writes ({len(clip)}):")
        for c in clip:
            print(f"  • \"{c.get('text', '')[:60]}\"")

    if notifs:
        print(f"\n🔔 Notifications ({len(notifs)}):")
        for n in notifs:
            print(f"  • [{n.get('title')}] {n.get('text')}")

    if errors:
        print(f"\n❌ Uncaught Errors ({len(errors)}):")
        for err in errors:
            print(f"  • {err}")

    if console:
        print(f"\n💬 Console Output ({len(console)}):")
        for msg in console[-10:]:
            print(f"  [{msg.get('type')}] {msg.get('text')}")

    print("=" * 70 + "\n")


def print_spa_summary(report: Dict[str, Any]) -> None:
    survived = report.get("survived", False)
    retained = report.get("retained_selectors", [])
    lost = report.get("lost_selectors", [])
    errors = report.get("errors", [])

    print("\n" + "=" * 70)
    print(f"🔄 SPA Route Resilience Audit: {report.get('script')}")
    print(f"Initial: {report.get('initial_url')}")
    print(f"Target:  {report.get('target_url')}")
    print("-" * 70)
    status_str = "✅ SURVIVED SPA TRANSITION" if survived else "❌ BROKEN IN SPA ROUTING"
    print(f"Verdict: {status_str}")
    print(f"Inserted Elements: {report.get('initial_added_elements_count', 0)} initial -> {report.get('post_navigation_elements_count', 0)} retained")

    if retained:
        print("\n✅ Elements Retained After Transition:")
        for sel in retained[:5]:
            print(f"  • {sel}")

    if lost:
        print("\n❌ Elements Wiped Out During Transition:")
        for sel in lost[:5]:
            print(f"  • {sel}")
        print("  💡 Tip: Listen to 'turbo:load', 'popstate', or 'yt-navigate-finish' to re-mount UI elements.")

    if errors:
        print(f"\n❌ Errors during transition ({len(errors)}):")
        for err in errors:
            print(f"  • {err}")

    print("=" * 70 + "\n")


def print_search_results(data: Dict[str, Any]) -> None:
    matches = data.get("matches", [])
    print("\n" + "=" * 60)
    print(f"🔍 DOM Search on {data.get('url')}")
    print(f"Matched Elements: {len(matches)}")
    print("-" * 60)

    for idx, m in enumerate(matches):
        print(f"\n#{idx + 1} <{m['tagName']}> | Visible: {'✅' if m.get('visible') else '❌'} | Dimensions: {m.get('rect', {}).get('width')}x{m.get('rect', {}).get('height')}px")
        if m.get("textSnippet"):
            print(f"   Text: \"{m['textSnippet']}\"")
        if m.get("className"):
            print(f"   Class: {m['className']}")
        if m.get("ariaLabel"):
            print(f"   aria-label: {m['ariaLabel']}")

        selectors = m.get("selectors", [])
        if selectors:
            print("   💡 Suggested Stable Selectors:")
            for s in selectors[:3]:
                unique_badge = "★ Unique (1 element)" if s.get("count") == 1 else f"({s.get('count')} elements)"
                print(f"      • {s['selector']}  [{unique_badge}]")

    print("\n" + "=" * 60 + "\n")


def print_scan_summary(data: Dict[str, Any]) -> None:
    total = data.get("total_scanned", 0)
    broken = data.get("broken_count", 0)
    healthy = total - broken

    print("\n" + "=" * 70)
    print(f"📂 Batch Scan Report: {data.get('root_dir')}")
    print(f"Total Files: {total} | ✅ Healthy: {healthy} | ❌ Broken / Errors: {broken}")
    print("-" * 70)

    for r in data.get("results", []):
        st = r.get("status")
        badge = "✅ OK" if st == "OK" else "❌ BROKEN"
        name = r.get("name")
        rel_file = r.get("file")
        if r.get("type") == "userstyle":
            details = f"{r.get('matched', 0)}/{r.get('total_selectors', 0)} matched"
            if st != "OK" and r.get("dead_selectors"):
                details += f" (Dead: {', '.join(r['dead_selectors'][:2])})"
        else:
            errs = r.get("errors", [])
            details = f"{len(errs)} errors" if errs else "Executed cleanly"

        print(f" {badge:<10} | {rel_file:<35} | {details}")

    print("=" * 70 + "\n")


def print_responsive_summary(report: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print(f"📱 Responsive Layout Audit: {report.get('url')}")
    print(f"Status: {'⚠️ Potential Issues Found' if report.get('has_any_issues') else '✅ Perfect Responsive Layout'}")
    print("=" * 70)

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

        status_icon = "❌" if has_h_overflow or len(touch_issues) > 3 else ("⚠️" if (touch_issues or text_issues or sticky_issues) else "✅")
        print(f"\n[{status_icon}] Viewport: {label}")
        print("-" * 50)

        if has_h_overflow:
            print(f"  ❌ HORIZONTAL OVERFLOW DETECTED: Page width {doc_w}px exceeds viewport {win_w}px (diff: +{doc_w - win_w}px)")
            print("     Elements causing layout blowout:")
            for el in overflow_els[:5]:
                print(f"       • <{el['tag_name']}> {el['selector']} (overflow: +{el['overflow_px']}px)")
                if el.get("text_snippet"):
                    print(f"         Text: \"{el['text_snippet']}\"")
                styles = el.get("computed_styles", {})
                print(f"         CSS: width={styles.get('width')}, max-width={styles.get('maxWidth')}, overflow-x={styles.get('overflowX')}")
        else:
            print(f"  ✅ No horizontal scroll (Page width fits within {win_w}px)")

        if touch_issues:
            print(f"  ⚠️ Touch targets < 24x24px ({len(touch_issues)} found):")
            for t in touch_issues[:4]:
                snippet = f" (\"{t['text_snippet']}\")" if t.get("text_snippet") else ""
                print(f"       • {t['selector']} [{t['width']}x{t['height']}px]{snippet}")

        if text_issues:
            print(f"  ⚠️ Text clipping / cut-off ({len(text_issues)} found):")
            for tc in text_issues[:3]:
                print(f"       • {tc['selector']} (scrollWidth: {tc['scroll_width']}px > clientWidth: {tc['client_width']}px) \"{tc['text_snippet']}\"")

        if sticky_issues:
            print(f"  ⚠️ Large Fixed/Sticky screen coverage ({len(sticky_issues)} found):")
            for sc in sticky_issues[:2]:
                print(f"       • {sc['selector']} covers {sc['height_ratio_pct']}% of screen height ({sc['position']})")

        if vp.get("screenshot_path"):
            print(f"  📸 Screenshot: {vp['screenshot_path']}")

    print("\n" + "=" * 70 + "\n")


def print_theme_flaws_summary(report: Dict[str, Any]) -> None:
    mode = report.get("theme_mode", "dark").upper()
    bleed = report.get("bleedthrough_issues", [])
    invis_text = report.get("invisible_text_issues", [])
    inputs = report.get("unstyled_input_issues", [])
    icons = report.get("invisible_icon_issues", [])
    has_scrollbar = report.get("has_custom_scrollbar", False)
    total_checked = report.get("total_elements_checked", 0)

    print("\n" + "=" * 70)
    print(f"🎨 Theme Quality & Visual Flaw Audit: {report.get('url')} (Mode: {mode})")
    print(f"Checked DOM Elements: {total_checked}")
    print("-" * 70)

    if bleed:
        print(f"\n❌ Unstyled Bleedthrough Containers ({len(bleed)} found):")
        for b in bleed[:8]:
            snippet = f" (\"{b['text_snippet']}\")" if b.get("text_snippet") else ""
            print(f"  • {b['selector']} [{b['bounds']['width']}x{b['bounds']['height']}px] -> {b['color']}{snippet}")
        if len(bleed) > 8:
            print(f"    ... and {len(bleed) - 8} more bright containers.")

    if invis_text:
        print(f"\n❌ Invisible / Blended Text ({len(invis_text)} found):")
        for t in invis_text[:8]:
            print(f"  • {t['selector']}: \"{t['text']}\"")
            print(f"    Ratio: {t['contrast_ratio']}:1 | color: {t['color']} on bg: {t['bg_color']}")
        if len(invis_text) > 8:
            print(f"    ... and {len(invis_text) - 8} more low-contrast text elements.")

    if inputs:
        print(f"\n⚠️ Unstyled / Broken Form Inputs ({len(inputs)} found):")
        for inp in inputs[:6]:
            print(f"  • <{inp['tag_name']} type=\"{inp['input_type']}\"> {inp['selector']}")
            print(f"    Issue: {inp['description']} (bg: {inp['bg_color']}, color: {inp['text_color']})")

    if icons:
        print(f"\n⚠️ Hidden / Low-Contrast SVG Icons ({len(icons)} found):")
        for ic in icons[:5]:
            print(f"  • {ic['selector']} ({ic['fill_or_stroke']} against {ic['parent_bg']}, ratio: {ic['contrast_ratio']}:1)")

    scrollbar_str = "✅ Custom scrollbar applied" if has_scrollbar else "⚠️ Native default scrollbars (consider adding scrollbar-color: #504945 #282828)"
    print(f"\nScrollbar: {scrollbar_str}")

    if not (bleed or invis_text or inputs or icons):
        if has_scrollbar:
            print("\n🎉 Flawless! No bleedthrough, invisible text, or broken form inputs detected.")
        else:
            print("\n🎉 Colors & contrast are clean! No bleedthrough, invisible text, or broken form inputs detected.")

    print("=" * 70 + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser-toolkit",
        description="Audit, inspect, and test UserStyles and UserScripts using Zen Browser profile and Playwright Gecko.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: audit
    audit_parser = subparsers.add_parser("audit", help="Audit a .user.css or .user.js file")
    audit_parser.add_argument("file", help="Path to .user.css or .user.js file")
    audit_parser.add_argument("--url", help="Override target base URL")
    audit_parser.add_argument("--urls", help="Comma-separated list of multiple URLs to audit across")
    audit_parser.add_argument("--sample-pages", type=int, default=2, help="Number of representative subpages to auto-discover and test (default: 2)")
    audit_parser.add_argument("--deep-hunt", action="store_true", help="Crawl site for unique DOM archetypes until 100% selectors are satisfied or limit reached")
    audit_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile (run clean)")
    audit_parser.add_argument("--profile", help="Path to custom profile directory")
    audit_parser.add_argument("--headful", action="store_true", help="Run with visible browser window")
    audit_parser.add_argument("--output", help="Directory to save screenshots and report")
    audit_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Batch scan directory of styles/scripts")
    scan_parser.add_argument("dir", help="Directory path to scan")
    scan_parser.add_argument("--only-broken", action="store_true", help="Only report broken files")
    scan_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    scan_parser.add_argument("--profile", help="Path to custom profile")
    scan_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    scan_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Search DOM by text/keyword and synthesize selectors")
    search_parser.add_argument("url", help="Target URL")
    search_parser.add_argument("--text", help="Search by visible text")
    search_parser.add_argument("--keyword", help="Search keyword in class, id, aria attributes")
    search_parser.add_argument("--role", help="Search by ARIA role")
    search_parser.add_argument("--tag", help="Filter by HTML tag")
    search_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    search_parser.add_argument("--profile", help="Path to custom profile")
    search_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    search_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: test-rule
    rule_parser = subparsers.add_parser("test-rule", help="Test candidate CSS rule on live page with impact analysis")
    rule_parser.add_argument("url", help="Target URL")
    rule_parser.add_argument("--css", required=True, help="CSS rule to test, e.g. '.foo { display: none; }'")
    rule_parser.add_argument("--output", help="Output directory for before/after screenshots")
    rule_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    rule_parser.add_argument("--profile", help="Path to custom profile")
    rule_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    rule_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: screenshot
    shot_parser = subparsers.add_parser("screenshot", help="Capture page or element screenshot with hover/wait")
    shot_parser.add_argument("url", help="Target URL")
    shot_parser.add_argument("--output", default="screenshot.png", help="Output image file path")
    shot_parser.add_argument("--selector", help="Capture only this element")
    shot_parser.add_argument("--hover", help="Hover over selector before screenshot")
    shot_parser.add_argument("--wait", help="Wait for selector before screenshot")
    shot_parser.add_argument("--full-page", action="store_true", help="Capture full page height")
    shot_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    shot_parser.add_argument("--profile", help="Path to custom profile")
    shot_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    shot_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: interact
    interact_parser = subparsers.add_parser("interact", help="Perform sequence of user actions (click, hover, fill)")
    interact_parser.add_argument("url", help="Target URL")
    interact_parser.add_argument("--actions", required=True, help="JSON string or file path containing list of actions")
    interact_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    interact_parser.add_argument("--profile", help="Path to custom profile")
    interact_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    interact_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a selector on a live URL")
    inspect_parser.add_argument("url", help="Target URL to open")
    inspect_parser.add_argument("--selector", required=True, help="CSS selector to inspect")
    inspect_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    inspect_parser.add_argument("--profile", help="Path to custom profile")
    inspect_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    inspect_parser.add_argument("--json", action="store_true", help="Output result as JSON")

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
    map_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: extract-palette
    pal_parser = subparsers.add_parser("extract-palette", help="Reverse engineer colors and CSS variables of target site")
    pal_parser.add_argument("url", help="Target URL")
    pal_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    pal_parser.add_argument("--profile", help="Path to custom profile")
    pal_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    pal_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: check-contrast
    contrast_parser = subparsers.add_parser("check-contrast", help="Audit WCAG text contrast across styled page")
    contrast_parser.add_argument("url", help="Target URL")
    contrast_parser.add_argument("--css", help="Path to .user.css file to test")
    contrast_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    contrast_parser.add_argument("--profile", help="Path to custom profile")
    contrast_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    contrast_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: preview
    preview_parser = subparsers.add_parser("preview", help="Live hot-reload preview server watching .user.css")
    preview_parser.add_argument("url", help="Target URL")
    preview_parser.add_argument("css", help="Path to .user.css file to watch")
    preview_parser.add_argument("--headful", action="store_true", default=True, help="Run with visible Zen window (default)")
    preview_parser.add_argument("--headless", action="store_true", help="Run headless taking screenshots on change")
    preview_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    preview_parser.add_argument("--profile", help="Path to custom profile")
    preview_parser.add_argument("--output", default="preview.png", help="Path to save preview screenshot")

    # Command: extract-colors
    extract_colors_parser = subparsers.add_parser("extract-colors", help="Extract pure color skeleton from CSS file or URL (port of Extract-ThemeColors)")
    extract_colors_parser.add_argument("target", help="Local .css file path OR website URL")
    extract_colors_parser.add_argument("--output", help="Path to write output CSS skeleton")
    extract_colors_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    extract_colors_parser.add_argument("--profile", help="Path to custom profile")

    # Command: check-responsive
    resp_parser = subparsers.add_parser("check-responsive", help="Audit responsive layout (horizontal overflow, touch targets, text clipping)")
    resp_parser.add_argument("url", help="Target URL")
    resp_parser.add_argument("--css", help="Optional path to .user.css to apply before testing")
    resp_parser.add_argument("--viewports", help="Comma-separated viewports, e.g. '390x844,768x1024,1440x900'")
    resp_parser.add_argument("--screenshots-dir", help="Directory to save viewport screenshots")
    resp_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    resp_parser.add_argument("--profile", help="Path to custom profile")
    resp_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    resp_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: check-theme
    theme_parser = subparsers.add_parser("check-theme", help="Audit theme flaws (bright bleedthrough, invisible text, unstyled inputs, hidden SVGs)")
    theme_parser.add_argument("url", help="Target URL")
    theme_parser.add_argument("--css", help="Optional path to .user.css to apply before testing")
    theme_parser.add_argument("--theme", choices=["dark", "light"], default="dark", help="Expected theme palette mode (default: dark)")
    theme_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    theme_parser.add_argument("--profile", help="Path to custom profile")
    theme_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    theme_parser.add_argument("--json", action="store_true", help="Output result as JSON")

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
    test_script_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: check-spa
    check_spa_parser = subparsers.add_parser("check-spa", help="Verify UserScript resilience across client-side SPA route transitions (Turbo, YouTube, etc.)")
    check_spa_parser.add_argument("file", help="Path to .user.js file")
    check_spa_parser.add_argument("target_url", help="Target SPA URL to navigate to (e.g. /watch?v=... or /tree/...)")
    check_spa_parser.add_argument("--initial-url", help="Initial starting URL (defaults to script's first @match)")
    check_spa_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    check_spa_parser.add_argument("--profile", help="Path to custom profile")
    check_spa_parser.add_argument("--headful", action="store_true", help="Run with visible window")
    check_spa_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: preview-js
    preview_js_parser = subparsers.add_parser("preview-js", help="Live hot-reload preview server watching .user.js")
    preview_js_parser.add_argument("file", help="Path to .user.js file to watch")
    preview_js_parser.add_argument("--url", help="Target URL (defaults to script @match)")
    preview_js_parser.add_argument("--headful", action="store_true", default=True, help="Run with visible Zen window (default)")
    preview_js_parser.add_argument("--headless", action="store_true", help="Run headless taking screenshots on change")
    preview_js_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    preview_js_parser.add_argument("--profile", help="Path to custom profile")
    preview_js_parser.add_argument("--output", default="preview_js.png", help="Path to save preview screenshot")

    # Command: ext (Extension management)
    ext_parser = subparsers.add_parser("ext", help="Manage Stylus and Violentmonkey extensions, styles, scripts, and sync")
    ext_subparsers = ext_parser.add_subparsers(dest="ext_action", required=True)

    # ext status
    status_p = ext_subparsers.add_parser("status", help="Show installed extensions, active profiles, and database stats")
    status_p.add_argument("--profile", help="Path to custom profile")
    status_p.add_argument("--json", action="store_true", help="Output result as JSON")

    # ext list-styles
    ls_styles_p = ext_subparsers.add_parser("list-styles", help="List all styles installed in Stylus")
    ls_styles_p.add_argument("--search", help="Filter styles by name or domain keyword")
    ls_styles_p.add_argument("--profile", help="Path to custom profile")
    ls_styles_p.add_argument("--json", action="store_true", help="Output result as JSON")

    # ext list-scripts
    ls_scripts_p = ext_subparsers.add_parser("list-scripts", help="List all scripts installed in Violentmonkey")
    ls_scripts_p.add_argument("--search", help="Filter scripts by name or match keyword")
    ls_scripts_p.add_argument("--profile", help="Path to custom profile")
    ls_scripts_p.add_argument("--json", action="store_true", help="Output result as JSON")

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
    diff_styles_p.add_argument("--json", action="store_true", help="Output result as JSON")

    # ext diff-scripts
    diff_scripts_p = ext_subparsers.add_parser("diff-scripts", help="Compare local .user.js files with active Violentmonkey database")
    diff_scripts_p.add_argument("local_dir", help="Path to local folder with userscripts")
    diff_scripts_p.add_argument("--profile", help="Path to custom profile")
    diff_scripts_p.add_argument("--json", action="store_true", help="Output result as JSON")

    # ext backup
    backup_p = ext_subparsers.add_parser("backup", help="Build ready-to-import backup bundles for Stylus and Violentmonkey")
    backup_p.add_argument("--styles-dir", default="/home/koresent/Projects/personal/userstyles", help="Local userstyles directory")
    backup_p.add_argument("--scripts-dir", default="/home/koresent/Projects/personal/userscripts", help="Local userscripts directory")
    backup_p.add_argument("--out-stylus", default="stylus-backup.json", help="Path for Stylus backup JSON")
    backup_p.add_argument("--out-vm", default="vm-backup.zip", help="Path for Violentmonkey backup ZIP")

    # ext serve
    serve_p = ext_subparsers.add_parser("serve", help="Launch interactive 1-click install & sync server hub")
    serve_p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    serve_p.add_argument("--styles-dir", help="Custom userstyles directory")
    serve_p.add_argument("--scripts-dir", help="Custom userscripts directory")
    serve_p.add_argument("--profile", help="Path to custom profile")

    # ext enable-style
    en_style_p = ext_subparsers.add_parser("enable-style", help="Enable an installed Stylus style by ID or name")
    en_style_p.add_argument("target", help="Numeric ID or style name")
    en_style_p.add_argument("--profile", help="Path to custom profile")

    # ext disable-style
    dis_style_p = ext_subparsers.add_parser("disable-style", help="Disable an installed Stylus style by ID or name")
    dis_style_p.add_argument("target", help="Numeric ID or style name")
    dis_style_p.add_argument("--profile", help="Path to custom profile")

    # ext toggle-style
    tog_style_p = ext_subparsers.add_parser("toggle-style", help="Toggle an installed Stylus style on/off")
    tog_style_p.add_argument("target", help="Numeric ID or style name")
    tog_style_p.add_argument("--profile", help="Path to custom profile")

    # ext delete-style
    del_style_p = ext_subparsers.add_parser("delete-style", help="Delete an installed style from Stylus DB")
    del_style_p.add_argument("target", help="Numeric ID or style name")
    del_style_p.add_argument("--profile", help="Path to custom profile")

    # ext install-style
    inst_style_p = ext_subparsers.add_parser("install-style", help="Install or update a .user.css file in Stylus DB")
    inst_style_p.add_argument("file", help="Path to .user.css file")
    inst_style_p.add_argument("--disabled", action="store_true", help="Install as disabled")
    inst_style_p.add_argument("--profile", help="Path to custom profile")

    # ext enable-script
    en_script_p = ext_subparsers.add_parser("enable-script", help="Enable an installed Violentmonkey script by ID or name")
    en_script_p.add_argument("target", help="Numeric ID or script name")
    en_script_p.add_argument("--profile", help="Path to custom profile")

    # ext disable-script
    dis_script_p = ext_subparsers.add_parser("disable-script", help="Disable an installed Violentmonkey script by ID or name")
    dis_script_p.add_argument("target", help="Numeric ID or script name")
    dis_script_p.add_argument("--profile", help="Path to custom profile")

    # ext toggle-script
    tog_script_p = ext_subparsers.add_parser("toggle-script", help="Toggle an installed Violentmonkey script on/off")
    tog_script_p.add_argument("target", help="Numeric ID or script name")
    tog_script_p.add_argument("--profile", help="Path to custom profile")

    # ext delete-script
    del_script_p = ext_subparsers.add_parser("delete-script", help="Delete an installed script from Violentmonkey DB")
    del_script_p.add_argument("target", help="Numeric ID or script name")
    del_script_p.add_argument("--profile", help="Path to custom profile")

    # ext install-script
    inst_script_p = ext_subparsers.add_parser("install-script", help="Install or update a .user.js file in Violentmonkey DB")
    inst_script_p.add_argument("file", help="Path to .user.js file")
    inst_script_p.add_argument("--disabled", action="store_true", help="Install as disabled")
    inst_script_p.add_argument("--profile", help="Path to custom profile")

    # Command: profile-info
    subparsers.add_parser("profile-info", help="Show detected Zen profile location")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "profile-info":
        prof = find_zen_profile()
        if prof:
            print(f"Zen profile found: {prof}")
        else:
            print("Zen profile not found.")
        sys.exit(0)

    runner = AuditorRunner(
        profile_path=getattr(args, "profile", None),
        use_profile=not getattr(args, "no_profile", False),
        headless=not getattr(args, "headful", False),
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
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print_style_summary(report)
        elif is_js:
            report = runner.audit_script(target_path, target_url=args.url, output_dir=args.output)
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print_script_summary(report)
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
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_scan_summary(data)

    elif args.command == "search":
        data = runner.search(
            url=args.url,
            text=args.text,
            keyword=args.keyword,
            role=args.role,
            tag=args.tag,
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_search_results(data)

    elif args.command == "test-rule":
        data = runner.test_rule(
            url=args.url,
            css_rule=args.css,
            output_dir=args.output,
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            impact = data.get("impact", {})
            matched = impact.get("matched", [])
            print("\n" + "=" * 60)
            print(f"🧪 Rule Impact Test on {args.url}")
            print(f"CSS: {args.css}")
            print(f"Matched elements: {len(matched)}")
            print(f"High-impact (>25% viewport) elements: {impact.get('highImpactCount', 0)}")
            print(f"Screenshots saved to: {data.get('screenshot_before')} and {data.get('screenshot_after')}")
            print("-" * 60)
            for m in matched[:5]:
                print(f" • <{m['tagName']}> | {m['dimensions']['width']}x{m['dimensions']['height']}px ({m['viewportRatioPercent']}% viewport) | Text: \"{m['textSnippet']}\"")
            print("=" * 60 + "\n")

    elif args.command == "screenshot":
        data = runner.screenshot(
            url=args.url,
            output_path=args.output,
            selector=args.selector,
            hover_selector=args.hover,
            wait_selector=args.wait,
            full_page=args.full_page,
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"\n📸 Screenshot captured and saved to: {data.get('saved_to')}\n")

    elif args.command == "interact":
        raw_actions = args.actions
        if Path(raw_actions).exists():
            with open(raw_actions, "r", encoding="utf-8") as f:
                actions_list = json.load(f)
        else:
            actions_list = json.loads(raw_actions)

        data = runner.interact(url=args.url, actions=actions_list)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"\n⚡ Action Sequence executed on {args.url}:")
            for res in data.get("action_results", []):
                print(f" Step #{res['step']}: {res['action']} -> {res['status']} {res.get('saved_to', '')}")
            print()

    elif args.command == "inspect":
        data = runner.inspect_element(args.url, args.selector)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            res = data.get("result", {})
            count = res.get("count", 0)
            print(f"\n🔍 Inspecting '{args.selector}' on {args.url}")
            print(f"Found elements: {count}")
            for idx, item in enumerate(res.get("items", [])):
                print(f"\n--- Element #{idx + 1} <{item['tagName']}> ---")
                print(f"Display: {item.get('display')}, Visibility: {item.get('visibility')}")
                print(f"Attributes: {item.get('attributes')}")
                print(f"HTML snippet:\n{item.get('outerHTML')}\n")


    elif args.command == "map-site":
        data = runner.map_site(
            url=args.url,
            css_path=getattr(args, "css", None),
            max_archetypes=getattr(args, "max_archetypes", 8),
            max_pages=getattr(args, "max_pages", 25),
            output_dir=args.output,
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            archs = data.get("archetypes", [])
            print("\n" + "=" * 70)
            print(f"🗺️ Site Template Archetypes: {data.get('base_url')}")
            print(f"Scanned {data.get('pages_visited')} pages | Discovered {len(archs)} unique structural layouts")
            print(f"Termination: {data.get('stopped_reason')}")
            print("-" * 70)
            for a in archs:
                matched_str = f" | {a['matched_selectors_count']} selectors" if a.get('matched_selectors_count') else ""
                sim_str = f" (similarity: {a['similarity_to_previous']})" if a['similarity_to_previous'] > 0 else " (root)"
                print(f" #{a['index']} [{a.get('title', 'No title')[:40]}]{sim_str}{matched_str}")
                print(f"    URL: {a['url']}")
                if a.get("screenshot"):
                    print(f"    📸 {a['screenshot']}")
            if data.get("cumulative_matched_count"):
                print(f"\n📊 Total Selectors Matched: {data['cumulative_matched_count']} | Remaining dead: {data.get('remaining_dead_count', 0)}")
            print("=" * 70 + "\n")

    elif args.command == "extract-palette":
        data = runner.extract_palette(args.url)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("\n" + "=" * 60)
            print(f"🎨 Palette Reverse Engineering: {args.url}")
            print("-" * 60)
            vars_list = data.get("site_color_variables", [])
            print(f"Native Site Color Variables Found ({len(vars_list)}):")
            for v in vars_list[:10]:
                print(f"  • {v['name']}: {v['value']}")
            if len(vars_list) > 10:
                print(f"  ... and {len(vars_list) - 10} more.")

            print("\nTop Computed Background Colors:")
            for bg in data.get("background_colors", [])[:5]:
                print(f"  • {bg['color']} ({bg['count']} elements, e.g. {', '.join(bg['samples'])})")

            print("\nTop Computed Text Colors:")
            for fg in data.get("text_colors", [])[:5]:
                print(f"  • {fg['color']} ({fg['count']} elements, e.g. {', '.join(fg['samples'])})")

            print(f"\nSVGs & Icons: {data.get('svg_count', 0)} SVG icons found on page.")
            print("=" * 60 + "\n")

    elif args.command == "check-contrast":
        data = runner.check_contrast(args.url, css_path=args.css)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            audit = data.get("contrast_audit", {})
            issues = audit.get("issues", [])
            total = audit.get("totalChecked", 0)
            failed = audit.get("failedCount", 0)
            print("\n" + "=" * 60)
            print(f"⚖️ WCAG Contrast Audit on {args.url}")
            print(f"Checked Text Nodes: {total} | ❌ Issues: {failed} | ✅ Passing: {total - failed}")
            print("-" * 60)
            if issues:
                print("Low Contrast Elements (Needs Gruvbox adjustment):")
                for iss in issues[:10]:
                    print(f"  • <{iss['tagName']}> \"{iss['textSnippet']}\"")
                    print(f"    Ratio: {iss['contrastRatio']}:1 (Required: {iss['requiredRatio']}:1) | fg: {iss['fg']}, bg: {iss['bg']}")
                if len(issues) > 10:
                    print(f"    ... and {len(issues) - 10} more low-contrast elements.")
            else:
                print("🎉 Excellent! All visible text elements meet WCAG contrast thresholds!")
            print("=" * 60 + "\n")

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
        res = runner.extract_css_colors(args.target, output_path=args.output)
        if args.output:
            print(f"\n✨ Extracted color skeleton saved to: {args.output} ({len(res)} bytes)\n")
        else:
            print("\n" + "=" * 60)
            print(f"🎨 Extracted Color Skeleton for {args.target}")
            print("-" * 60)
            print(res[:2000] + ("\n... [truncated]" if len(res) > 2000 else ""))
            print("=" * 60 + "\n")

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
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_responsive_summary(data)

    elif args.command == "check-theme":
        data = runner.check_theme(
            url=args.url,
            target_theme=getattr(args, "theme", "dark"),
            css_path=getattr(args, "css", None),
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_theme_flaws_summary(data)

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
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_script_test_summary(data)

    elif args.command == "check-spa":
        data = runner.check_spa(
            script_path=args.file,
            initial_url=getattr(args, "initial_url", None),
            target_spa_url=args.target_url,
        )
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_spa_summary(data)

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
            if args.json:
                print(json.dumps(st, indent=2, ensure_ascii=False))
            else:
                print("\n" + "=" * 65)
                print("🧩 Zen Browser Extension Status")
                print("-" * 65)
                print(f"Profile directory:  {st['profile_dir']}")
                print(f"Stylus DB:          {st['stylus_db']}")
                print(f"Violentmonkey DB:   {st['violentmonkey_db']}")
                print("-" * 65)
                print(f"🎨 Stylus Styles:        {st['stylus_installed_count']} installed ({st['active_styles_count']} active)")
                print(f"⚙️ Violentmonkey Scripts: {st['violentmonkey_installed_count']} installed ({st['active_scripts_count']} active)")
                print("=" * 65 + "\n")

        elif action == "list-styles":
            styles = runner.ext_list_styles()
            if getattr(args, "search", None):
                q = args.search.lower()
                styles = [s for s in styles if q in s["name"].lower() or any(q in d.lower() for d in s["domains"])]
            if args.json:
                print(json.dumps(styles, indent=2, ensure_ascii=False))
            else:
                print("\n" + "=" * 70)
                print(f"🎨 Stylus Installed Styles ({len(styles)}):")
                print("-" * 70)
                for s in styles:
                    status_badge = "✅" if s["enabled"] else "⏸️"
                    doms = ", ".join(s["domains"][:2]) if s["domains"] else "all sites"
                    print(f"  {status_badge} [{s['id']:<3}] {s['name']:<42} -> {doms}")
                print("=" * 70 + "\n")

        elif action == "list-scripts":
            scripts = runner.ext_list_scripts()
            if getattr(args, "search", None):
                q = args.search.lower()
                scripts = [sc for sc in scripts if q in sc["name"].lower() or any(q in m.lower() for m in sc["matches"])]
            if args.json:
                print(json.dumps(scripts, indent=2, ensure_ascii=False))
            else:
                print("\n" + "=" * 70)
                print(f"⚙️ Violentmonkey Installed Scripts ({len(scripts)}):")
                print("-" * 70)
                for sc in scripts:
                    status_badge = "✅" if sc["enabled"] else "⏸️"
                    matches = ", ".join(sc["matches"][:2]) if sc["matches"] else "*://*/*"
                    print(f"  {status_badge} [{sc['id']:<3}] {sc['name']:<40} (v{sc['version']}) -> {matches}")
                print("=" * 70 + "\n")

        elif action == "export-styles":
            count = runner.ext_export_styles(args.out_dir)
            print(f"\n✨ Exported {count} styles from Stylus DB to: {args.out_dir}\n")

        elif action == "export-scripts":
            count = runner.ext_export_scripts(args.out_dir)
            print(f"\n✨ Exported {count} scripts from Violentmonkey DB to: {args.out_dir}\n")

        elif action == "diff-styles":
            diff = runner.ext_diff_styles(args.local_dir)
            if args.json:
                print(json.dumps(diff, indent=2, ensure_ascii=False))
            else:
                print("\n" + "=" * 70)
                print(f"🔍 UserStyles Sync Diff: Local ({args.local_dir}) vs Stylus DB")
                print(f"Local files: {diff['total_local']} | Installed in Stylus: {diff['total_installed']} | In Sync: {diff['in_sync']}")
                print("-" * 70)
                if diff["modified"]:
                    print(f"\n⚠️ Modified / Out of Sync ({len(diff['modified'])}):")
                    for m in diff["modified"]:
                        print(f"  • {m['name']} ({m['file']}) [Local: {m['local_size']}B, Stylus: {m['installed_size']}B]")
                if diff["only_local"]:
                    print(f"\n➕ Only Local (Not in Stylus) ({len(diff['only_local'])}):")
                    for ol in diff["only_local"][:10]:
                        print(f"  • {ol['name']} ({ol['file']})")
                if diff["only_installed"]:
                    print(f"\n📦 Only in Stylus (Missing in git repo) ({len(diff['only_installed'])}):")
                    for oi in diff["only_installed"][:10]:
                        print(f"  • [{oi['id']}] {oi['name']}")
                print("=" * 70 + "\n")

        elif action == "diff-scripts":
            diff = runner.ext_diff_scripts(args.local_dir)
            if args.json:
                print(json.dumps(diff, indent=2, ensure_ascii=False))
            else:
                print("\n" + "=" * 70)
                print(f"🔍 UserScripts Sync Diff: Local ({args.local_dir}) vs Violentmonkey DB")
                print(f"Local files: {diff['total_local']} | Installed in VM: {diff['total_installed']} | In Sync: {diff['in_sync']}")
                print("-" * 70)
                if diff["modified"]:
                    print(f"\n⚠️ Modified / Out of Sync ({len(diff['modified'])}):")
                    for m in diff["modified"]:
                        print(f"  • {m['name']} ({m['file']}) [Local: {m['local_size']}B, VM: {m['installed_size']}B]")
                if diff["only_local"]:
                    print(f"\n➕ Only Local (Not in VM) ({len(diff['only_local'])}):")
                    for ol in diff["only_local"][:10]:
                        print(f"  • {ol['name']} ({ol['file']})")
                if diff["only_installed"]:
                    print(f"\n📦 Only in Violentmonkey (Missing in git repo) ({len(diff['only_installed'])}):")
                    for oi in diff["only_installed"][:10]:
                        print(f"  • [{oi['id']}] {oi['name']} (v{oi['version']})")
                print("=" * 70 + "\n")

        elif action == "backup":
            styles_cnt = runner.ext_build_stylus_backup(args.styles_dir, args.out_stylus)
            vm_cnt = runner.ext_build_vm_backup(args.scripts_dir, args.out_vm)
            print("\n" + "=" * 65)
            print("📦 Extension Backup Bundles Built Successfully:")
            print(f"  • Stylus JSON:         {args.out_stylus} ({styles_cnt} styles bundled)")
            print(f"  • Violentmonkey ZIP:   {args.out_vm} ({vm_cnt} scripts bundled)")
            print("-" * 65)
            print("💡 In Stylus: Manage -> Import -> select JSON")
            print("💡 In Violentmonkey: Settings -> Import from zip -> select ZIP")
            print("=" * 65 + "\n")

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
                print(f"\n✅ Style successfully {status_label}: {name} (ID: {st['id'] if st else '?'})\n")
            else:
                print(f"\n❌ Style not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "toggle-style":
            ok = runner.ext_toggle_style(args.target)
            if ok:
                st = runner.ext_find_style(args.target)
                status_label = "Enabled" if st and st["enabled"] else "Disabled"
                name = st["name"] if st else args.target
                print(f"\n🔄 Style toggled to {status_label}: {name} (ID: {st['id'] if st else '?'})\n")
            else:
                print(f"\n❌ Style not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "delete-style":
            st = runner.ext_find_style(args.target)
            ok = runner.ext_delete_style(args.target)
            if ok:
                name = st["name"] if st else args.target
                print(f"\n🗑️ Style successfully deleted from Stylus: {name}\n")
            else:
                print(f"\n❌ Style not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "install-style":
            res = runner.ext_install_or_update_style(args.file, enabled=not args.disabled)
            act = "Updated" if res["action"] == "updated" else "Installed"
            print(f"\n✨ Style successfully {act} in Stylus: {res['name']} (ID: {res['id']}, Status: {'Enabled' if res['enabled'] else 'Disabled'})\n")

        elif action in ("enable-script", "disable-script"):
            enable = action == "enable-script"
            ok = runner.ext_set_script_enabled(args.target, enable)
            if ok:
                sc = runner.ext_find_script(args.target)
                status_label = "Enabled" if enable else "Disabled"
                name = sc["name"] if sc else args.target
                print(f"\n✅ Script successfully {status_label}: {name} (ID: {sc['id'] if sc else '?'})\n")
            else:
                print(f"\n❌ Script not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "toggle-script":
            ok = runner.ext_toggle_script(args.target)
            if ok:
                sc = runner.ext_find_script(args.target)
                status_label = "Enabled" if sc and sc["enabled"] else "Disabled"
                name = sc["name"] if sc else args.target
                print(f"\n🔄 Script toggled to {status_label}: {name} (ID: {sc['id'] if sc else '?'})\n")
            else:
                print(f"\n❌ Script not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "delete-script":
            sc = runner.ext_find_script(args.target)
            ok = runner.ext_delete_script(args.target)
            if ok:
                name = sc["name"] if sc else args.target
                print(f"\n🗑️ Script successfully deleted from Violentmonkey: {name}\n")
            else:
                print(f"\n❌ Script not found: {args.target}\n", file=sys.stderr)
                sys.exit(1)

        elif action == "install-script":
            res = runner.ext_install_or_update_script(args.file, enabled=not args.disabled)
            act = "Updated" if res["action"] == "updated" else "Installed"
            print(f"\n✨ Script successfully {act} in Violentmonkey: {res['name']} (ID: {res['id']}, Status: {'Enabled' if res['enabled'] else 'Disabled'})\n")


if __name__ == "__main__":
    main()
