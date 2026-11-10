import configparser
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


def find_zen_profile(custom_path: Optional[str] = None) -> Optional[Path]:
    """
    Locates the default Zen Browser profile directory.
    Checks custom path, ~/.config/zen/profiles.ini, and fallbacks.
    """
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.exists() and p.is_dir():
            return p
        raise FileNotFoundError(f"Specified profile directory does not exist: {custom_path}")

    zen_config = Path("~/.config/zen").expanduser().resolve()
    if not zen_config.exists():
        # Fallback to standard Firefox config if Zen is not in default path
        ff_config = Path("~/.mozilla/firefox").expanduser().resolve()
        if ff_config.exists():
            zen_config = ff_config
        else:
            return None

    profiles_ini = zen_config / "profiles.ini"
    if profiles_ini.exists():
        config = configparser.ConfigParser()
        try:
            config.read(profiles_ini)
            # Check for Install sections first (modern Firefox/Zen multi-install mapping)
            for section in config.sections():
                if section.startswith("Install") and "Default" in config[section]:
                    rel_or_abs = config[section]["Default"]
                    target = zen_config / rel_or_abs
                    if target.exists() and target.is_dir():
                        return target

            # Check standard Profile sections
            for section in config.sections():
                if section.startswith("Profile"):
                    is_default = config[section].get("Default", "0") == "1"
                    if is_default:
                        path_str = config[section].get("Path", "")
                        is_rel = config[section].get("IsRelative", "1") == "1"
                        target = (zen_config / path_str) if is_rel else Path(path_str)
                        if target.exists() and target.is_dir():
                            return target
        except Exception as e:
            sys.stderr.write(f"[browser-auditor] Error reading profiles.ini: {e}\n")

    # Common default folder
    default_dir = zen_config / "default"
    if default_dir.exists() and default_dir.is_dir():
        return default_dir

    return None


class ZenProfileContext:
    """
    Context manager that creates a temporary copy of the Zen profile (using CoW reflink if available)
    removes lock and session files, and cleans up the temporary directory on exit.
    """

    def __init__(self, profile_path: Optional[str] = None, use_profile: bool = True):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.temp_dir: Optional[str] = None
        self.cloned_profile_path: Optional[Path] = None

    def __enter__(self) -> Optional[Path]:
        if not self.use_profile:
            return None

        src_profile = find_zen_profile(self.profile_path)
        if not src_profile:
            sys.stderr.write("[browser-auditor] Warning: Zen profile not found. Proceeding with clean profile.\n")
            return None

        self.temp_dir = tempfile.mkdtemp(prefix="zen_audit_profile_")
        target_profile = Path(self.temp_dir) / "profile"

        # Clone using CoW reflink where supported (instantaneous on Btrfs/XFS)
        try:
            subprocess.run(
                ["cp", "-a", "--reflink=auto", str(src_profile), str(target_profile)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            # Fallback to python shutil copytree if cp command fails
            shutil.copytree(src_profile, target_profile, symlinks=True, ignore_dangling_symlinks=True)

        self.cloned_profile_path = target_profile
        self._sanitize_cloned_profile(target_profile)
        return self.cloned_profile_path

    def _sanitize_cloned_profile(self, profile_dir: Path) -> None:
        """
        Removes lock files and previous session tabs so the browser starts cleanly
        and does not clash with the running Zen instance.
        """
        # Lock files
        for lock_name in ["lock", ".parentlock", "parent.lock"]:
            lock_file = profile_dir / lock_name
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        # Session tabs (to prevent opening 50 previous tabs during test)
        sessionstore = profile_dir / "sessionstore.jsonlz4"
        if sessionstore.exists():
            try:
                sessionstore.unlink()
            except OSError:
                pass

        for backup_dir_name in ["sessionstore-backups", "zen-sessions-backup"]:
            backup_dir = profile_dir / backup_dir_name
            if backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                except OSError:
                    pass

        # Inject preferences to disable crash popups, default browser checks, etc.
        user_js = profile_dir / "user.js"
        prefs = (
            "\n"
            "user_pref('browser.sessionstore.resume_from_crash', false);\n"
            "user_pref('browser.shell.checkDefaultBrowser', false);\n"
            "user_pref('toolkit.startup.max_resumed_crashes', -1);\n"
            "user_pref('browser.tabs.warnOnClose', false);\n"
            "user_pref('datareporting.policy.dataSubmissionEnabled', false);\n"
        )
        try:
            with open(user_js, "a", encoding="utf-8") as f:
                f.write(prefs)
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                sys.stderr.write(f"[browser-auditor] Error cleaning up temporary profile {self.temp_dir}: {e}\n")
