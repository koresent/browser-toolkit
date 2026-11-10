import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse


@dataclass
class StyleSection:
    domains: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    url_prefixes: List[str] = field(default_factory=list)
    regexps: List[str] = field(default_factory=list)
    css_content: str = ""


@dataclass
class UserStyleInfo:
    filepath: Path
    name: str = ""
    version: str = ""
    description: str = ""
    homepage_url: str = ""
    author: str = ""
    namespace: str = ""
    sections: List[StyleSection] = field(default_factory=list)
    raw_css: str = ""

    def get_target_url(self) -> str:
        """Determines the most plausible target URL to open for testing."""
        if self.homepage_url:
            parsed = urlparse(self.homepage_url)
            # If homepage is repository (e.g. github.com/koresent/...), don't use it if section is for another domain
            for section in self.sections:
                if any(d in parsed.netloc for d in section.domains):
                    return self.homepage_url

        for section in self.sections:
            if section.urls:
                return section.urls[0]
            if section.url_prefixes:
                return section.url_prefixes[0]
            if section.domains:
                domain = section.domains[0]
                return f"https://{domain}"

        return "https://example.com"

    def get_all_css(self) -> str:
        """Returns all CSS across all sections combined."""
        return "\n".join(s.css_content for s in self.sections)

    def get_combined_css_for_url(self, target_url: str) -> str:
        """Returns all CSS rules that apply to the given URL."""
        parsed = urlparse(target_url)
        domain = parsed.netloc
        path = parsed.path

        matched_css = []
        for section in self.sections:
            # If section has no domain/url restrictions, it applies everywhere
            if not (section.domains or section.urls or section.url_prefixes or section.regexps):
                matched_css.append(section.css_content)
                continue

            applies = False
            for d in section.domains:
                if domain == d or domain.endswith("." + d):
                    applies = True
                    break

            for u in section.urls:
                if target_url == u:
                    applies = True
                    break

            for p in section.url_prefixes:
                if target_url.startswith(p):
                    applies = True
                    break

            for r in section.regexps:
                try:
                    if re.search(r, target_url):
                        applies = True
                        break
                except re.error:
                    pass

            if applies:
                matched_css.append(section.css_content)

        if not matched_css and self.raw_css:
            return self.raw_css

        return "\n\n".join(matched_css)


@dataclass
class UserScriptInfo:
    filepath: Path
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    namespace: str = ""
    matches: List[str] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)
    run_at: str = "document-end"
    raw_js: str = ""

    def get_target_url(self) -> str:
        """Derives a working target URL from @match or @include patterns."""
        for pattern in self.matches + self.includes:
            cleaned = pattern.replace("*://", "https://")
            # Replace wildcards
            if "/*" in cleaned:
                cleaned = cleaned.split("/*")[0] + "/"
            cleaned = cleaned.replace("*.", "")
            parsed = urlparse(cleaned)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"

        return "https://example.com"


def parse_userstyle(filepath: str | Path) -> UserStyleInfo:
    path = Path(filepath).resolve()
    content = path.read_text(encoding="utf-8", errors="replace")

    info = UserStyleInfo(filepath=path, raw_css=content)

    # Parse metadata block
    meta_match = re.search(r"/\* ==UserStyle==\s*(.*?)\s*==/UserStyle== \*/", content, re.DOTALL)
    if meta_match:
        meta_text = meta_match.group(1)
        for line in meta_text.splitlines():
            line = line.strip()
            if m := re.match(r"^@name\s+(.+)$", line):
                info.name = m.group(1).strip()
            elif m := re.match(r"^@version\s+(.+)$", line):
                info.version = m.group(1).strip()
            elif m := re.match(r"^@description\s+(.+)$", line):
                info.description = m.group(1).strip()
            elif m := re.match(r"^@author\s+(.+)$", line):
                info.author = m.group(1).strip()
            elif m := re.match(r"^@namespace\s+(.+)$", line):
                info.namespace = m.group(1).strip()
            elif m := re.match(r"^@homepageURL\s+(.+)$", line):
                info.homepage_url = m.group(1).strip()
            elif m := re.match(r"^@author\s+(.+)$", line):
                info.author = m.group(1).strip()
            elif m := re.match(r"^@namespace\s+(.+)$", line):
                info.namespace = m.group(1).strip()

    # Parse @-moz-document blocks
    # Handle nested braces inside @-moz-document
    moz_doc_pattern = re.compile(r"@-moz-document\s+([^{]+)\{", re.MULTILINE)
    last_end = 0

    for match in moz_doc_pattern.finditer(content):
        header = match.group(1)
        start_idx = match.end()

        # Find matching closing brace
        depth = 1
        pos = start_idx
        while pos < len(content) and depth > 0:
            if content[pos] == "{":
                depth += 1
            elif content[pos] == "}":
                depth -= 1
            pos += 1

        body = content[start_idx : pos - 1].strip()
        last_end = pos

        section = StyleSection(css_content=body)

        # Parse conditions in header
        for domain in re.findall(r'domain\(["\']([^"\']+)["\']\)', header):
            section.domains.append(domain)
        for url in re.findall(r'url\(["\']([^"\']+)["\']\)', header):
            section.urls.append(url)
        for prefix in re.findall(r'url-prefix\(["\']([^"\']+)["\']\)', header):
            section.url_prefixes.append(prefix)
        for regexp in re.findall(r'regexp\(["\']([^"\']+)["\']\)', header):
            section.regexps.append(regexp)

        info.sections.append(section)

    if not info.sections:
        # No @-moz-document found, strip metadata block and treat remainder as single section
        clean_content = content
        if meta_match:
            clean_content = content[meta_match.end() :].strip()
        info.sections.append(StyleSection(css_content=clean_content))

    return info


def parse_userscript(filepath: str | Path) -> UserScriptInfo:
    path = Path(filepath).resolve()
    content = path.read_text(encoding="utf-8", errors="replace")

    info = UserScriptInfo(filepath=path, raw_js=content)

    meta_match = re.search(r"// ==UserScript==\s*(.*?)\s*// ==/UserScript==", content, re.DOTALL)
    if meta_match:
        meta_text = meta_match.group(1)
        for line in meta_text.splitlines():
            line = line.strip().lstrip("/").strip()
            if m := re.match(r"^@name\s+(.+)$", line):
                info.name = m.group(1).strip()
            elif m := re.match(r"^@version\s+(.+)$", line):
                info.version = m.group(1).strip()
            elif m := re.match(r"^@description\s+(.+)$", line):
                info.description = m.group(1).strip()
            elif m := re.match(r"^@author\s+(.+)$", line):
                info.author = m.group(1).strip()
            elif m := re.match(r"^@namespace\s+(.+)$", line):
                info.namespace = m.group(1).strip()
            elif m := re.match(r"^@match\s+(.+)$", line):
                info.matches.append(m.group(1).strip())
            elif m := re.match(r"^@include\s+(.+)$", line):
                info.includes.append(m.group(1).strip())
            elif m := re.match(r"^@grant\s+(.+)$", line):
                info.grants.append(m.group(1).strip())
            elif m := re.match(r"^@run-at\s+(.+)$", line):
                info.run_at = m.group(1).strip()

    return info
