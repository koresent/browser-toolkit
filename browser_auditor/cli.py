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

    print("\n" + "=" * 60)
    print(f"⚙️ UserScript Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"🌐 Target URL:     {report.get('target_url')}")
    print(f"📁 Source file:    {report.get('script_file')}")
    print(f"📸 Screenshot:     {report.get('screenshot')}")
    print("-" * 60)
    print(f"Execution: {'✅ Success' if executed and not errors else '❌ Issues Detected'}")
    if commands:
        print(f"Menu Commands: {', '.join(commands)}")
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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="browser-auditor",
        description="Audit and inspect UserStyles and UserScripts using Zen Browser profile and Playwright Gecko.",
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

    # Command: profile-info
    subparsers.add_parser("profile-info", help="Show detected Zen profile location")

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


if __name__ == "__main__":
    main()
