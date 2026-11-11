from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.sync_api import Page, Locator


class PageInteractor:
    def __init__(self, page: Page):
        self.page = page

    def click(self, selector: str, timeout: int = 5000, force: bool = False) -> bool:
        """Clicks an element by selector."""
        try:
            self.page.click(selector, timeout=timeout, force=force)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to click '{selector}': {e}")

    def click_text(self, text: str, timeout: int = 5000, force: bool = False) -> bool:
        """Clicks an element containing the given text."""
        try:
            loc = self.page.get_by_text(text, exact=False).first
            loc.click(timeout=timeout, force=force)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to click text '{text}': {e}")

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
        """Waits for an element to appear in DOM or a millisecond duration if numeric."""
        try:
            s_str = str(selector).strip()
            if s_str.isdigit():
                self.page.wait_for_timeout(int(s_str))
                return True
            self.page.wait_for_selector(s_str, timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Timed out waiting for '{selector}': {e}")

    def scroll(self, selector: Optional[str] = None, x: int = 0, y: int = 0) -> bool:
        """Scrolls container or page by (x, y) delta."""
        try:
            if selector:
                self.page.eval_on_selector(
                    selector,
                    "(el, [dx, dy]) => { el.scrollLeft += dx; el.scrollTop += dy; }",
                    [x, y],
                )
            else:
                self.page.mouse.wheel(x, y)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to scroll '{selector or 'page'}': {e}")

    def scroll_into_view(self, selector: str, timeout: int = 5000) -> bool:
        """Scrolls element into view."""
        try:
            loc = self.page.locator(selector).first
            loc.scroll_into_view_if_needed(timeout=timeout)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to scroll '{selector}' into view: {e}")

    def evaluate(self, script: str) -> Any:
        """Evaluates arbitrary JavaScript in the page context."""
        try:
            return self.page.evaluate(script)
        except Exception as e:
            raise RuntimeError(f"Failed to evaluate script: {e}")

    def evaluate_many(self, scripts: Dict[str, str] | List[str]) -> Dict[str, Any]:
        """Evaluates multiple JavaScript expressions or statements in a batch."""
        res: Dict[str, Any] = {}
        if isinstance(scripts, dict):
            items = scripts.items()
        elif isinstance(scripts, list):
            items = [(str(i), s) for i, s in enumerate(scripts)]
        else:
            raise ValueError("scripts must be a dict or list")

        for key, code in items:
            try:
                res[key] = self.page.evaluate(code)
            except Exception as e:
                res[key] = f"error: {e}"
        return res

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
                timeout = int(act.get("timeout", 5000))
                force = bool(act.get("force", False))
                if sel:
                    interactor.click(sel, timeout=timeout, force=force)
                elif act.get("text"):
                    interactor.click_text(act["text"], timeout=timeout, force=force)
                else:
                    raise ValueError("Click action requires 'selector' or 'text'")
            elif action_type == "click_text":
                interactor.click_text(
                    act.get("text", ""),
                    timeout=int(act.get("timeout", 5000)),
                    force=bool(act.get("force", False)),
                )
            elif action_type == "hover":
                interactor.hover(sel, timeout=int(act.get("timeout", 5000)))
            elif action_type == "fill":
                interactor.fill(sel, act.get("text", ""), timeout=int(act.get("timeout", 5000)))
            elif action_type == "press":
                interactor.press(act.get("key", "Enter"))
            elif action_type == "wait_for":
                interactor.wait_for(sel, timeout=int(act.get("timeout", 5000)))
            elif action_type == "scroll" or action_type == "wheel":
                x = int(act.get("x", act.get("delta_x", 0)))
                y = int(act.get("y", act.get("delta_y", 0)))
                interactor.scroll(selector=sel, x=x, y=y)
            elif action_type == "scroll_into_view":
                interactor.scroll_into_view(sel, timeout=int(act.get("timeout", 5000)))
            elif action_type == "evaluate":
                script = act.get("script") or act.get("js") or ""
                eval_res = interactor.evaluate(script)
                if eval_res is not None:
                    res["result"] = eval_res
            elif action_type == "evaluate_many":
                scripts = act.get("scripts") or {}
                batch_res = interactor.evaluate_many(scripts)
                res["results"] = batch_res
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
