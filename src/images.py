from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .image_filters import is_noise_image
from .models import Entity, PageExtraction
from .text_utils import normalize_key


STOPWORDS = {
    "de",
    "del",
    "la",
    "las",
    "los",
    "el",
    "y",
    "en",
    "san",
    "santa",
    "maria",
    "real",
    "burgos",
    "centro",
    "ciudad",
    "visita",
    "forum",
}

# CMS guest-image paths never contain semantic tokens — only context signal is reliable.
_GUEST_IMAGE_PATH = "/documents/d/guest/"
# Wider context window for scoring: the 80-word limit was rejecting full article sections.
_CONTEXT_MAX_WORDS = 200

GENERIC_IMAGE_TOKENS = {
    "logo",
    "facebook",
    "instagram",
    "twitter",
    "whatsapp",
    "desliza",
    "arrow",
    "boton",
    "saber",
    "mas",
    "app",
    "googleplay",
    "apple",
    "logovidriera",
    "promocional",
}


def enrich_entities_images(entities: list[Entity], page: PageExtraction, max_images: int = 8) -> list[Entity]:
    is_detail_page = len(entities) == 1
    for entity in entities:
        existing = [
            url
            for url in entity.images
            if is_image_relevant_to_entity_url(url, entity)
        ]
        matches = match_images_for_entity(entity, page)
        merged = _dedupe([*existing, *matches])

        # Level 2a: context proximity — image's surrounding text mentions the entity
        if not merged:
            merged = _dedupe(match_images_by_context(entity, page))

        # Level 2b: position proximity — only on single-entity detail pages
        if not merged and is_detail_page:
            merged = _dedupe(_page_images_by_position(page))

        entity.images = merged[:max_images]
    return entities


def match_images_by_context(entity: Entity, page: PageExtraction) -> list[str]:
    """Level-2 fallback: images whose surrounding DOM text mentions the entity."""
    keywords = _entity_name_keywords(entity)
    if not keywords:
        return []
    scored: list[tuple[int, int, str]] = []
    for image in page.images:
        url = image.get("url", "")
        if not url or _is_generic_image(_url_haystack(url)) or is_noise_image(url):
            continue
        alt = image.get("alt", "")
        alt_score = _score_alt_for_entity(alt, entity)
        ctx_score = _score_context(image, keywords)
        score = max(alt_score, ctx_score)
        if score <= 0:
            continue
        index = int(image.get("index", "999999") or "999999")
        scored.append((score, -index, url))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [url for _, _, url in scored]


def _page_images_by_position(page: PageExtraction) -> list[str]:
    """Level-2b fallback: all non-noise page images in DOM order (detail pages only)."""
    sorted_imgs = sorted(page.images, key=lambda i: int(i.get("index", "999999") or "999999"))
    return [
        img["url"]
        for img in sorted_imgs
        if img.get("url") and not _is_generic_image(_url_haystack(img.get("url", ""))) and not is_noise_image(img.get("url", ""))
    ]


def match_images_for_entity(entity: Entity, page: PageExtraction) -> list[str]:
    name_keywords = _entity_name_keywords(entity)
    if not name_keywords:
        return []
    scored: list[tuple[int, int, str]] = []
    for image in page.images:
        url = image.get("url", "")
        url_haystack = _url_haystack(url)
        if _is_generic_image(url_haystack):
            continue
        alt = image.get("alt", "")
        score = _score_image_for_entity(url, alt, entity)
        if score <= 0:
            continue
        index = int(image.get("index", "999999") or "999999")
        scored.append((score, -index, url))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [url for _, _, url in scored]


def is_image_relevant_to_entity_url(url: str, entity: Entity) -> bool:
    return _score_url_for_entity(url, entity) > 0 and not _is_generic_image(_url_haystack(url))


def _score_image_for_entity(url: str, alt: str, entity: Entity) -> int:
    """Score combining URL-slug match and alt-text match. Either alone is sufficient."""
    url_score = _score_url_for_entity(url, entity)
    alt_score = _score_alt_for_entity(alt, entity) if alt else 0
    return max(url_score, alt_score)


def _score_alt_for_entity(alt: str, entity: Entity) -> int:
    if not alt:
        return 0
    alt_key = normalize_key(alt)
    keywords = _entity_name_keywords(entity)
    if not keywords:
        return 0
    compound = normalize_key(entity.name).replace(" ", " ")
    if compound and compound in alt_key:
        return 95
    matched = [kw for kw in keywords if kw in alt_key and "-" not in kw]
    distinctive = [kw for kw in keywords if "-" not in kw]
    if not distinctive:
        return 0
    if len(matched) >= min(2, len(distinctive)):
        return 35 + len(matched)
    if len(distinctive) == 1 and matched:
        return 45
    return 0


def _score_url_for_entity(url: str, entity: Entity) -> int:
    url_key = _url_haystack(url)
    if not url_key:
        return 0
    keywords = _entity_name_keywords(entity)
    if not keywords:
        return 0
    compound = normalize_key(entity.name).replace(" ", "-")
    compact = normalize_key(entity.name).replace(" ", "")
    if compound and compound in url_key.replace(" ", "-"):
        return 100
    if compact and compact in url_key.replace(" ", ""):
        return 100
    matched = [keyword for keyword in keywords if keyword in url_key]
    distinctive_count = len([keyword for keyword in keywords if "-" not in keyword])
    if distinctive_count <= 1 and matched:
        return 50
    if len(matched) >= min(2, distinctive_count):
        return 40 + len(matched)
    return 0


def _entity_name_keywords(entity: Entity) -> set[str]:
    text = normalize_key(entity.name)
    words = set(re.findall(r"[a-z0-9]+", text))
    words = {word for word in words if len(word) >= 4 and word not in STOPWORDS}
    compound = text.replace(" ", "-")
    if compound:
        words.add(compound)
    return words


def _url_haystack(url: str) -> str:
    parsed = urlparse(unquote(url))
    return normalize_key(parsed.path.replace("/", " "))


def _image_context_haystack(image: dict[str, str]) -> str:
    return normalize_key(image.get("context", ""))


def _score_text(text: str, keywords: set[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _score_context(image: dict[str, str], keywords: set[str]) -> int:
    context = _image_context_haystack(image)
    # Very large containers often include menus, footers, or many unrelated entities.
    # Treat them as weak global context instead of local proximity.
    if len(context.split()) > _CONTEXT_MAX_WORDS:
        return 0
    return _score_text(context, keywords)


def _is_generic_image(haystack: str) -> bool:
    words = set(re.findall(r"[a-z0-9]+", haystack))
    return bool(words & GENERIC_IMAGE_TOKENS)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
