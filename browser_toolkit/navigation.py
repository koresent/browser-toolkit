from typing import Any, Optional
from playwright.sync_api import Page, Response


def safe_goto(
    page: Page,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 30000,
    **kwargs: Any,
) -> Optional[Response]:
    """
    Navigate page safely, catching Gecko/Firefox client-redirect aborts (NS_BINDING_ABORTED).
    """
    try:
        return page.goto(url, wait_until=wait_until, timeout=timeout, **kwargs)
    except Exception as e:
        err_msg = str(e)
        if "NS_BINDING_ABORTED" in err_msg or "net::ERR_ABORTED" in err_msg:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(timeout, 15000))
                return None
            except Exception:
                return None
        raise
