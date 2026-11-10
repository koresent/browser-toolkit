import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

from .profile import ZenProfileContext
from .parser import parse_userstyle, parse_userscript
from .css_auditor import audit_css_on_page
from .js_auditor import inject_userscript, JSAuditResult, GM_SHIM_JS
from .crawler import discover_sample_subpages


def scan_directory(
    root_dir: str | Path,
    profile_path: Optional[str] = None,
    use_profile: bool = True,
    only_broken: bool = False,
    headless: bool = True,
) -> Dict[str, Any]:
    path = Path(root_dir).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    # Find all styles and scripts
    css_files = sorted(list(path.glob("**/*.user.css")))
    js_files = sorted(list(path.glob("**/*.user.js")))

    total_files = len(css_files) + len(js_files)
    results: List[Dict[str, Any]] = []

    with ZenProfileContext(profile_path, use_profile=use_profile) as temp_profile:
        with sync_playwright() as p:
            launch_kwargs: Dict[str, Any] = {"headless": headless}
            if temp_profile:
                context = p.firefox.launch_persistent_context(
                    user_data_dir=str(temp_profile),
                    **launch_kwargs,
                )
            else:
                browser = p.firefox.launch(**launch_kwargs)
                context = browser.new_context()

            try:
                page = context.new_page() if not context.pages else context.pages[0]

                # 1. Audit Styles
                for f in css_files:
                    try:
                        info = parse_userstyle(f)
                        url = info.get_target_url()
                        css = info.get_combined_css_for_url(url)

                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(1500)

                        res = audit_css_on_page(page, css)
                        matched_set = {m.selector for m in res.matched}

                        # If there are dead selectors, check 1 diverse subpage (e.g. item/details)
                        if res.dead:
                            subpages = discover_sample_subpages(page, url, max_subpages=1)
                            for sub_url in subpages:
                                try:
                                    page.goto(sub_url, wait_until="domcontentloaded", timeout=25000)
                                    page.wait_for_timeout(1000)
                                    sub_res = audit_css_on_page(page, css)
                                    matched_set.update({m.selector for m in sub_res.matched})
                                except Exception:
                                    pass

                        dead_selectors = [d.selector for d in res.dead if d.selector not in matched_set]
                        dead_cnt = len(dead_selectors)
                        total_cnt = res.total_selectors
                        matched_cnt = len(matched_set)

                        status = "OK" if dead_cnt == 0 and total_cnt > 0 else "BROKEN"

                        item = {
                            "type": "userstyle",
                            "name": info.name or f.name,
                            "file": str(f.relative_to(path)),
                            "url": url,
                            "status": status,
                            "total_selectors": total_cnt,
                            "matched": matched_cnt,
                            "dead": dead_cnt,
                            "dead_selectors": dead_selectors,
                        }
                        if not only_broken or status == "BROKEN":
                            results.append(item)
                    except Exception as e:
                        results.append({
                            "type": "userstyle",
                            "name": f.name,
                            "file": str(f.relative_to(path)),
                            "status": "ERROR",
                            "error": str(e),
                        })

                # 2. Audit Scripts
                for f in js_files:
                    try:
                        info = parse_userscript(f)
                        url = info.get_target_url()

                        js_res = JSAuditResult()
                        page.add_init_script(GM_SHIM_JS)
                        if info.run_at == "document-start":
                            page.add_init_script(info.raw_js)

                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(1500)

                        if info.run_at != "document-start":
                            try:
                                page.evaluate(info.raw_js)
                                js_res.executed = True
                            except Exception as eval_err:
                                js_res.errors.append(str(eval_err))

                        status = "OK" if not js_res.errors else "BROKEN"
                        item = {
                            "type": "userscript",
                            "name": info.name or f.name,
                            "file": str(f.relative_to(path)),
                            "url": url,
                            "status": status,
                            "errors": js_res.errors,
                        }
                        if not only_broken or status == "BROKEN":
                            results.append(item)
                    except Exception as e:
                        results.append({
                            "type": "userscript",
                            "name": f.name,
                            "file": str(f.relative_to(path)),
                            "status": "ERROR",
                            "error": str(e),
                        })

            finally:
                context.close()

    broken_count = sum(1 for r in results if r.get("status") in ("BROKEN", "ERROR"))
    return {
        "root_dir": str(path),
        "total_scanned": total_files,
        "broken_count": broken_count,
        "results": results,
    }
