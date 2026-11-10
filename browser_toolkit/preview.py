import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .parser import parse_userstyle

JS_HOT_RELOAD = r"""(cssText) => {
    let style = document.getElementById('__browser_toolkit_live_css__');
    if (!style) {
        style = document.createElement('style');
        style.id = '__browser_toolkit_live_css__';
        (document.head || document.documentElement).appendChild(style);
    }
    style.textContent = cssText;
}"""


def run_live_preview(
    url: str,
    style_path: str | Path,
    profile_path: Optional[str] = None,
    use_profile: bool = True,
    headless: bool = False,
    screenshot_on_change: bool = True,
    output_screenshot: str = "preview.png",
) -> None:
    style_file = Path(style_path).resolve()
    if not style_file.exists():
        raise FileNotFoundError(f"Style file not found: {style_file}")

    print(f"\n🔥 Starting Live Preview for {url}")
    print(f"📁 Watching: {style_file}")
    print(f"Mode: {'Headless' if headless else 'Interactive Headful Window'}")
    print("Press Ctrl+C to stop.\n")

    last_mtime = 0.0

    with ZenProfileContext(profile_path, use_profile=use_profile) as temp_profile:
        with sync_playwright() as p:
            launch_kwargs = {"headless": headless}
            if temp_profile:
                context = p.firefox.launch_persistent_context(
                    user_data_dir=str(temp_profile),
                    viewport={"width": 1440, "height": 900},
                    **launch_kwargs,
                )
                page = context.new_page() if not context.pages else context.pages[0]
            else:
                browser = p.firefox.launch(**launch_kwargs)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)

                while True:
                    cur_mtime = style_file.stat().st_mtime
                    if cur_mtime != last_mtime:
                        last_mtime = cur_mtime
                        try:
                            info = parse_userstyle(style_file)
                            css_content = info.get_combined_css_for_url(url)
                            page.evaluate(JS_HOT_RELOAD, css_content)

                            t_str = time.strftime("%H:%M:%S")
                            print(f"[{t_str}] ⚡ Hot-reloaded CSS ({len(css_content)} bytes)")

                            if screenshot_on_change:
                                page.screenshot(path=output_screenshot)
                                print(f"[{t_str}] 📸 Screenshot saved to {output_screenshot}")
                        except Exception as e:
                            print(f"[Error] Failed to reload CSS: {e}")

                    time.sleep(0.5)

            except KeyboardInterrupt:
                print("\nStopped live preview.")
            finally:
                context.close()
