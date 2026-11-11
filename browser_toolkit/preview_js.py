"""
Live hot-reload preview server for UserScripts (.user.js).
Watches .user.js on disk, reloads page, injects script, and streams DOM mutations,
errors, and console output in real-time.
"""

import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .parser import parse_userscript
from .js_auditor import inject_userscript
from .navigation import safe_goto
from .browser_backend import safe_launch_persistent_context, safe_launch_browser


def run_live_script_preview(
    url: str,
    script_path: str | Path,
    profile_path: Optional[str] = None,
    use_profile: bool = True,
    headless: bool = False,
    screenshot_on_change: bool = True,
    output_screenshot: str = "preview_js.png",
) -> None:
    script_file = Path(script_path).resolve()
    if not script_file.exists():
        raise FileNotFoundError(f"Script file not found: {script_file}")

    info = parse_userscript(script_file)
    target_url = url or info.get_target_url()

    print(f"\nStarting Live UserScript Preview for {target_url}")
    print(f"Watching: {script_file}")
    print(f"Mode: {'Headless' if headless else 'Interactive Headful Window'}")
    print("Press Ctrl+C to stop.\n")

    last_mtime = 0.0

    with ZenProfileContext(profile_path, use_profile=use_profile) as temp_profile:
        with sync_playwright() as p:
            launch_kwargs = {"headless": headless}
            if temp_profile:
                context = safe_launch_persistent_context(
                    p,
                    user_data_dir=str(temp_profile),
                    viewport={"width": 1440, "height": 900},
                    **launch_kwargs,
                )
                page = context.new_page() if not context.pages else context.pages[0]
            else:
                browser = safe_launch_browser(p, **launch_kwargs)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()

            try:
                safe_goto(page, target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1000)

                while True:
                    cur_mtime = script_file.stat().st_mtime
                    if cur_mtime > last_mtime:
                        t0 = time.time()
                        fresh_code = script_file.read_text(encoding="utf-8", errors="replace")
                        last_mtime = cur_mtime

                        page.reload(wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(500)

                        res = inject_userscript(page, raw_js=fresh_code, run_at=info.run_at or "document-end")
                        dt_ms = int((time.time() - t0) * 1000)

                        err_count = len(res.errors)
                        mut_count = len(res.mutations.added_nodes)
                        net_count = len(res.network_requests)
                        cmds = ", ".join(res.registered_commands) if res.registered_commands else "None"

                        status = "OK" if err_count == 0 else f"{err_count} errors"
                        print(f"[{time.strftime('%H:%M:%S')}] {status} ({dt_ms}ms) | Added nodes: {mut_count} | Net reqs: {net_count} | Commands: {cmds}")

                        if res.errors:
                            for err in res.errors[:3]:
                                print(f"    Error: {err}")

                        if screenshot_on_change:
                            page.screenshot(path=output_screenshot)

                    time.sleep(0.3)

            except KeyboardInterrupt:
                print("\nLive preview stopped.")
            finally:
                context.close()
