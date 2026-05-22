from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_TIMEOUT = 15
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

_RSS_PAGES = ["/rss", "/feeds", "/rss/", "/feeds/", "/syndication", "/feed", "/info/rss", "/info/rss/"]
_FEED_TYPES = {"application/rss+xml", "application/atom+xml", "text/xml"}
_NOISE_TITLES = {"ir al contenido", "copiar enlace", "copiar", "copy link", "skip to content", ""}


def discover_rss(site_url: str, topic: str = "") -> list[dict]:
    """Return RSS feeds from a site filtered by topic keyword."""
    base = _base(site_url)
    feeds: dict[str, dict] = {}

    # 1. Auto-discovery via <link rel="alternate"> in the home page
    _collect_from_page(base, base, feeds)

    # 2. Common RSS index pages (/rss, /feeds, ...)
    for path in _RSS_PAGES:
        url = base + path
        try:
            resp = requests.get(url, timeout=_TIMEOUT, headers=_HEADERS, allow_redirects=True)
            if resp.status_code == 200:
                _collect_from_page(resp.url, base, feeds)
                _collect_hrefs_from_page(resp.text, resp.url, base, feeds)
                _collect_raw_feed_urls(resp.text, base, feeds)
        except Exception:
            pass

    results = list(feeds.values())

    if topic:
        kw = topic.lower()
        results = [
            f for f in results
            if kw in (f.get("title") or "").lower() or kw in f["url"].lower()
        ]

    return results


def _base(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _root_domain(netloc: str) -> str:
    """Return last two labels of hostname (e.g. feeds.elpais.com → elpais.com)."""
    parts = netloc.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else netloc


def _collect_from_page(page_url: str, base: str, feeds: dict) -> None:
    try:
        resp = requests.get(page_url, timeout=_TIMEOUT, headers=_HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link", rel=lambda r: r and "alternate" in r):
            mime = (link.get("type") or "").strip().lower().split(";")[0]
            if mime not in _FEED_TYPES:
                continue
            href = link.get("href", "").strip()
            if not href:
                continue
            full = urljoin(base, href)
            if full not in feeds:
                feeds[full] = {"url": full, "title": (link.get("title") or "").strip()}
    except Exception:
        pass


def _collect_raw_feed_urls(html: str, base: str, feeds: dict) -> None:
    """Extract feed URLs from raw HTML using regex — catches JS-embedded and escaped URLs."""
    root = _root_domain(urlparse(base).netloc)
    for match in re.finditer(r'https?://[^\s"\'<>]+', html):
        url = match.group(0).rstrip(".,;)")
        parsed = urlparse(url)
        if _root_domain(parsed.netloc) != root:
            continue
        path = parsed.path.lower()
        qs = parsed.query.lower()
        if not any(seg in path for seg in ("/rss", "/feed", ".rss", ".xml", "atom")):
            if "outputtype=xml" not in qs and "format=rss" not in qs:
                continue
        clean = parsed._replace(fragment="").geturl()
        if clean not in feeds:
            feeds[clean] = {"url": clean, "title": ""}


def _collect_hrefs_from_page(html: str, page_url: str, base: str, feeds: dict) -> None:
    """Collect <a href> links that look like RSS feeds from a feeds-index page."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        parsed = urlparse(urljoin(page_url, href))
        # Skip anchors pointing to the same page
        if parsed.fragment and not parsed.path.strip("/"):
            continue
        full = parsed._replace(fragment="").geturl()
        path = parsed.path.lower()
        if not any(seg in path for seg in ("/rss", "/feed", ".rss", ".xml", "atom")):
            continue
        if _root_domain(parsed.netloc) != _root_domain(urlparse(base).netloc):
            continue
        title = a.get_text(strip=True) or ""
        if title.lower() in _NOISE_TITLES:
            continue
        if full not in feeds:
            feeds[full] = {"url": full, "title": title}
