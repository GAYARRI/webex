from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

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

_SITEMAP_TIMEOUT = 10
_SITEMAP_CANDIDATES = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"]


# ---------------------------------------------------------------------------
# Sitemap discovery
# ---------------------------------------------------------------------------

def fetch_sitemap_urls(home_url: str) -> list[str]:
    """Try standard sitemap paths and return filtered internal URLs."""
    if _requests is None:
        return []
    base = home_url.rstrip("/")
    for path in _SITEMAP_CANDIDATES:
        try:
            resp = _requests.get(
                base + path,
                timeout=_SITEMAP_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            if resp.status_code == 200 and "<url" in resp.text:
                urls = _parse_sitemap_xml(resp.text, home_url)
                if urls:
                    return urls
        except Exception:
            continue
    return []


def _parse_sitemap_xml(xml_text: str, home_url: str, _depth: int = 0) -> list[str]:
    """Parse sitemap XML (urlset or sitemapindex). Recurses into index sitemaps."""
    if _depth > 3:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    tag = root.tag.lower()
    urls: list[str] = []

    if "sitemapindex" in tag:
        for child in root:
            loc = _loc(child)
            if not loc or not loc.endswith(".xml"):
                continue
            try:
                resp = _requests.get(loc, timeout=_SITEMAP_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    urls.extend(_parse_sitemap_xml(resp.text, home_url, _depth + 1))
            except Exception:
                continue
    else:
        home_domain = _domain(home_url)
        for child in root:
            loc = _loc(child)
            if not loc:
                continue
            norm = _normalize(loc)
            if not norm:
                continue
            if _domain(norm) != home_domain:
                continue
            if _should_skip(norm):
                continue
            urls.append(norm)

    return urls


def _loc(elem: ET.Element) -> str:
    for child in elem:
        if child.tag.endswith("}loc") or child.tag == "loc":
            return (child.text or "").strip()
    return ""


# ---------------------------------------------------------------------------
# BFS link discovery from HTML
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SiteCrawl iterator
# ---------------------------------------------------------------------------

def crawl_urls(home_url: str, max_pages: int, use_sitemap: bool = True) -> "SiteCrawl":
    return SiteCrawl(home_url, max_pages, use_sitemap=use_sitemap)


class SiteCrawl:
    """BFS iterator seeded with sitemap URLs (when available) + HTML link discovery."""

    def __init__(self, home_url: str, max_pages: int, use_sitemap: bool = True) -> None:
        self.home_url = home_url
        self.max_pages = max_pages
        self._visited: set[str] = set()
        self._queue: deque[str] = deque([_normalize(home_url) or home_url])
        self.sitemap_urls_found = 0

        if use_sitemap:
            sitemap_urls = fetch_sitemap_urls(home_url)
            self.sitemap_urls_found = len(sitemap_urls)
            for url in sitemap_urls:
                if url not in self._visited:
                    self._queue.append(url)

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
        clean = urlunparse(parsed._replace(fragment="", query=""))
        if clean.endswith("/") and len(urlparse(clean).path) > 1:
            clean = clean.rstrip("/")
        return clean
    except Exception:
        return None


def _should_skip(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    for ext in _SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return True
    segments = set(path_lower.strip("/").split("/"))
    return bool(segments & _SKIP_SEGMENTS)
