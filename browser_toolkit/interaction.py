from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page, Locator


class PageInteractor:
    def __init__(self, page: Page):
        self.page = page

    def click(self, selector: str, timeout: int = 5000) -> bool:
        """Clicks an element by selector."""
        try:
            self.page.click(selector, timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to click '{selector}': {e}")

    def hover(self, selector: str, timeout: int = 5000) -> bool:
        """Hovers over an element to trigger CSS :hover states or dropdowns."""
        try:
            self.page.hover(selector, timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to hover over '{selector}': {e}")

    def fill(self, selector: str, text: str, timeout: int = 5000) -> bool:
        """Fills an input or textarea."""
        try:
            self.page.fill(selector, text, timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to fill '{selector}': {e}")

    def press(self, key: str) -> bool:
        """Presses a keyboard key, e.g. 'Enter', 'Escape'."""
        try:
            self.page.keyboard.press(key)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to press key '{key}': {e}")

    def wait_for(self, selector: str, timeout: int = 5000) -> bool:
        """Waits for an element to appear in DOM."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Timed out waiting for '{selector}': {e}")

    def capture_screenshot(
        self,
        output_path: str | Path,
        selector: Optional[str] = None,
        full_page: bool = False,
    ) -> Path:
        """
        Captures a screenshot:
        - If selector is provided: captures only that specific element!
        - Otherwise: captures viewport or full_page.
        """
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        if selector:
            loc = self.page.locator(selector).first
            loc.screenshot(path=str(out))
        else:
            self.page.screenshot(path=str(out), full_page=full_page)

        return out


def execute_action_sequence(
    page: Page,
    actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Executes a list of actions in sequence, e.g.:
    [
        {"action": "hover", "selector": "#user-menu"},
        {"action": "wait", "ms": 500},
        {"action": "screenshot", "path": "menu.png", "selector": ".dropdown-content"}
    ]
    """
    interactor = PageInteractor(page)
    results = []

    for idx, act in enumerate(actions):
        action_type = act.get("action", "").lower()
        sel = act.get("selector")
        res = {"step": idx + 1, "action": action_type, "status": "success"}

        try:
            if action_type == "click":
                interactor.click(sel)
            elif action_type == "hover":
                interactor.hover(sel)
            elif action_type == "fill":
                interactor.fill(sel, act.get("text", ""))
            elif action_type == "press":
                interactor.press(act.get("key", "Enter"))
            elif action_type == "wait_for":
                interactor.wait_for(sel)
            elif action_type == "wait":
                ms = int(act.get("ms", 1000))
                page.wait_for_timeout(ms)
            elif action_type == "screenshot":
                p = act.get("path", f"action_step_{idx + 1}.png")
                full = bool(act.get("full_page", False))
                saved = interactor.capture_screenshot(p, selector=sel, full_page=full)
                res["saved_to"] = str(saved)
            else:
                res["status"] = "unknown_action"

        except Exception as e:
            res["status"] = "failed"
            res["error"] = str(e)

        results.append(res)

    return results
