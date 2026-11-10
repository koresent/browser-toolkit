import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .profile import find_zen_profile
from .runner import AuditorRunner


def print_style_summary(report: Dict[str, Any]) -> None:
    audit = report.get("css_audit", {})
    total = audit.get("total_selectors", 0)
    matched = audit.get("matched_count", 0)
    dead = audit.get("dead_count", 0)
    invalid = audit.get("invalid_count", 0)

    print("\n" + "=" * 60)
    print(f"🎨 UserStyle Audit: {report.get('name')} (v{report.get('version', 'unknown')})")
    print(f"🌐 Target URL:     {report.get('target_url')}")
    print(f"📁 Source file:    {report.get('style_file')}")
    print(f"📸 Screenshots:    {report.get('output_dir')}/")
    print("-" * 60)
    print(f"📊 Selectors Summary: {total} total | ✅ {matched} matched | ❌ {dead} dead | ⚠️ {invalid} invalid")
    print("-" * 60)

    if dead > 0:
        print("\n❌ Dead Selectors (Need Attention):")
        for item in audit.get("dead", []):
            sel = item["selector"]
            print(f"  • {sel}")
            suggestions = item.get("suggestions", [])
            if suggestions:
                print("    💡 Potential candidates found in DOM:")
                for s in suggestions[:3]:
                    cls_str = f".{s['className']}" if s.get("className") else ""
                    id_str = f"#{s['id']}" if s.get("id") else ""
                    kw = s.get("matchedKeyword", "")
                    print(f"       - <{s.get('tagName')}{id_str}{cls_str}> (matched '{kw}')")

    if matched > 0:
        print("\n✅ Matched Selectors (Sample):")
        for item in audit.get("matched", [])[:10]:
            print(f"  • {item['selector']} -> {item['count']} elements")
        if matched > 10:
            print(f"  ... and {matched - 10} more matched selectors.")

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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="browser-auditor",
        description="Audit and inspect UserStyles and UserScripts using Zen Browser profile and Playwright Gecko.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: audit
    audit_parser = subparsers.add_parser("audit", help="Audit a .user.css or .user.js file")
    audit_parser.add_argument("file", help="Path to .user.css or .user.js file")
    audit_parser.add_argument("--url", help="Override target URL")
    audit_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile (run clean)")
    audit_parser.add_argument("--profile", help="Path to custom profile directory")
    audit_parser.add_argument("--headful", action="store_true", help="Run with visible browser window")
    audit_parser.add_argument("--output", help="Directory to save screenshots and report")
    audit_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # Command: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a selector on a live URL")
    inspect_parser.add_argument("url", help="Target URL to open")
    inspect_parser.add_argument("--selector", required=True, help="CSS selector to inspect")
    inspect_parser.add_argument("--no-profile", action="store_true", help="Do not clone Zen profile")
    inspect_parser.add_argument("--profile", help="Path to custom profile directory")
    inspect_parser.add_argument("--headful", action="store_true", help="Run with visible browser window")
    inspect_parser.add_argument("--json", action="store_true", help="Output result as JSON")

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
            report = runner.audit_style(target_path, target_url=args.url, output_dir=args.output)
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


if __name__ == "__main__":
    main()
