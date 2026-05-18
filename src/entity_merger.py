from __future__ import annotations

from .contact_extractor import extract_contact_info
from .entity_text import relevant_text_for_entity
from .models import Entity, Evidence, PageExtraction
from .text_utils import compact_text, normalize_key


LEADING_ARTICLES = {"el", "la", "los", "las", "un", "una", "the", "a", "an", "le", "les"}


def _strip_articles(text: str) -> str:
    words = text.split()
    while words and words[0] in LEADING_ARTICLES:
        words = words[1:]
    return " ".join(words)


def attach_block_evidence(entities: list[Entity], page: PageExtraction) -> list[Entity]:
    for entity in entities:
        matching_blocks = _matching_blocks(entity, page)
        for block in matching_blocks:
            relevant_text = relevant_text_for_entity(entity.name, block.text)
            contact = extract_contact_info(relevant_text)
            evidence = Evidence(
                url=page.url,
                block_id=block.block_id,
                source_type="page_block",
                title=block.title,
                text=relevant_text,
                images=[image.get("url", "") for image in block.images if image.get("url")],
                metadata={k: v for k, v in contact.items() if v},
            )
            entity.sources = _merge_sources(entity.sources, [evidence])
            entity.sourceText = _prefer_source_text(entity.sourceText, relevant_text, entity.name)
            if not entity.address and contact["address"]:
                entity.address = contact["address"]
            if not entity.phone and contact["phone"]:
                entity.phone = contact["phone"]
        if not entity.sources:
            entity.sources = _merge_sources(
                entity.sources,
                [
                    Evidence(
                        url=page.url,
                        block_id="page",
                        source_type="page",
                        title=page.title or "",
                        text=entity.evidence or entity.description or entity.shortDescription,
                        images=entity.images,
                    )
                ],
            )
    return entities


def merge_entities(entities: list[Entity]) -> list[Entity]:
    merged: dict[str, Entity] = {}
    for entity in entities:
        key = entity_key(entity)
        if key not in merged:
            merged[key] = entity
            continue
        merged[key] = _merge_entity(merged[key], entity)
    return list(merged.values())


def entity_key(entity: Entity) -> str:
    if entity.wikidataId:
        return f"wikidata:{entity.wikidataId}"
    stripped = _strip_articles(normalize_key(entity.name))
    return f"name:{stripped}"


def _entity_key(entity: Entity) -> str:
    return entity_key(entity)


def _merge_entity(base: Entity, incoming: Entity) -> Entity:
    base.types = _dedupe([*base.types, *incoming.types])
    base.relatedUrls = _dedupe([*base.relatedUrls, *incoming.relatedUrls])
    base.images = _dedupe([*base.images, *incoming.images])
    base.sources = _merge_sources(base.sources, incoming.sources)
    base.shortDescription = _prefer_text(base.shortDescription, incoming.shortDescription)
    base.longDescription = _prefer_text(base.longDescription, incoming.longDescription)
    base.sourceText = _prefer_text(base.sourceText, incoming.sourceText)
    base.description = _prefer_text(base.description, incoming.description)
    base.evidence = compact_text(" ".join(_dedupe([base.evidence, incoming.evidence])))
    if not base.address:
        base.address = incoming.address
    if not base.phone:
        base.phone = incoming.phone
    if not base.email:
        base.email = incoming.email
    if base.coordinates.lat is None and incoming.coordinates.lat is not None:
        base.coordinates = incoming.coordinates
    if base.score is None or (incoming.score is not None and incoming.score > base.score):
        base.score = incoming.score
    return base


def _matching_blocks(entity: Entity, page: PageExtraction):
    name_key = normalize_key(entity.name)
    tokens = [token for token in name_key.split() if len(token) >= 4]
    matches = []
    for block in page.blocks:
        block_text = normalize_key(" ".join([block.title, block.text]))
        score = 0
        if name_key and name_key in block_text:
            score += 100
        title_key = normalize_key(block.title)
        if name_key and name_key in title_key:
            score += 80
        if tokens and sum(1 for token in tokens if token in block_text) >= min(2, len(tokens)):
            score += sum(1 for token in tokens if token in block_text) * 10
        if score:
            word_count = len(block_text.split())
            if word_count <= 120:
                score += 30
            elif word_count > 450:
                score -= 40
            matches.append((score, block))
    matches.sort(key=lambda item: (item[0], -len(item[1].text)), reverse=True)
    return [block for _, block in matches]


def _merge_sources(existing: list[Evidence], incoming: list[Evidence]) -> list[Evidence]:
    by_key: dict[tuple[str, str, str], Evidence] = {
        (item.url, item.block_id, item.source_type): item for item in existing
    }
    for item in incoming:
        key = (item.url, item.block_id, item.source_type)
        if key not in by_key:
            by_key[key] = item
            continue
        current = by_key[key]
        current.text = _prefer_text(current.text, item.text)
        current.images = _dedupe([*current.images, *item.images])
        if not current.title:
            current.title = item.title
        if current.coordinates is None and item.coordinates is not None:
            current.coordinates = item.coordinates
        current.metadata = {**current.metadata, **item.metadata}
    return list(by_key.values())


def _prefer_text(current: str, incoming: str) -> str:
    if len(incoming or "") > len(current or ""):
        return incoming
    return current


def _prefer_source_text(current: str, incoming: str, entity_name: str) -> str:
    if not current:
        return incoming
    current_score = _source_text_score(current, entity_name)
    incoming_score = _source_text_score(incoming, entity_name)
    if incoming_score > current_score:
        return incoming
    return current


def _source_text_score(text: str, entity_name: str) -> int:
    text_key = normalize_key(text)
    name_key = normalize_key(entity_name)
    score = 0
    if name_key and name_key in text_key:
        score += 100
    tokens = [token for token in name_key.split() if len(token) >= 4]
    score += sum(1 for token in tokens if token in text_key) * 10
    word_count = len(text_key.split())
    if word_count <= 120:
        score += 50
    elif word_count <= 250:
        score += 20
    elif word_count > 450:
        score -= 60
    return score


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value or ""
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
