from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser


def read_rss(
    feed_url: str,
    limit: int = 20,
    since_days: int = 0,
) -> list[dict[str, Any]]:
    """Fetch and parse an RSS/Atom feed, return articles sorted newest first."""
    feed = feedparser.parse(feed_url)
    cutoff = None
    if since_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400

    articles = []
    for entry in feed.entries:
        published_ts = _published_ts(entry)
        if cutoff and published_ts and published_ts < cutoff:
            continue
        articles.append({
            "title": entry.get("title", "(sin título)"),
            "source": _source(entry, feed),
            "published": _format_date(published_ts),
            "url": entry.get("link", ""),
            "summary": _clean_summary(entry.get("summary", "")),
        })

    return articles[:limit]


def print_articles(articles: list[dict[str, Any]], show_summary: bool = False) -> None:
    if not articles:
        print("No se encontraron artículos.")
        return
    for art in articles:
        date = f"[{art['published']}] " if art["published"] else ""
        source = f" — {art['source']}" if art["source"] else ""
        print(f"{date}{art['title']}{source}")
        if show_summary and art["summary"]:
            print(f"  {art['summary'][:200]}")
        if show_summary:
            print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _published_ts(entry) -> float | None:
    import time
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return time.mktime(t)
    return None


def _format_date(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _source(entry, feed) -> str:
    # Google News embeds source in <source> tag
    src = entry.get("source", {})
    if isinstance(src, dict):
        return src.get("title", "") or ""
    return feed.feed.get("title", "") or ""


def _clean_summary(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
