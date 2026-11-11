"""
Extension manager for Stylus and Violentmonkey in Zen Browser.
Directly inspects, exports, diffs, and manages installed styles and scripts
from the user's Zen profile storage databases.
"""

import fcntl
import json
import re
import shutil
import sqlite3
import struct
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import snappy
from dfindexeddb.indexeddb.firefox import definitions, gecko
from dfindexeddb.indexeddb.firefox.record import FileReader

from .profile import find_zen_profile
from .parser import parse_userstyle, parse_userscript

LOCK_FILE = Path(tempfile.gettempdir()) / "browser-toolkit" / "ext_db.lock"


@contextmanager
def ext_db_lock(timeout: float = 30.0):
    """Inter-process file lock protecting extension database writes."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCK_FILE, "a+", encoding="utf-8")
    start = time.time()
    while True:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (BlockingIOError, OSError):
            if time.time() - start > timeout:
                f.close()
                raise TimeoutError("Timed out waiting for extension database lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def ext_db_locked(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator ensuring that method runs under the inter-process extension DB lock."""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with ext_db_lock():
            return func(*args, **kwargs)
    return wrapper


def encode_idb_number(val: float | int) -> bytes:
    """Encodes a numeric ID into Firefox IndexedDB key format."""
    int_val = struct.unpack(">Q", struct.pack(">d", float(val)))[0]
    if int_val & 0x8000000000000000 == 0:
        int_val = int_val | 0x8000000000000000
    else:
        int_val = (-struct.unpack(">q", struct.pack(">Q", int_val))[0]) & 0xFFFFFFFFFFFFFFFF
    number_bytes = struct.pack(">Q", int_val).rstrip(b"\x00")
    return b"\x10" + number_bytes


def encode_idb_string(s: str) -> bytes:
    """Encodes a string into Firefox IndexedDB key format (0x30 prefix + Caesar +1 shift)."""
    return b"0" + bytes((c + 1) for c in s.encode("utf-8"))


def decode_idb_string(b: bytes) -> str:
    """Decodes a Firefox IndexedDB string key."""
    if b.startswith(b"0"):
        return bytes((c - 1) for c in b[1:]).decode("utf-8", errors="replace")
    return str(b)


def decompress_idb_blob(raw_data: bytes) -> bytes:
    """Decompresses a Snappy / Gecko IndexedDB data blob."""
    if raw_data.startswith(definitions.FRAME_HEADER):
        uncompressed = bytearray()
        pos = len(definitions.FRAME_HEADER)
        while pos < len(raw_data):
            is_uncompressed = raw_data[pos]
            block_size = int.from_bytes(raw_data[pos + 1 : pos + 4], byteorder="little")
            if is_uncompressed:
                uncompressed += raw_data[pos + 8 : pos + 8 + block_size - 4]
            else:
                uncompressed += snappy.decompress(raw_data[pos + 8 : pos + 8 + block_size - 4])
            pos += block_size + 4
        return bytes(uncompressed)
    else:
        return snappy.decompress(raw_data)


class GeckoStructuredCloneEncoder:
    """Serializes Python values into Gecko Structured Clone format compressed with Snappy."""

    @classmethod
    def encode(cls, obj: Any) -> bytes:
        buf = bytearray()
        buf += struct.pack("<II", 3, 0xFFF10000)
        cls._write_val(buf, obj)
        return snappy.compress(bytes(buf))

    @classmethod
    def _write_val(cls, buf: bytearray, val: Any) -> None:
        if val is None or isinstance(val, (gecko.types.Null, gecko.types.Undefined)):
            buf += struct.pack("<II", 0, 0xFFFF0000)
        elif isinstance(val, bool):
            buf += struct.pack("<II", 1 if val else 0, 0xFFFF0002)
        elif isinstance(val, int):
            buf += struct.pack("<iI", val, 0xFFFF0003)
        elif isinstance(val, float):
            buf += struct.pack("<d", val)
        elif isinstance(val, str):
            try:
                raw = val.encode("latin-1")
                data = 0x80000000 | len(raw)
            except UnicodeEncodeError:
                raw = val.encode("utf-16-le")
                data = len(raw) // 2
            buf += struct.pack("<II", data, 0xFFFF0004)
            padded = bytearray(raw)
            if len(padded) % 8:
                padded += b"\x00" * (8 - (len(padded) % 8))
            buf += padded
        elif isinstance(val, (list, tuple, gecko.types.JSArray)):
            items = val.values if isinstance(val, gecko.types.JSArray) else val
            buf += struct.pack("<II", len(items), 0xFFFF0007)
            for idx, item in enumerate(items):
                cls._write_val(buf, idx)
                cls._write_val(buf, item)
            buf += struct.pack("<II", 0, 0xFFFF0013)
        elif isinstance(val, dict):
            buf += struct.pack("<II", 0, 0xFFFF0008)
            for k, v in val.items():
                cls._write_val(buf, str(k))
                cls._write_val(buf, v)
            buf += struct.pack("<II", 0, 0xFFFF0013)
        else:
            raise TypeError(f"Unsupported type for structured clone: {type(val)}")


