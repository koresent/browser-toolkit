import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
from playwright.sync_api import Page

from .css_auditor import audit_css_on_page

JS_EXTRACT_DOM_FINGERPRINT = r"""() => {
    const tokens = new Set();
    function walk(el, path, depth) {
        if (depth > 18) return;
        const tag = el.tagName.toLowerCase();
        if (['script', 'style', 'svg', 'path', 'noscript', 'link', 'meta'].includes(tag)) return;
        
        let cls = '';
        if (typeof el.className === 'string' && el.className) {
            cls = el.className.split(/\s+/)
                .filter(c => c && !/[0-9_-]{8,}/.test(c))
                .slice(0, 2)
                .join('.');
        }
        const nodeStr = cls ? (tag + '.' + cls) : tag;
        const curPath = path ? (path + '>' + nodeStr) : nodeStr;
        tokens.add(curPath);
        
        for (const child of el.children) {
            walk(child, curPath, depth + 1);
        }
    }
    walk(document.body, '', 0);
    return Array.from(tokens);
}"""

JS_EXTRACT_INTERNAL_LINKS = r"""() => {
    const anchors = document.querySelectorAll('a[href]');
    const urls = [];
    for (const a of anchors) {
        try {
            const u = new URL(a.href, document.baseURI);
            urls.push(u.href);
        } catch(_) {}
    }
    return urls;
}"""


def jaccard_similarity(s1: Set[str], s2: Set[str]) -> float:
    if not s1 and not s2:
        return 1.0
    union = s1.union(s2)
    if not union:
        return 0.0
    return len(s1.intersection(s2)) / len(union)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/") or "/"
    # Clean standard tracking params
    query = ""
    if parsed.query:
        # Keep non-tracking params
        params = [p for p in parsed.query.split("&") if not p.startswith(("utm_", "ref", "_ga"))]
        if params:
            query = "?" + "&".join(params)
    return f"{parsed.scheme}://{parsed.netloc}{clean_path}{query}"


@dataclass
class PageArchetype:
    url: str
    title: str
    fingerprint: Set[str] = field(default_factory=set)
    matched_selectors: Set[str] = field(default_factory=set)
    similarity_to_previous: float = 0.0
    screenshot_path: Optional[str] = None


@dataclass
class CrawlReport:
    base_url: str
    total_pages_visited: int
    archetypes: List[PageArchetype] = field(default_factory=list)
    cumulative_matched_selectors: Set[str] = field(default_factory=set)
    remaining_dead_selectors: List[str] = field(default_factory=list)
    stopped_reason: str = ""


def crawl_site_archetypes(
    page: Page,
    start_url: str,
    css_content: Optional[str] = None,
    max_archetypes: int = 8,
    max_pages: int = 25,
    similarity_threshold: float = 0.65,
    output_dir: Optional[Path] = None,
) -> CrawlReport:
    """
    Crawls a site to discover structurally unique page templates (archetypes).
    Prunes redundant pages (e.g. repeated forum threads or articles) using DOM structural similarity,
    and hunts for unverified CSS selectors until full coverage or limit is reached.
    """
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    all_css_selectors: Set[str] = set()
    if css_content:
        # Extract initial selector list
        raw_res = page.evaluate(
            """(css) => {
                const sheet = new CSSStyleSheet();
                try { sheet.replaceSync(css); } catch(_) { return []; }
                const sels = [];
                for (const r of sheet.cssRules) {
                    if (r.selectorText) sels.push(r.selectorText);
                }
                return sels;
            }""",
            css_content,
        )
        all_css_selectors = set(raw_res)

    unverified_selectors = set(all_css_selectors)
    cumulative_matched: Set[str] = set()

    visited_urls: Set[str] = set()
    frontier: List[str] = [normalize_url(start_url)]
    archetypes: List[PageArchetype] = []

    stopped_reason = "Frontier exhausted"

    while frontier and len(visited_urls) < max_pages:
        current_url = frontier.pop(0)
        norm_url = normalize_url(current_url)

        if norm_url in visited_urls:
            continue
        visited_urls.add(norm_url)

        try:
            page.goto(norm_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1200)
        except Exception:
            continue

        # Extract structural fingerprint
        raw_tokens: List[str] = page.evaluate(JS_EXTRACT_DOM_FINGERPRINT)
        current_fp = set(raw_tokens)
        page_title = page.title()

        # Compare with existing archetypes
        max_sim = 0.0
        matched_arch = None
        for arch in archetypes:
            sim = jaccard_similarity(current_fp, arch.fingerprint)
            if sim > max_sim:
                max_sim = sim
                matched_arch = arch

        # Test CSS selectors on this page
        current_matched: Set[str] = set()
        if css_content:
            audit_res = audit_css_on_page(page, css_content)
            current_matched = {m.selector for m in audit_res.matched}

        new_selectors = current_matched.difference(cumulative_matched)

        # Decide whether this is a NEW ARCHETYPE
        is_first_page = len(archetypes) == 0
        is_distinct_structure = max_sim < similarity_threshold
        has_new_selectors = len(new_selectors) > 0

        is_archetype = is_first_page or has_new_selectors or is_distinct_structure

        if is_archetype:
            shot_file = None
            if output_dir:
                shot_file = str(output_dir / f"archetype_{len(archetypes) + 1}.png")
                try:
                    page.screenshot(path=shot_file, full_page=False)
                except Exception:
                    pass

            archetype = PageArchetype(
                url=norm_url,
                title=page_title,
                fingerprint=current_fp,
                matched_selectors=current_matched,
                similarity_to_previous=round(max_sim, 3),
                screenshot_path=shot_file,
            )
            archetypes.append(archetype)
            cumulative_matched.update(current_matched)
            unverified_selectors.difference_update(current_matched)

            # Check victory condition: 100% selectors found!
            if all_css_selectors and len(unverified_selectors) == 0:
                stopped_reason = "100% of UserStyle selectors successfully verified!"
                break

            if len(archetypes) >= max_archetypes:
                stopped_reason = f"Reached maximum requested archetypes ({max_archetypes})"
                break

            # Harvest links from this archetype to expand frontier
            links = page.evaluate(JS_EXTRACT_INTERNAL_LINKS)
            for link in links:
                p_link = urlparse(link)
                if p_link.netloc != base_domain or p_link.scheme not in ("http", "https"):
                    continue
                clean_l = normalize_url(link)
                if clean_l in visited_urls or clean_l in frontier:
                    continue
                # Avoid non-HTML static files or actions
                if re.search(r"\.(css|js|png|jpg|gif|svg|ico|pdf|zip)$", p_link.path, re.IGNORECASE):
                    continue
                if re.search(r"/(logout|signout|delete|auth)", p_link.path, re.IGNORECASE):
                    continue

                frontier.append(clean_l)

        else:
            # Structurally redundant page with 0 new selectors.
            # PRUNE: do not add its outgoing links to frontier.
            pass

    if len(visited_urls) >= max_pages and not stopped_reason:
        stopped_reason = f"Reached max page scan limit ({max_pages})"

    remaining_dead = list(unverified_selectors)

    return CrawlReport(
        base_url=start_url,
        total_pages_visited=len(visited_urls),
        archetypes=archetypes,
        cumulative_matched_selectors=cumulative_matched,
        remaining_dead_selectors=remaining_dead,
        stopped_reason=stopped_reason,
    )
