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
    "pulsera",
    "turistica",
    "promocional",
}


def enrich_entities_images(entities: list[Entity], page: PageExtraction, max_images: int = 50) -> list[Entity]:
    for entity in entities:
        existing = [url for url in entity.images if url and not _is_generic_image(_url_haystack(url))]
        matches = match_images_for_entity(entity, page)
        merged = _dedupe([*existing, *matches])
        entity.images = merged[:max_images]
    return entities


def match_images_for_entity(entity: Entity, page: PageExtraction) -> list[str]:
    keywords = _entity_keywords(entity)
    if not keywords:
        return []
    scored: list[tuple[int, int, str]] = []
    for image in page.images:
        url = image.get("url", "")
        haystack = _image_haystack(image)
        if _is_generic_image(haystack):
            continue
        context_score = _score_context(image, keywords)
        metadata_score = _score_text(haystack, keywords)
        if not _has_strong_enough_signal(context_score, metadata_score, url):
            continue
        score = (context_score * 1000) + metadata_score
        if score:
            index = int(image.get("index", "999999") or "999999")
            scored.append((score, -index, url))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [url for _, _, url in scored]


def _entity_keywords(entity: Entity) -> set[str]:
    # Include description fields so that rich semantic terms (e.g. "jacobeo", "peregrino",
    # "ermita") can match images whose URL slug is opaque but whose context mentions them.
    description_sample = " ".join([
        entity.shortDescription[:200],
        entity.longDescription[:200],
    ])
    text = normalize_key(" ".join([entity.name, *entity.types, description_sample]))
    words = set(re.findall(r"[a-z0-9]+", text))
    words = {word for word in words if len(word) >= 4 and word not in STOPWORDS}
    compound = normalize_key(entity.name).replace(" ", "-")
    if compound:
        words.add(compound)
    return words


def _image_haystack(image: dict[str, str]) -> str:
    url = unquote(image.get("url", ""))
    parsed = urlparse(url)
    path = normalize_key(parsed.path.replace("/", " "))
    alt = normalize_key(image.get("alt", ""))
    return f"{path} {alt}"


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


def _has_strong_enough_signal(context_score: int, metadata_score: int, url: str = "") -> bool:
    # CMS guest images have opaque slugs — context_score >= 1 is sufficient when
    # the URL itself carries no semantic signal.
    if _GUEST_IMAGE_PATH in url:
        return metadata_score > 0 or context_score >= 1
    return metadata_score > 0 or context_score >= 2


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
