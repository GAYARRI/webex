from __future__ import annotations

import json
from pathlib import Path

from .entity_merger import entity_key
from .models import Entity


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


def save_kb(path: str, entities: list[Entity]) -> None:
    kb_path = Path(path)
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    kb_path.write_text(
        json.dumps({"entities": [e.to_dict() for e in entities]}, ensure_ascii=False, indent=2),
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
    # Descriptions: keep the longer version
    if len(incoming.shortDescription) > len(base.shortDescription):
        base.shortDescription = incoming.shortDescription
    if len(incoming.longDescription) > len(base.longDescription):
        base.longDescription = incoming.longDescription
    if len(incoming.sourceText) > len(base.sourceText):
        base.sourceText = incoming.sourceText
    if len(incoming.description) > len(base.description):
        base.description = incoming.description

    # Images: accumulate without duplicates
    seen = set(base.images)
    for img in incoming.images:
        if img and img not in seen:
            base.images.append(img)
            seen.add(img)

    # Types: union preserving order
    for t in incoming.types:
        if t not in base.types:
            base.types.append(t)

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

    # Sources: accumulate without duplicates
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
