"""
SPA navigation resilience checker for UserScripts.
Verifies whether a UserScript survives client-side SPA route transitions
(pushState, Turbo, YouTube yt-navigate-finish, etc.).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page

from .js_auditor import inject_userscript, JSAuditResult
from .navigation import safe_goto


@dataclass
class SPAResilienceReport:
    initial_url: str
    target_url: str
    survived: bool
    initial_added_elements_count: int
    post_navigation_elements_count: int
    errors_during_navigation: List[str] = field(default_factory=list)
    retained_selectors: List[str] = field(default_factory=list)
    lost_selectors: List[str] = field(default_factory=list)


JS_TRIGGER_SPA_EVENTS = r"""
(newUrl) => {
    history.pushState({}, '', newUrl);

    window.dispatchEvent(new PopStateEvent('popstate', { state: {} }));
    window.dispatchEvent(new HashChangeEvent('hashchange'));

    // Framework-specific SPA lifecycle events (Turbo, YouTube, PJAX)
    document.dispatchEvent(new CustomEvent('turbo:load', { bubbles: true }));
    document.dispatchEvent(new CustomEvent('turbo:render', { bubbles: true }));
    window.dispatchEvent(new CustomEvent('yt-navigate-finish', { bubbles: true }));
    document.dispatchEvent(new CustomEvent('yt-page-data-updated', { bubbles: true }));
    document.dispatchEvent(new CustomEvent('pjax:end', { bubbles: true }));
}
"""


def check_spa_resilience(
    page: Page,
    initial_url: str,
    target_spa_url: str,
    raw_js: str,
    run_at: str = "document-end",
) -> SPAResilienceReport:
    """Tests if a UserScript survives an in-page SPA navigation."""
    if initial_url and page.url != initial_url:
        safe_goto(page, initial_url, wait_until="domcontentloaded", timeout=30000)

    audit_initial = inject_userscript(page, raw_js, run_at=run_at, settle_ms=600)
    initial_selectors = [n.selector for n in audit_initial.mutations.added_nodes if n.selector]

    page.evaluate(JS_TRIGGER_SPA_EVENTS, target_spa_url)
    page.wait_for_timeout(800)

    retained = []
    lost = []
    for sel in initial_selectors:
        try:
            exists = page.evaluate(f"() => !!document.querySelector({sel!r})")
            if exists:
                retained.append(sel)
            else:
                lost.append(sel)
        except Exception:
            lost.append(sel)

    # Any new errors logged during transition?
    errors = audit_initial.errors

    survived = (len(lost) == 0 or len(retained) > 0) and not errors

    return SPAResilienceReport(
        initial_url=initial_url,
        target_url=target_spa_url,
        survived=survived,
        initial_added_elements_count=len(initial_selectors),
        post_navigation_elements_count=len(retained),
        errors_during_navigation=errors,
        retained_selectors=retained[:10],
        lost_selectors=lost[:10],
    )