@dataclass
class StylusSection:
    code: str
    domains: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    url_prefixes: List[str] = field(default_factory=list)
    regexps: List[str] = field(default_factory=list)


@dataclass
class StylusStyle:
    id: int
    name: str
    enabled: bool
    sections: List[StylusSection] = field(default_factory=list)
    usercss_data: Dict[str, Any] = field(default_factory=dict)
    original_data: Dict[str, Any] = field(default_factory=dict)

    def to_usercss(self) -> str:
        """Converts style back into standard .user.css format."""
        lines = ["/* ==UserStyle=="]
        lines.append(f"@name         {self.name}")
        if self.usercss_data:
            for k in ("namespace", "version", "description", "author", "license", "homepageURL", "supportURL", "updateURL"):
                val = self.usercss_data.get(k)
                if val:
                    lines.append(f"@{k:<12} {val}")
        lines.append("==/UserStyle== */")
        lines.append("")

        for sec in self.sections:
            conditions = []
            for d in sec.domains:
                conditions.append(f'domain("{d}")')
            for u in sec.urls:
                conditions.append(f'url("{u}")')
            for p in sec.url_prefixes:
                conditions.append(f'url-prefix("{p}")')
            for r in sec.regexps:
                conditions.append(f'regexp("{r}")')

            if conditions:
                cond_str = ", ".join(conditions)
                lines.append(f"@-moz-document {cond_str} {{")
                lines.append(sec.code)
                lines.append("}")
                lines.append("")
            else:
                lines.append(sec.code)
                lines.append("")

        return "\n".join(lines).strip() + "\n"


@dataclass
class ViolentmonkeyScript:
    id: int
    name: str
    version: str
    enabled: bool
    matches: List[str] = field(default_factory=list)
    code: str = ""
    custom: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)


