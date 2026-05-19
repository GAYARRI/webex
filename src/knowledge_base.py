from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .entity_merger import entity_key
from .models import Entity
from .text_utils import is_boilerplate_text

_MAX_KB_IMAGES = 10

# Entities whose name is this long without a geographic/structural anchor are
# almost certainly blog article titles or sentence fragments, not tourist places.
_MAX_NAME_WORDS_WITHOUT_ANCHOR = 7

# URL path segments that indicate a listing/aggregation page rather than a
# dedicated place description. Entities from these pages are discarded unless
# they have a geographic anchor.
_LISTING_PAGE_SEGMENTS = {"blog", "noticias", "actualidad", "novedades", "agenda"}


def filter_low_quality_entities(entities: list[Entity]) -> list[Entity]:
    """Discard entities that lack sufficient context to be useful KB entries."""
    result = []
    for entity in entities:
        has_anchor = (
            entity.coordinates.lat is not None
            or bool(entity.wikidataId)
            or bool(entity.url and entity.url != entity.sourceUrl)
            or (entity.score is not None and entity.score >= 0.9 and bool(entity.types))
        )
        # Entities from listing/blog pages without a geographic anchor are
        # article titles or snippets, not tourist places.
        if not has_anchor and _is_listing_page(entity.sourceUrl):
            continue
        # Heuristic-only entities (score < 0.5) with no type and no geographic
        # anchor are navigation items or section headings, not real entities.
        if (
            not entity.types
            and entity.coordinates.lat is None
            and (entity.score is None or entity.score < 0.5)
        ):
            continue
        name_words = entity.name.split()
        if len(name_words) > _MAX_NAME_WORDS_WITHOUT_ANCHOR and not has_anchor:
            continue
        result.append(entity)
    return result


def _is_listing_page(url: str) -> bool:
    if not url:
        return False
    path_segments = set(urlparse(url).path.strip("/").split("/"))
    return bool(path_segments & _LISTING_PAGE_SEGMENTS)


def tag_sources_with_page_url(entities: list[Entity], page_url: str) -> None:
    """Stamp page_url on every source that doesn't already have one."""
    for entity in entities:
        for source in entity.sources:
            if not source.page_url:
                source.page_url = page_url
            if "page_url" not in source.metadata:
                source.metadata["page_url"] = page_url


def load_kb(path: str) -> list[Entity]:
    kb_path = Path(path)
    if not kb_path.exists():
        return []
    try:
        data = json.loads(kb_path.read_text(encoding="utf-8"))
        return [
            Entity.from_dict(item)
            for item in data.get("entities", [])
            if isinstance(item, dict)
        ]
    except Exception:
        return []


def load_crawled_urls(path: str) -> set[str]:
    """Return the set of URLs already processed in a previous crawl run."""
    kb_path = Path(path)
    if not kb_path.exists():
        return set()
    try:
        data = json.loads(kb_path.read_text(encoding="utf-8"))
        return set(data.get("crawled_urls", []))
    except Exception:
        return set()


def save_kb(path: str, entities: list[Entity], crawled_urls: set[str] | None = None) -> None:
    kb_path = Path(path)
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"entities": [e.to_dict() for e in entities]}
    if crawled_urls is not None:
        data["crawled_urls"] = sorted(crawled_urls)
    kb_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def merge_into_kb(
    kb_entities: list[Entity],
    new_entities: list[Entity],
) -> tuple[list[Entity], dict]:
    kb: dict[str, Entity] = {entity_key(e): e for e in kb_entities}
    added: list[str] = []
    enriched: list[str] = []

    for entity in new_entities:
        key = entity_key(entity)
        if key in kb:
            _enrich(kb[key], entity)
            enriched.append(entity.name)
        else:
            kb[key] = entity
            added.append(entity.name)

    report = {
        "kb_total": len(kb),
        "added": len(added),
        "added_names": added,
        "enriched": len(enriched),
        "enriched_names": enriched,
    }
    return list(kb.values()), report


def _enrich(base: Entity, incoming: Entity) -> None:
    # Descriptions: accumulate non-redundant content; clones are discarded
    base.shortDescription = _merge_text(base.shortDescription, incoming.shortDescription)
    base.longDescription = _merge_text(base.longDescription, incoming.longDescription)
    base.sourceText = _merge_text(base.sourceText, incoming.sourceText)
    base.description = _merge_text(base.description, incoming.description)

    # Images: accumulate without duplicates, capped to avoid unrelated image drift
    seen = set(base.images)
    for img in incoming.images:
        if img and img not in seen and len(base.images) < _MAX_KB_IMAGES:
            base.images.append(img)
            seen.add(img)

    # Types: accumulate all valid types from both entities. The final
    # classify_entities() pass will resolve conflicts using all accumulated
    # evidence — the classification with the strongest combined evidence wins.
    from .ai_client import TOURIST_TYPES
    allowed = set(TOURIST_TYPES)
    seen = set(base.types)
    for t in incoming.types:
        if t in allowed and t not in seen:
            base.types.append(t)
            seen.add(t)
    # Drop any invalid types that slipped in
    base.types = [t for t in base.types if t in allowed]

    # Coordinates: keep the one with higher confidence
    incoming_conf = incoming.coordinates.confidence or 0.0
    base_conf = base.coordinates.confidence or 0.0
    if incoming.coordinates.lat is not None and (
        base.coordinates.lat is None or incoming_conf > base_conf
    ):
        base.coordinates = incoming.coordinates

    # Contact / location: fill gaps
    if not base.address and incoming.address:
        base.address = incoming.address
    if not base.phone and incoming.phone:
        base.phone = incoming.phone
    if not base.email and incoming.email:
        base.email = incoming.email
    if not base.wikidataId and incoming.wikidataId:
        base.wikidataId = incoming.wikidataId

    # Sources: accumulate without exact duplicates; page_url traceability is always kept
    seen_sources = {(s.url, s.block_id, s.source_type) for s in base.sources}
    for source in incoming.sources:
        if (source.url, source.block_id, source.source_type) not in seen_sources:
            base.sources.append(source)
            seen_sources.add((source.url, source.block_id, source.source_type))

    # Score: keep highest
    if incoming.score is not None and (
        base.score is None or incoming.score > base.score
    ):
        base.score = incoming.score


def _merge_text(current: str, incoming: str) -> str:
    """Accumulate two text fields, discarding clones, subsets, and boilerplate."""
    current = (current or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming if not is_boilerplate_text(incoming) else current
    if incoming in current:   # incoming is a clone or subset
        return current
    if current in incoming:   # current is a subset of incoming
        return incoming
    if is_boilerplate_text(incoming):
        return current
    return f"{current} {incoming}"
