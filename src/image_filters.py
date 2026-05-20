from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .text_utils import normalize_key


BLOCKED_IMAGE_TOKENS = {
    "app",
    "apple",
    "arrow",
    "blog",
    "boton",
    "button",
    "calendar",
    "chevron",
    "clock",
    "desliza",
    "facebook",
    "googleplay",
    "icon",
    "instagram",
    "linkedin",
    "logo",
    "logotipo",
    "map",
    "pin",
    "menu",
    "nav",
    "promo",
    "promocional",
    "rrss",
    "social",
    "svg",
    "twitter",
    "whatsapp",
    "x",
    "youtube",
}

BLOCKED_IMAGE_SUBSTRINGS = {
    "logo",
    "logovidriera",
    "desliza",
    "twitter",
    "facebook",
    "instagram",
    "whatsapp",
    "ruta-ia",
    "rutaia",
    "infoicons",
    "info icons",
    "map pin",
}

BLOCKED_EXTENSIONS = {
    ".svg",
    ".ico",
}

IMAGE_EXTENSIONS = {
    ".apng",
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
}


def is_noise_image(url: str, alt: str = "", metadata: str = "") -> bool:
    parsed = urlparse(unquote(url))
    path = parsed.path.lower()
    if any(path.endswith(extension) for extension in BLOCKED_EXTENSIONS):
        return True

    filename = path.rsplit("/", 1)[-1]

    # Filenames that start with "-" are typically derived/internal site assets
    if filename.startswith("-"):
        return True

    text = normalize_key(f"{path} {alt} {metadata}")
    words = set(re.findall(r"[a-z0-9]+", text))

    if words & BLOCKED_IMAGE_TOKENS:
        return True
    compact = text.replace(" ", "")
    if any(token in compact for token in BLOCKED_IMAGE_SUBSTRINGS):
        return True

    # Common compact social icon filenames: x.png, X_1.png, Twitter+X+1.png, etc.
    filename_key = normalize_key(filename)
    if filename_key in {"x png", "x jpg", "twitter x 1 png"}:
        return True

    return False


_TRUSTED_IMAGE_DOMAINS = {
    "commons.wikimedia.org",
    "upload.wikimedia.org",
}


def is_trusted_image_source(url: str) -> bool:
    """Images from curated encyclopedic sources bypass URL-name relevance checks."""
    try:
        host = urlparse(url).netloc.lower()
        return host in _TRUSTED_IMAGE_DOMAINS
    except Exception:
        return False


def is_image_url(url: str) -> bool:
    parsed = urlparse(unquote(url or ""))
    path = parsed.path.lower()
    query = parsed.query.lower()
    if any(path.endswith(extension) for extension in IMAGE_EXTENSIONS):
        return True
    if "imagepreview" in query or "image_preview" in query:
        return True
    if "/documents/d/guest/" in path:
        return True
    return False
