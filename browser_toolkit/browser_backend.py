import subprocess
import sys
from pathlib import Path
from typing import Any


def ensure_playwright_browser(playwright_obj: Any, browser_name: str = "firefox") -> None:
    """Ensure the Playwright browser executable exists, attempting auto-install if missing."""
    browser_type = getattr(playwright_obj, browser_name, None)
    if not browser_type:
        return

    exec_path = None
    try:
        exec_path = Path(browser_type.executable_path)
    except Exception:
        pass

    if exec_path and not exec_path.exists():
        sys.stderr.write(
            f"Playwright {browser_name} executable not found at {exec_path}.\n"
            f"Attempting automatic installation via 'playwright install {browser_name}'...\n"
        )
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", browser_name], check=True)
            sys.stderr.write(f"Playwright {browser_name} successfully installed.\n")
        except Exception as exc:
            msg = (
                f"\nError: Playwright {browser_name} is missing and automatic installation failed: {exc}\n"
                f"Please run manually:\n"
                f"    {sys.executable} -m playwright install {browser_name}\n\n"
            )
            sys.stderr.write(msg)
            raise RuntimeError(msg) from exc


def safe_launch_persistent_context(
    playwright_obj: Any,
    user_data_dir: str,
    browser_name: str = "firefox",
    **launch_kwargs: Any,
):
    """Launch persistent context with automatic missing-browser recovery."""
    ensure_playwright_browser(playwright_obj, browser_name)
    browser_type = getattr(playwright_obj, browser_name)
    try:
        return browser_type.launch_persistent_context(user_data_dir=user_data_dir, **launch_kwargs)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            sys.stderr.write(f"Encountered missing browser error during launch: {exc}\nRetrying installation...\n")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", browser_name], check=True)
                return browser_type.launch_persistent_context(user_data_dir=user_data_dir, **launch_kwargs)
            except Exception as install_exc:
                msg = (
                    f"\nError: Playwright {browser_name} executable missing and install failed: {install_exc}\n"
                    f"Please run manually:\n"
                    f"    {sys.executable} -m playwright install {browser_name}\n\n"
                )
                sys.stderr.write(msg)
                raise RuntimeError(msg) from install_exc
        raise


def safe_launch_browser(
    playwright_obj: Any,
    browser_name: str = "firefox",
    **launch_kwargs: Any,
):
    """Launch browser instance with automatic missing-browser recovery."""
    ensure_playwright_browser(playwright_obj, browser_name)
    browser_type = getattr(playwright_obj, browser_name)
    try:
        return browser_type.launch(**launch_kwargs)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            sys.stderr.write(f"Encountered missing browser error during launch: {exc}\nRetrying installation...\n")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", browser_name], check=True)
                return browser_type.launch(**launch_kwargs)
            except Exception as install_exc:
                msg = (
                    f"\nError: Playwright {browser_name} executable missing and install failed: {install_exc}\n"
                    f"Please run manually:\n"
                    f"    {sys.executable} -m playwright install {browser_name}\n\n"
                )
                sys.stderr.write(msg)
                raise RuntimeError(msg) from install_exc
        raise
