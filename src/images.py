from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

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
    for entity in entities:
        existing = [
            url
            for url in entity.images
            if is_image_relevant_to_entity_url(url, entity)
        ]
        matches = match_images_for_entity(entity, page)
        merged = _dedupe([*existing, *matches])
        entity.images = merged[:max_images]
    return entities


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
        metadata_score = _score_url_for_entity(url, entity)
        # Contract: an image can be assigned only when the image URL itself has
        # an explicit or indubitable textual match with the entity name.
        if metadata_score <= 0:
            continue
        index = int(image.get("index", "999999") or "999999")
        scored.append((metadata_score, -index, url))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [url for _, _, url in scored]


def is_image_relevant_to_entity_url(url: str, entity: Entity) -> bool:
    return _score_url_for_entity(url, entity) > 0 and not _is_generic_image(_url_haystack(url))


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
