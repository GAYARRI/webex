from __future__ import annotations

import re
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

_SKIP_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".css", ".js", ".json", ".xml", ".txt", ".csv",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ogg", ".wav",
}

_SKIP_SEGMENTS = {
    "login", "logout", "admin", "api", "register", "signup",
    "search", "feed", "rss", "sitemap", "tag", "category",
    "wp-admin", "wp-login", "wp-content", "wp-json",
    "cart", "checkout", "account", "password",
}


def discover_links(html: str, base_url: str, home_url: str) -> list[str]:
    """Return internal links found in html, normalized and filtered."""
    home_domain = _domain(home_url)
    found: set[str] = set()
    for match in re.finditer(r'href=["\']([^"\'#][^"\']*)["\']', html):
        href = match.group(1).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full = urljoin(base_url, href)
        norm = _normalize(full)
        if not norm:
            continue
        if _domain(norm) != home_domain:
            continue
        if _should_skip(norm):
            continue
        found.add(norm)
    return sorted(found)


def crawl_urls(home_url: str, max_pages: int) -> "SiteCrawl":
    """Return a SiteCrawl iterator that yields URLs in BFS order."""
    return SiteCrawl(home_url, max_pages)


class SiteCrawl:
    """BFS iterator over internal URLs, fed incrementally as pages are processed."""

    def __init__(self, home_url: str, max_pages: int) -> None:
        self.home_url = home_url
        self.max_pages = max_pages
        self._queue: deque[str] = deque([_normalize(home_url) or home_url])
        self._visited: set[str] = set()

    def __iter__(self):
        return self

    def __next__(self) -> str:
        while self._queue:
            url = self._queue.popleft()
            if url in self._visited:
                continue
            if len(self._visited) >= self.max_pages:
                raise StopIteration
            self._visited.add(url)
            return url
        raise StopIteration

    def feed(self, html: str, page_url: str) -> None:
        """Enqueue newly discovered links from a processed page."""
        for link in discover_links(html, page_url, self.home_url):
            if link not in self._visited:
                self._queue.append(link)

    @property
    def visited_count(self) -> int:
        return len(self._visited)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _normalize(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        # Remove fragment and query string, normalise path
        clean = urlunparse(parsed._replace(fragment="", query=""))
        # Remove trailing slash unless it's just the root
        if clean.endswith("/") and len(urlparse(clean).path) > 1:
            clean = clean.rstrip("/")
        return clean
    except Exception:
        return None


def _should_skip(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    # Skip static assets
    for ext in _SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return True
    # Skip system segments
    segments = set(path_lower.strip("/").split("/"))
    return bool(segments & _SKIP_SEGMENTS)
