from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse

try:
    import requests as _requests
    from requests.exceptions import SSLError as _SSLError
except ImportError:
    _requests = None  # type: ignore[assignment]
    _SSLError = Exception  # type: ignore[assignment,misc]

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

# ISO 639-1 codes used as URL path prefixes for multilingual sites
_LANG_CODES = {
    "af", "ar", "bg", "bn", "ca", "cs", "cy", "da", "de", "el",
    "en", "es", "et", "eu", "fi", "fr", "gl", "he", "hr", "hu",
    "hy", "id", "it", "ja", "ka", "ko", "lt", "lv", "mk", "ml",
    "mt", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sl", "sq",
    "sr", "sv", "sw", "th", "tr", "uk", "ur", "vi", "zh",
}

_SITEMAP_TIMEOUT = 10
_SITEMAP_CANDIDATES = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"]


# ---------------------------------------------------------------------------
# Sitemap discovery
# ---------------------------------------------------------------------------

def fetch_sitemap_urls(home_url: str, lang: str = "") -> list[str]:
    """Try standard sitemap paths and return filtered internal URLs."""
    if _requests is None:
        return []
    base = home_url.rstrip("/")
    for path in _SITEMAP_CANDIDATES:
        url = base + path
        resp = _get(url)
        if resp is None:
            continue
        if resp.status_code == 200 and _looks_like_sitemap(resp.text):
            urls = _parse_sitemap_xml(resp.text, home_url, lang=lang)
            if urls:
                return urls
    return []


def _get(url: str, **kwargs) -> "object | None":
    """GET with automatic SSL fallback, returns None on unrecoverable error."""
    if _requests is None:
        return None
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        return _requests.get(url, timeout=_SITEMAP_TIMEOUT, headers=headers, allow_redirects=True, **kwargs)
    except _SSLError:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        try:
            return _requests.get(url, timeout=_SITEMAP_TIMEOUT, headers=headers, verify=False, allow_redirects=True, **kwargs)
        except Exception:
            return None
    except Exception:
        return None


def _parse_sitemap_xml(xml_text: str, home_url: str, _depth: int = 0, lang: str = "") -> list[str]:
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
            if not loc:
                continue
            resp = _get(loc)
            if resp is not None and resp.status_code == 200 and _looks_like_sitemap(resp.text):
                urls.extend(_parse_sitemap_xml(resp.text, home_url, _depth + 1, lang))
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
            if _is_foreign_lang(norm, lang):
                continue
            urls.append(norm)

    return urls


def _is_foreign_lang(url: str, lang: str) -> bool:
    """Return True if the URL's first path segment is a language code other than lang."""
    if not lang:
        return False
    first_seg = urlparse(url).path.strip("/").split("/")[0].lower()
    return first_seg in _LANG_CODES and first_seg != lang.lower()


def _looks_like_sitemap(text: str) -> bool:
    return "<url" in text or "sitemapindex" in text or "urlset" in text


def _loc(elem: ET.Element) -> str:
    for child in elem:
        if child.tag.endswith("}loc") or child.tag == "loc":
            return (child.text or "").strip()
    return ""


# ---------------------------------------------------------------------------
# BFS link discovery from HTML
# ---------------------------------------------------------------------------

def discover_links(html: str, base_url: str, home_url: str, lang: str = "") -> list[str]:
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
        if _is_foreign_lang(norm, lang):
            continue
        found.add(norm)
    return sorted(found)


# ---------------------------------------------------------------------------
# SiteCrawl iterator
# ---------------------------------------------------------------------------

def crawl_urls(home_url: str, max_pages: int, use_sitemap: bool = True, lang: str = "") -> "SiteCrawl":
    return SiteCrawl(home_url, max_pages, use_sitemap=use_sitemap, lang=lang)


class SiteCrawl:
    """BFS iterator seeded with sitemap URLs (when available) + HTML link discovery."""

    def __init__(self, home_url: str, max_pages: int, use_sitemap: bool = True, lang: str = "") -> None:
        self.home_url = home_url
        self.max_pages = max_pages
        self.lang = lang
        self._visited: set[str] = set()
        self._queue: deque[str] = deque([_normalize(home_url) or home_url])
        self.sitemap_urls_found = 0

        if use_sitemap:
            sitemap_urls = fetch_sitemap_urls(home_url, lang=lang)
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
        for link in discover_links(html, page_url, self.home_url, lang=self.lang):
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