class ExtensionManager:
    """Inspects and manages Stylus and Violentmonkey databases in Zen profile."""

    STYLUS_ADDON_ID = "{7a7a4a92-a2a0-41d1-9fd7-1e92480d612d}"
    VM_ADDON_ID = "{aecec67f-0d10-4fa7-b7c7-609a2db280cf}"

    @staticmethod
    def _connect(db_path: Path | str) -> sqlite3.Connection:
        """Opens a connection to Firefox IndexedDB SQLite database, registering custom Gecko triggers."""
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.create_function("update_refcount", 2, lambda old, new: None)
        return conn

    @staticmethod
    def _invalidate_stylus_cache(db_path: Path) -> None:
        """Removes Stylus Web Cache API data so updated IndexedDB styles recompile instead of serving stale CSS."""
        cache_dir = db_path.parent.parent / "cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)

    def __init__(self, profile_path: Optional[str | Path] = None):
        self.profile_dir = Path(profile_path).resolve() if profile_path else find_zen_profile()
        if not self.profile_dir or not self.profile_dir.exists():
            raise FileNotFoundError(f"Zen profile directory not found: {self.profile_dir}")

        self.webext_uuids = self._load_webext_uuids()

    def _load_webext_uuids(self) -> Dict[str, str]:
        """Reads extensions.webextensions.uuids from prefs.js."""
        prefs_file = self.profile_dir / "prefs.js"
        if not prefs_file.exists():
            return {}

        content = prefs_file.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'user_pref\("extensions\.webextensions\.uuids",\s*"((?:\\.|[^"\\])*)"\);', content)
        if not m:
            return {}

        try:
            inner_str = json.loads('"' + m.group(1) + '"')
            return json.loads(inner_str)
        except Exception:
            return {}

    def get_stylus_db_path(self) -> Optional[Path]:
        uuid = self.webext_uuids.get(self.STYLUS_ADDON_ID)
        if not uuid:
            return None
        storage_idb = self.profile_dir / "storage" / "default" / f"moz-extension+++{uuid}" / "idb"
        if not storage_idb.exists():
            return None
        # Locate *shtsyil.sqlite
        for f in storage_idb.glob("*shtsyil.sqlite"):
            return f
        return None

    def get_violentmonkey_db_path(self) -> Optional[Path]:
        uuid = self.webext_uuids.get(self.VM_ADDON_ID)
        if not uuid:
            return None
        storage_idb = self.profile_dir / "storage" / "default" / f"moz-extension+++{uuid}^userContextId=4294967295" / "idb"
        if not storage_idb.exists():
            return None
        for f in storage_idb.glob("*wleabcEoxlt-eengsairo.sqlite"):
            return f
        return None

    def list_styles(self) -> List[StylusStyle]:
        """Reads all styles from Stylus SQLite database."""
        db_path = self.get_stylus_db_path()
        if not db_path:
            return []

        styles: List[StylusStyle] = []
        reader = FileReader(str(db_path))

        for rec in reader.Records():
            val = rec.value
            if not isinstance(val, dict):
                continue

            style_id = val.get("id", 0)
            name = val.get("name", "Untitled")
            enabled = bool(val.get("enabled", True))
            usercss_data = val.get("usercssData") or {}

            sections: List[StylusSection] = []
            raw_secs = val.get("sections")
            if raw_secs:
                sec_items = getattr(raw_secs, "values", raw_secs) if not isinstance(raw_secs, list) else raw_secs
                for sec in sec_items:
                    if isinstance(sec, dict):
                        code = sec.get("code", "")
                        domains = list(getattr(sec.get("domains"), "values", sec.get("domains") or []))
                        urls = list(getattr(sec.get("urls"), "values", sec.get("urls") or []))
                        prefixes = list(getattr(sec.get("urlPrefixes"), "values", sec.get("urlPrefixes") or []))
                        regexps = list(getattr(sec.get("regexps"), "values", sec.get("regexps") or []))

                        sections.append(
                            StylusSection(
                                code=code,
                                domains=domains,
                                urls=urls,
                                url_prefixes=prefixes,
                                regexps=regexps,
                            )
                        )

            styles.append(
                StylusStyle(
                    id=style_id,
                    name=name,
                    enabled=enabled,
                    sections=sections,
                    usercss_data=usercss_data,
                    original_data=val,
                )
            )

        styles.sort(key=lambda s: s.name.lower())
        return styles

    def list_scripts(self) -> List[ViolentmonkeyScript]:
        """Reads all scripts and their source code from Violentmonkey SQLite database."""
        db_path = self.get_violentmonkey_db_path()
        if not db_path:
            return []

        scripts_map: Dict[int, ViolentmonkeyScript] = {}
        code_map: Dict[int, str] = {}

        for attempt in range(4):
            try:
                reader = FileReader(str(db_path))
                scripts_map.clear()
                code_map.clear()

                for rec in reader.Records():
                    key = rec.key.value if hasattr(rec.key, "value") else str(rec.key)
                    val = rec.value

                    if key.startswith("scr:"):
                        try:
                            s_id = int(key.split(":", 1)[1])
                        except ValueError:
                            continue

                        if isinstance(val, dict):
                            meta = val.get("meta") or {}
                            custom = val.get("custom") or {}
                            name = custom.get("name") or meta.get("name") or f"Script #{s_id}"
                            version = meta.get("version", "1.0.0")
                            enabled = bool(val.get("config", {}).get("enabled", True))
                            matches = list(getattr(meta.get("match"), "values", meta.get("match") or []))

                            scripts_map[s_id] = ViolentmonkeyScript(
                                id=s_id,
                                name=name,
                                version=version,
                                enabled=enabled,
                                matches=matches,
                                custom=custom,
                                meta=meta,
                            )

                    elif key.startswith("code:"):
                        try:
                            c_id = int(key.split(":", 1)[1])
                        except ValueError:
                            continue
                        if isinstance(val, str):
                            code_map[c_id] = val
                break
            except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                if attempt < 3 and "locked" in str(e).lower():
                    time.sleep(0.4)
                    continue
                raise

        for s_id, script in scripts_map.items():
            if s_id in code_map:
                script.code = code_map[s_id]

        results = list(scripts_map.values())
        results.sort(key=lambda s: s.name.lower())
        return results

    def export_styles(self, output_dir: Path | str) -> int:
        """Dumps all Stylus styles as clean .user.css files to disk."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        styles = self.list_styles()
        exported = 0

        for s in styles:
            # Clean safe filename from style name
            safe_name = re.sub(r"[^\w\-\.]+", "-", s.name).strip("-").lower()
            if not safe_name:
                safe_name = f"style-{s.id}"
            file_path = out / f"{safe_name}.user.css"
            file_path.write_text(s.to_usercss(), encoding="utf-8")
            exported += 1

        return exported

    def export_scripts(self, output_dir: Path | str) -> int:
        """Dumps all Violentmonkey scripts as clean .user.js files to disk."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        scripts = self.list_scripts()
        exported = 0

        for sc in scripts:
            safe_name = re.sub(r"[^\w\-\.]+", "-", sc.name).strip("-").lower()
            if not safe_name:
                safe_name = f"script-{sc.id}"
            file_path = out / f"{safe_name}.user.js"
            file_path.write_text(sc.code, encoding="utf-8")
            exported += 1

        return exported

    def build_stylus_backup_json(self, styles_dir: Path | str, output_file: Path | str) -> int:
        """Takes a directory of local .user.css files and builds a standard

        Stylus backup JSON file (importable in 1 click).
        """
        src = Path(styles_dir).resolve()
        out = Path(output_file).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        items = [{"settings": {"updateInterval": 24}}]
        count = 0

        for f in sorted(src.rglob("*.user.css")):
            info = parse_userstyle(f)
            sections_data = []
            for sec in info.sections:
                sections_data.append({
                    "code": sec.css_content,
                    "domains": sec.domains,
                    "urls": sec.urls,
                    "urlPrefixes": sec.url_prefixes,
                    "regexps": sec.regexps,
                })

            item = {
                "name": info.name or f.stem,
                "enabled": True,
                "sections": sections_data,
                "usercssData": {
                    "name": info.name or f.stem,
                    "version": info.version or "1.0.0",
                    "description": info.description or "",
                    "homepageURL": info.homepage_url or "",
                },
            }
            items.append(item)
            count += 1

        out.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        return count

    def build_violentmonkey_backup_zip(self, scripts_dir: Path | str, output_zip: Path | str) -> int:
        """Takes a directory of local .user.js files and packs them into a standard

        Violentmonkey backup ZIP file (importable in 1 click).
        """
        src = Path(scripts_dir).resolve()
        out = Path(output_zip).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(src.rglob("*.user.js")):
                info = parse_userscript(f)
                # Keep directory structure or safe relative path
                arc_name = str(f.relative_to(src)).replace("/", "_")
                zf.writestr(arc_name, info.raw_js)
                count += 1

        return count

    def diff_styles(self, local_dir: Path | str) -> Dict[str, Any]:
        """Compares local .user.css files against active Stylus database."""
        src = Path(local_dir).resolve()
        installed = self.list_styles()
        inst_by_name = {s.name.strip().lower(): s for s in installed}

        local_files = list(src.rglob("*.user.css"))
        matched = []
        only_local = []
        modified = []

        seen_installed = set()

        for f in local_files:
            info = parse_userstyle(f)
            key = (info.name or f.stem).strip().lower()

            if key in inst_by_name:
                inst = inst_by_name[key]
                seen_installed.add(key)
                local_code = info.get_all_css()
                inst_code = "\n".join(sec.code for sec in inst.sections)

                if local_code.strip() != inst_code.strip():
                    modified.append({
                        "name": inst.name,
                        "file": str(f.relative_to(src)),
                        "installed_size": len(inst_code),
                        "local_size": len(local_code),
                    })
                else:
                    matched.append({"name": inst.name, "file": str(f.relative_to(src))})
            else:
                only_local.append({"name": info.name or f.stem, "file": str(f.relative_to(src))})

        only_installed = [
            {"id": s.id, "name": s.name, "enabled": s.enabled}
            for k, s in inst_by_name.items()
            if k not in seen_installed
        ]

        return {
            "total_local": len(local_files),
            "total_installed": len(installed),
            "in_sync": len(matched),
            "modified": modified,
            "only_local": only_local,
            "only_installed": only_installed,
        }

    def diff_scripts(self, local_dir: Path | str) -> Dict[str, Any]:
        """Compares local .user.js files against active Violentmonkey database."""
        src = Path(local_dir).resolve()
        installed = self.list_scripts()
        inst_by_name = {s.name.strip().lower(): s for s in installed}

        local_files = list(src.rglob("*.user.js"))
        matched = []
        only_local = []
        modified = []
        seen_installed = set()

        for f in local_files:
            info = parse_userscript(f)
            key = (info.name or f.stem).strip().lower()

            if key in inst_by_name:
                inst = inst_by_name[key]
                seen_installed.add(key)
                if info.raw_js.strip() != inst.code.strip():
                    modified.append({
                        "name": inst.name,
                        "file": str(f.relative_to(src)),
                        "installed_size": len(inst.code),
                        "local_size": len(info.raw_js),
                    })
                else:
                    matched.append({"name": inst.name, "file": str(f.relative_to(src))})
            else:
                only_local.append({"name": info.name or f.stem, "file": str(f.relative_to(src))})

        only_installed = [
            {"id": s.id, "name": s.name, "version": s.version, "enabled": s.enabled}
            for k, s in inst_by_name.items()
            if k not in seen_installed
        ]

        return {
            "total_local": len(local_files),
            "total_installed": len(installed),
            "in_sync": len(matched),
            "modified": modified,
            "only_local": only_local,
            "only_installed": only_installed,
        }

    def find_style(self, target: str | int) -> Optional[StylusStyle]:
        """Finds an installed style by numeric ID, exact name, or partial name."""
        styles = self.list_styles()
        target_str = str(target).strip()
        if target_str.isdigit():
            target_id = int(target_str)
            for s in styles:
                if s.id == target_id:
                    return s

        t_lower = target_str.lower()
        for s in styles:
            if s.name.strip().lower() == t_lower:
                return s

        for s in styles:
            if t_lower in s.name.lower():
                return s

        return None

    @ext_db_locked
    def set_style_enabled(self, target: str | int, enabled: bool) -> bool:
        """Enables or disables an installed Stylus style directly in SQLite storage."""
        db_path = self.get_stylus_db_path()
        if not db_path:
            raise FileNotFoundError("Stylus database not found")

        style = self.find_style(target)
        if not style:
            return False

        key = encode_idb_number(style.id)
        conn = self._connect(db_path)
        try:
            row = conn.execute("SELECT data FROM object_data WHERE key = ?", (key,)).fetchone()
            if not row:
                return False

            raw_data = row[0]
            decomp = bytearray(decompress_idb_blob(raw_data))
            pos = decomp.find(b"enabled\x00")
            if pos != -1 and decomp[pos + 12 : pos + 16] == b"\x02\x00\xff\xff":
                decomp[pos + 8] = 1 if enabled else 0
                new_data = snappy.compress(bytes(decomp))
            else:
                val = gecko.JSStructuredCloneDecoder.FromBytes(raw_data)
                val["enabled"] = enabled
                val["_rev"] = float(time.time() * 1000)
                new_data = GeckoStructuredCloneEncoder.encode(val)

            conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (new_data, key))
            conn.commit()
            self._invalidate_stylus_cache(db_path)
            return True
        finally:
            conn.close()

    def toggle_style(self, target: str | int) -> bool:
        """Toggles an installed Stylus style on or off."""
        style = self.find_style(target)
        if not style:
            return False
        return self.set_style_enabled(target, not style.enabled)

    @ext_db_locked
    def delete_style(self, target: str | int) -> bool:
        """Deletes an installed style from Stylus SQLite storage."""
        db_path = self.get_stylus_db_path()
        if not db_path:
            raise FileNotFoundError("Stylus database not found")

        style = self.find_style(target)
        if not style:
            return False

        key = encode_idb_number(style.id)
        conn = self._connect(db_path)
        try:
            conn.execute("DELETE FROM object_data WHERE key = ?", (key,))
            conn.commit()
            self._invalidate_stylus_cache(db_path)
            return True
        finally:
            conn.close()

    @ext_db_locked
    def install_or_update_style(self, style_path: Path | str, enabled: bool = True) -> Dict[str, Any]:
        """Installs or updates a .user.css file directly into Stylus SQLite storage."""
        p = Path(style_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"UserStyle file not found: {p}")

        info = parse_userstyle(p)
        db_path = self.get_stylus_db_path()
        if not db_path:
            raise FileNotFoundError("Stylus database not found")

        name = info.name or p.stem
        existing = self.find_style(name)
        now_ms = float(time.time() * 1000)
        source_code = p.read_text(encoding="utf-8", errors="replace")

        conn = self._connect(db_path)
        try:
            if existing:
                style_id = existing.id
                key = encode_idb_number(style_id)
                row = conn.execute("SELECT data FROM object_data WHERE key = ?", (key,)).fetchone()
                if row:
                    try:
                        record_dict = gecko.JSStructuredCloneDecoder.FromBytes(row[0])
                    except Exception:
                        record_dict = dict(existing.original_data)
                else:
                    record_dict = dict(existing.original_data)

                record_dict["name"] = name
                record_dict["enabled"] = enabled
                record_dict["_rev"] = now_ms
                record_dict["sourceCode"] = source_code
                record_dict["usercssData"] = {
                    "name": name,
                    "version": info.version or "1.0.0",
                    "description": info.description or "",
                    "author": info.author or "",
                    "homepageURL": info.homepage_url or "",
                }
                record_dict["sections"] = [
                    {
                        "code": sec.css_content,
                        "domains": sec.domains,
                        "urls": sec.urls,
                        "urlPrefixes": sec.url_prefixes,
                        "regexps": sec.regexps,
                    }
                    for sec in info.sections
                ]

                new_data = GeckoStructuredCloneEncoder.encode(record_dict)
                conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (new_data, key))
                conn.commit()
                self._invalidate_stylus_cache(db_path)
                return {"id": style_id, "name": name, "action": "updated", "enabled": enabled}
            else:
                row = conn.execute("SELECT auto_increment FROM object_store WHERE id = 1").fetchone()
                auto_inc = row[0] if row else 1
                new_id = auto_inc
                conn.execute("UPDATE object_store SET auto_increment = ? WHERE id = 1", (auto_inc + 1,))

                key = encode_idb_number(new_id)
                new_record = {
                    "id": new_id,
                    "_id": str(uuid.uuid4()),
                    "_rev": now_ms,
                    "installDate": now_ms,
                    "name": name,
                    "enabled": enabled,
                    "sourceCode": source_code,
                    "usercssData": {
                        "name": name,
                        "version": info.version or "1.0.0",
                        "description": info.description or "",
                        "author": info.author or "",
                        "homepageURL": info.homepage_url or "",
                    },
                    "sections": [
                        {
                            "code": sec.css_content,
                            "domains": sec.domains,
                            "urls": sec.urls,
                            "urlPrefixes": sec.url_prefixes,
                            "regexps": sec.regexps,
                        }
                        for sec in info.sections
                    ],
                }
                new_data = GeckoStructuredCloneEncoder.encode(new_record)
                conn.execute(
                    "INSERT INTO object_data (object_store_id, key, index_data_values, file_ids, data) VALUES (1, ?, NULL, NULL, ?)",
                    (key, new_data),
                )
                conn.commit()
                self._invalidate_stylus_cache(db_path)
                return {"id": new_id, "name": name, "action": "created", "enabled": enabled}
        finally:
            conn.close()

    def find_script(self, target: str | int) -> Optional[ViolentmonkeyScript]:
        """Finds an installed script by numeric ID, exact name, or partial name."""
        scripts = self.list_scripts()
        target_str = str(target).strip()
        if target_str.isdigit():
            target_id = int(target_str)
            for sc in scripts:
                if sc.id == target_id:
                    return sc

        t_lower = target_str.lower()
        for sc in scripts:
            if sc.name.strip().lower() == t_lower:
                return sc

        for sc in scripts:
            if t_lower in sc.name.lower():
                return sc

        return None

    @ext_db_locked
    def set_script_enabled(self, target: str | int, enabled: bool) -> bool:
        """Enables or disables an installed Violentmonkey script directly in SQLite storage."""
        db_path = self.get_violentmonkey_db_path()
        if not db_path:
            raise FileNotFoundError("Violentmonkey database not found")

        script = self.find_script(target)
        if not script:
            return False

        scr_key = encode_idb_string(f"scr:{script.id}")
        conn = self._connect(db_path)
        try:
            row = conn.execute("SELECT data FROM object_data WHERE key = ?", (scr_key,)).fetchone()
            if not row:
                return False

            raw_data = row[0]
            decomp = bytearray(decompress_idb_blob(raw_data))
            pos = decomp.find(b"enabled\x00")
            if pos != -1 and decomp[pos + 12 : pos + 16] == b"\x03\x00\xff\xff":
                decomp[pos + 8] = 1 if enabled else 0
                new_data = snappy.compress(bytes(decomp))
            else:
                val = gecko.JSStructuredCloneDecoder.FromBytes(raw_data)
                cfg = val.get("config") or {}
                cfg["enabled"] = 1 if enabled else 0
                val["config"] = cfg
                new_data = GeckoStructuredCloneEncoder.encode(val)

            conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (new_data, scr_key))
            conn.commit()
            return True
        finally:
            conn.close()

    def toggle_script(self, target: str | int) -> bool:
        """Toggles an installed Violentmonkey script on or off."""
        script = self.find_script(target)
        if not script:
            return False
        return self.set_script_enabled(target, not script.enabled)

    @ext_db_locked
    def delete_script(self, target: str | int) -> bool:
        """Deletes an installed script from Violentmonkey SQLite storage."""
        db_path = self.get_violentmonkey_db_path()
        if not db_path:
            raise FileNotFoundError("Violentmonkey database not found")

        script = self.find_script(target)
        if not script:
            return False

        keys = [
            encode_idb_string(f"scr:{script.id}"),
            encode_idb_string(f"code:{script.id}"),
            encode_idb_string(f"mod:{script.id}"),
            encode_idb_string(f"val:{script.id}"),
        ]
        conn = self._connect(db_path)
        try:
            conn.execute(
                f"DELETE FROM object_data WHERE key IN ({','.join('?' for _ in keys)})",
                keys,
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @ext_db_locked
    def install_or_update_script(self, script_path: Path | str, enabled: bool = True) -> Dict[str, Any]:
        """Installs or updates a .user.js file directly into Violentmonkey SQLite storage."""
        p = Path(script_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"UserScript file not found: {p}")

        info = parse_userscript(p)
        db_path = self.get_violentmonkey_db_path()
        if not db_path:
            raise FileNotFoundError("Violentmonkey database not found")

        name = info.name or p.stem
        existing = self.find_script(name)
        now_ms = float(time.time() * 1000)
        raw_code = p.read_text(encoding="utf-8", errors="replace")

        conn = self._connect(db_path)
        try:
            if existing:
                script_id = existing.id
                code_key = encode_idb_string(f"code:{script_id}")
                scr_key = encode_idb_string(f"scr:{script_id}")
                mod_key = encode_idb_string(f"mod:{script_id}")

                code_data = GeckoStructuredCloneEncoder.encode(raw_code)
                conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (code_data, code_key))

                row = conn.execute("SELECT data FROM object_data WHERE key = ?", (scr_key,)).fetchone()
                if row:
                    try:
                        scr_dict = gecko.JSStructuredCloneDecoder.FromBytes(row[0])
                    except Exception:
                        scr_dict = {}
                else:
                    scr_dict = {}

                cfg = scr_dict.get("config") or {}
                cfg["enabled"] = 1 if enabled else 0
                scr_dict["config"] = cfg

                meta = scr_dict.get("meta") or {}
                meta["name"] = name
                meta["version"] = info.version or meta.get("version", "1.0.0")
                if info.description:
                    meta["description"] = info.description
                if info.matches:
                    meta["match"] = info.matches
                if info.includes:
                    meta["include"] = info.includes
                if info.grants:
                    meta["grant"] = info.grants
                meta["runAt"] = info.run_at or meta.get("runAt", "document-end")
                scr_dict["meta"] = meta

                props = scr_dict.get("props") or {}
                props["lastModified"] = now_ms
                props["lastUpdated"] = now_ms
                scr_dict["props"] = props

                scr_data = GeckoStructuredCloneEncoder.encode(scr_dict)
                conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (scr_data, scr_key))

                mod_data = GeckoStructuredCloneEncoder.encode(now_ms)
                conn.execute("UPDATE object_data SET data = ? WHERE key = ?", (mod_data, mod_key))

                conn.commit()
                return {"id": script_id, "name": name, "action": "updated", "enabled": enabled}
            else:
                rows = conn.execute("SELECT key FROM object_data").fetchall()
                existing_ids = []
                for r in rows:
                    k_str = decode_idb_string(r[0])
                    if k_str.startswith("scr:"):
                        try:
                            existing_ids.append(int(k_str.split(":", 1)[1]))
                        except ValueError:
                            pass
                new_id = (max(existing_ids) + 1) if existing_ids else 1

                scr_key = encode_idb_string(f"scr:{new_id}")
                code_key = encode_idb_string(f"code:{new_id}")
                mod_key = encode_idb_string(f"mod:{new_id}")

                scr_dict = {
                    "custom": {
                        "origInclude": True,
                        "origExclude": True,
                        "origMatch": True,
                        "origExcludeMatch": True,
                        "origTag": True,
                        "pathMap": {},
                    },
                    "config": {
                        "enabled": 1 if enabled else 0,
                        "shouldUpdate": 1,
                        "removed": 0,
                    },
                    "meta": {
                        "name": name,
                        "namespace": info.namespace or "",
                        "version": info.version or "1.0.0",
                        "description": info.description or "",
                        "author": info.author or "",
                        "match": info.matches,
                        "include": info.includes,
                        "grant": info.grants,
                        "runAt": info.run_at or "document-end",
                    },
                    "props": {
                        "id": new_id,
                        "lastModified": now_ms,
                        "uuid": str(uuid.uuid4()),
                        "position": new_id,
                        "uri": f"{name}-0a{info.namespace}-0a",
                        "lastUpdated": now_ms,
                    },
                }

                scr_data = GeckoStructuredCloneEncoder.encode(scr_dict)
                code_data = GeckoStructuredCloneEncoder.encode(raw_code)
                mod_data = GeckoStructuredCloneEncoder.encode(now_ms)

                conn.execute(
                    "INSERT INTO object_data (object_store_id, key, index_data_values, file_ids, data) VALUES (1, ?, NULL, NULL, ?)",
                    (scr_key, scr_data),
                )
                conn.execute(
                    "INSERT INTO object_data (object_store_id, key, index_data_values, file_ids, data) VALUES (1, ?, NULL, NULL, ?)",
                    (code_key, code_data),
                )
                conn.execute(
                    "INSERT INTO object_data (object_store_id, key, index_data_values, file_ids, data) VALUES (1, ?, NULL, NULL, ?)",
                    (mod_key, mod_data),
                )
                conn.commit()
                return {"id": new_id, "name": name, "action": "created", "enabled": enabled}
        finally:
            conn.close()
