import re
from typing import List, Set
from urllib.parse import urlparse
from playwright.sync_api import Page


def normalize_route_pattern(path: str) -> str:
    """
    Normalizes a URL path into a route pattern to group similar pages.
    E.g.:
      /q/1413034        -> /q/:id
      /user/alice        -> /user/:slug
      /tag/python        -> /tag/:slug
    """
    p = path.rstrip("/") or "/"
    # Replace numeric IDs
    p = re.sub(r"/\d+(?=/|$)", "/:id", p)
    # Replace UUIDs
    p = re.sub(r"/[0-9a-fA-F-]{16,}(?=/|$)", "/:uuid", p)
    return p


def discover_sample_subpages(
    page: Page,
    base_url: str,
    max_subpages: int = 3,
) -> List[str]:
    """
    Extracts internal links from the current page and selects up to max_subpages
    distinct route patterns to maximize page diversity (e.g. 1 question, 1 user profile, 1 tag).
    Prioritizes deeper item/entity routes (like /q/:id, /user/:slug) over top-level index tabs.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    base_norm = normalize_route_pattern(parsed_base.path)

    # Extract all links
    links: List[str] = page.evaluate(
        """() => {
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
    )

    candidates: List[tuple[int, str, str]] = []

    for link in links:
        parsed = urlparse(link)
        if parsed.netloc != base_domain or parsed.scheme not in ("http", "https"):
            continue

        clean_path = parsed.path.rstrip("/") or "/"
        clean_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"

        if re.search(r"\.(css|js|png|jpg|jpeg|gif|svg|ico|pdf|zip)$", clean_path, re.IGNORECASE):
            continue
        if re.search(r"/(logout|signout|delete|auth|login)", clean_path, re.IGNORECASE):
            continue

        pattern = normalize_route_pattern(clean_path)
        if pattern == base_norm:
            continue

        # Score priority: entity routes with parameters (:id, :uuid) get highest priority, then depth
        depth = clean_path.count("/")
        has_param = 1 if (":id" in pattern or ":uuid" in pattern) else 0
        score = (has_param * 10) + depth

        candidates.append((score, pattern, clean_url))

    # Sort descending so entity subpages come first
    candidates.sort(key=lambda x: x[0], reverse=True)

    seen_patterns: Set[str] = {base_norm}
    sample_urls: List[str] = []

    for _, pattern, url in candidates:
        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            sample_urls.append(url)
            if len(sample_urls) >= max_subpages:
                break

    return sample_urls
