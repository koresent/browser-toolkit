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
            sys.stderr.write(f"[browser-toolkit] Error reading profiles.ini: {e}\n")

    # Common default folder
    default_dir = zen_config / "default"
    if default_dir.exists() and default_dir.is_dir():
        return default_dir

    return None


class ZenProfileContext:
    """
    Context manager that creates a temporary copy of the Zen profile (using CoW reflink if available)
    removes lock, sync and background session restore files, and cleans up the temporary directory on exit.
    """

    def __init__(
        self,
        profile_path: Optional[str] = None,
        use_profile: bool = True,
        clean_styles: bool = False,
    ):
        self.profile_path = profile_path
        self.use_profile = use_profile
        self.clean_styles = clean_styles
        self.temp_dir: Optional[str] = None
        self.cloned_profile_path: Optional[Path] = None

    def __enter__(self) -> Optional[Path]:
        if not self.use_profile:
            return None

        src_profile = find_zen_profile(self.profile_path)
        if not src_profile:
            sys.stderr.write("[browser-toolkit] Warning: Zen profile not found. Proceeding with clean profile.\n")
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
        self._sanitize_cloned_profile(target_profile, src_profile=src_profile)
        return self.cloned_profile_path

    def _sanitize_cloned_profile(self, profile_dir: Path, src_profile: Optional[Path] = None) -> None:
        """
        Removes lock files, previous session tabs, sync state, and fixes NSS config
        so the browser starts cleanly with authentic logins without clashing with the running Zen instance.
        """
        # Lock files (handle symlinks properly even if dangling)
        for lock_name in ["lock", ".parentlock", "parent.lock"]:
            lock_file = profile_dir / lock_name
            if lock_file.is_symlink() or lock_file.exists():
                try:
                    lock_file.unlink()
                except OSError:
                    pass

        # Session tabs (to prevent opening 50 previous tabs or Zen background sessions during test)
        for sess_name in [
            "sessionstore.jsonlz4",
            "zen-sessions.jsonlz4",
            "zen-live-folders.jsonlz4",
            "sessionCheckpoints.json",
        ]:
            sess_file = profile_dir / sess_name
            if sess_file.is_symlink() or sess_file.exists():
                try:
                    sess_file.unlink()
                except OSError:
                    pass

        for backup_dir_name in ["sessionstore-backups", "zen-sessions-backup", "sessionstore-logs"]:
            backup_dir = profile_dir / backup_dir_name
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

        # Fix NSS PKCS#11 configuration so NSS opens the cloned profile, not the live host profile
        pkcs11_file = profile_dir / "pkcs11.txt"
        if pkcs11_file.exists() and src_profile:
            try:
                content = pkcs11_file.read_text(encoding="utf-8")
                updated = content.replace(str(src_profile), str(profile_dir))
                pkcs11_file.write_text(updated, encoding="utf-8")
            except OSError:
                pass

        # Strip Mozilla Accounts / Firefox Sync credentials so the clone never synchronizes with Mozilla
        signed_in = profile_dir / "signedInUser.json"
        if signed_in.is_symlink() or signed_in.exists():
            try:
                signed_in.unlink()
            except OSError:
                pass

        weave_dir = profile_dir / "weave"
        if weave_dir.exists():
            shutil.rmtree(weave_dir, ignore_errors=True)

        # Strip Stylus storage in the temporary clone so candidate CSS can be tested without conflicts.
        if self.clean_styles:
            storage_default = profile_dir / "storage" / "default"
            if storage_default.exists():
                for db_file in storage_default.glob("moz-extension+++*/idb/*shtsyil.sqlite"):
                    ext_storage = db_file.parent.parent
                    shutil.rmtree(ext_storage, ignore_errors=True)

        # Inject preferences to disable crash popups, default browser checks, sync, webdriver flags, etc.
        user_js = profile_dir / "user.js"
        prefs = (
            "\n"
            "user_pref('browser.sessionstore.resume_from_crash', false);\n"
            "user_pref('browser.shell.checkDefaultBrowser', false);\n"
            "user_pref('toolkit.startup.max_resumed_crashes', -1);\n"
            "user_pref('browser.tabs.warnOnClose', false);\n"
            "user_pref('datareporting.policy.dataSubmissionEnabled', false);\n"
            "user_pref('identity.fxaccounts.enabled', false);\n"
            "user_pref('services.sync.engine.tabs', false);\n"
            "user_pref('services.sync.engine.bookmarks', false);\n"
            "user_pref('services.sync.engine.history', false);\n"
            "user_pref('services.sync.engine.passwords', false);\n"
            "user_pref('services.sync.engine.prefs', false);\n"
            "user_pref('services.sync.engine.addons', false);\n"
            "user_pref('dom.webdriver.enabled', false);\n"
            "user_pref('marionette.enabled', false);\n"
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
                sys.stderr.write(f"[browser-toolkit] Error cleaning up temporary profile {self.temp_dir}: {e}\n")
