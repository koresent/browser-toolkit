"""
Extension manager for Stylus and Violentmonkey in Zen Browser.
Directly inspects, exports, diffs, and manages installed styles and scripts
from the user's Zen profile storage databases.
"""

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dfindexeddb.indexeddb.firefox.record import FileReader

from .profile import find_zen_profile
from .parser import parse_userstyle, parse_userscript


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

        reader = FileReader(str(db_path))
        scripts_map: Dict[int, ViolentmonkeyScript] = {}
        code_map: Dict[int, str] = {}

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
