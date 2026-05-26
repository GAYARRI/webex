from __future__ import annotations

import argparse
from typing import Any
from urllib.parse import unquote, urlparse as _up

from .ai_client import configured_model
from .entity_extractor import classify_entities, extract_entities
from .entity_merger import attach_block_evidence, merge_entities
from .geo import (
    enrich_entities_coordinates,
    enrich_entities_external_context,
    enrich_entities_geosearch_images,
    enrich_entities_wikidata_images,
)
from .image_ai import analyze_images_with_vision
from .image_filters import is_image_url, is_noise_image, is_trusted_image_source
from .images import enrich_entities_images, is_image_relevant_to_entity_url
from .text_utils import is_boilerplate_text, normalize_key
from .web_extractor import extract_page

_MAX_ENTITY_IMAGES = 10


def process_page(
    url: str,
    args: argparse.Namespace,
) -> tuple[list[Any], Any, dict[str, Any]]:
    """Extract and enrich entities from a single page. Returns (entities, page, image_report)."""
    page = extract_page(url)
    model = args.model or configured_model()
    entities = extract_entities(page, use_ai=not args.no_ai, model=model)
    entities = enrich_entities_images(entities, page)
    image_analysis_report: dict[str, Any] = {
        "enabled": False,
        "status": "not_requested",
        "candidates_count": 0,
        "accepted_count": 0,
        "accepted": [],
        "errors": [],
    }
    if args.analyze_images:
        entities, image_analysis_report = analyze_images_with_vision(
            entities,
            page,
            model=model,
            strategy=args.image_strategy,
        )
    entities = attach_block_evidence(entities, page)
    entities = merge_entities(entities)
    wikidata_coords = getattr(args, "wikidata_coords", False)
    entities = enrich_entities_coordinates(
        entities, page, geocode=args.geocode, wikidata_coords=wikidata_coords
    )
    entities = enrich_entities_wikidata_images(entities)
    entities = enrich_entities_external_context(entities, page)
    if args.geocode:
        entities = enrich_entities_geosearch_images(entities)
    entities = consolidate_entity_evidence(entities)
    entities = classify_entities(entities)
    entities = sanitize_entity_images(entities)
    return entities, page, image_analysis_report


def consolidate_entity_evidence(entities: Any) -> Any:
    for entity in entities:
        for source in entity.sources:
            if source.url and source.source_type not in {"page_block", "page"}:
                entity.relatedUrls = [*entity.relatedUrls, source.url]
                entity.images = [
                    *entity.images,
                    *[
                        image
                        for image in source.images
                        if is_trusted_image_source(image) or is_image_relevant_to_entity_url(image, entity)
                    ],
                ]
                if source.text:
                    entity.longDescription = _append_context(entity.longDescription, source.text)
                    entity.description = _append_context(entity.description, source.text)
            if not entity.address and source.metadata.get("address"):
                entity.address = str(source.metadata["address"])
            if not entity.phone and source.metadata.get("phone"):
                entity.phone = str(source.metadata["phone"])
    return entities


def sanitize_entity_images(entities: Any) -> Any:
    for entity in entities:
        clean_images = []
        seen = set()
        clean_related_urls = []
        for url in entity.relatedUrls:
            if is_image_url(url):
                entity.images = [*entity.images, url]
                continue
            clean_related_urls.append(url)
        if entity.url and is_image_url(entity.url):
            entity.images = [*entity.images, entity.url]
            entity.url = ""
        for image in entity.images:
            if (
                not image
                or image in seen
                or is_noise_image(image)
                or (not is_trusted_image_source(image) and not is_image_relevant_to_entity_url(image, entity))
            ):
                continue
            seen.add(image)
            clean_images.append(image)
        entity.images = _rank_and_cap_images(clean_images, entity, _MAX_ENTITY_IMAGES)
        entity.relatedUrls = _dedupe_urls(clean_related_urls)
    return entities


def _rank_and_cap_images(images: list[str], entity: Any, max_count: int) -> list[str]:
    name_words = {w for w in normalize_key(entity.name).split() if len(w) >= 4}
    if not name_words:
        return images[:max_count]

    def _slug_score(url: str) -> int:
        slug = normalize_key(_up(unquote(url)).path.replace("/", " "))
        return sum(1 for w in name_words if w in slug)

    scored = sorted(range(len(images)), key=lambda i: _slug_score(images[i]), reverse=True)
    return [images[i] for i in scored[:max_count]]


def _append_context(current: str, incoming: str) -> str:
    current = (current or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming if not is_boilerplate_text(incoming) else current
    if incoming in current:
        return current
    if current in incoming:
        return incoming
    if is_boilerplate_text(incoming):
        return current
    return f"{current} {incoming}"


def _dedupe_urls(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
