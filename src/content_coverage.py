from __future__ import annotations

from typing import Any

from .models import Entity, PageExtraction
from .text_utils import normalize_key


TOURIST_SIGNALS = {
    "arte",
    "basilica",
    "capilla",
    "cartuja",
    "castillo",
    "catedral",
    "centro cultural",
    "concierto",
    "exposicion",
    "festival",
    "iglesia",
    "monasterio",
    "monumento",
    "museo",
    "palacio",
    "parque",
    "patrimonio",
    "ruta",
    "semana santa",
    "teatro",
    "turismo",
    "visita",
}

NAVIGATION_TITLES = {
    "descubre",
    "gastronomia",
    "inicio",
    "planifica tu viaje",
    "profesionales",
    "que hacer",
    "que ver",
    "turismo en familia",
}

NAVIGATION_MARKERS = {
    "saber mas",
    "contacto",
    "aviso legal",
    "politica de privacidad",
    "accesibilidad",
    "newsletter",
    "descarga material",
}


def analyze_content_coverage(page: PageExtraction, entities: list[Entity]) -> dict[str, Any]:
    covered_blocks = _covered_blocks_by_entity(entities)

    resolutions = []
    status_counts: dict[str, int] = {}
    for block in page.blocks:
        reasons = _tourist_reasons(block.title, block.text, len(block.images))
        if not reasons:
            continue

        resolution = _resolve_block(block, reasons, entities, covered_blocks)
        resolutions.append(resolution)
        status_counts[resolution["status"]] = status_counts.get(resolution["status"], 0) + 1

    candidate_count = len(resolutions)
    resolved_statuses = {
        "attached_to_entity",
        "covered_by_related_entities",
        "discarded_navigation",
        "discarded_noise",
    }
    covered_candidate_count = sum(1 for item in resolutions if item["status"] in resolved_statuses)
    unresolved_blocks = [
        item for item in resolutions if item["status"] == "unresolved_relevant"
    ]
    coverage_ratio = (
        round(covered_candidate_count / candidate_count, 3)
        if candidate_count
        else None
    )
    return {
        "total_blocks": len(page.blocks),
        "candidate_tourist_blocks": candidate_count,
        "covered_candidate_blocks": covered_candidate_count,
        "uncovered_candidate_blocks": len(unresolved_blocks),
        "coverage_ratio": coverage_ratio,
        "status_counts": status_counts,
        "block_resolution": resolutions[:80],
        "uncovered_blocks": unresolved_blocks[:20],
    }


def _tourist_reasons(title: str, text: str, image_count: int) -> list[str]:
    normalized = normalize_key(" ".join([title, text]))
    reasons = [
        signal
        for signal in sorted(TOURIST_SIGNALS)
        if normalize_key(signal) in normalized
    ]
    if image_count and len(normalized.split()) >= 8:
        reasons.append("imagenes_en_bloque")
    return reasons[:6]


def _covered_blocks_by_entity(entities: list[Entity]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for entity in entities:
        for source in entity.sources:
            if not source.block_id or source.block_id == "page":
                continue
            result.setdefault(source.block_id, []).append(entity.name)
    return result


def _resolve_block(
    block,
    reasons: list[str],
    entities: list[Entity],
    covered_blocks: dict[str, list[str]],
) -> dict[str, Any]:
    base = {
        "block_id": block.block_id,
        "title": block.title,
        "excerpt": block.text[:240],
        "image_count": len(block.images),
        "reasons": reasons,
    }

    directly_attached = covered_blocks.get(block.block_id, [])
    if directly_attached:
        return {
            **base,
            "status": "attached_to_entity",
            "covered_by": _dedupe(directly_attached),
            "resolution_reason": "El bloque aparece como evidencia directa de una o varias entidades.",
        }

    related = _related_entities(block.title, block.text, entities)
    if related:
        return {
            **base,
            "status": "covered_by_related_entities",
            "covered_by": related,
            "resolution_reason": "El bloque no esta como evidencia directa, pero su contenido queda cubierto por entidades relacionadas ya extraidas.",
        }

    if _looks_like_navigation(block.title, block.text):
        return {
            **base,
            "status": "discarded_navigation",
            "covered_by": [],
            "resolution_reason": "El bloque parece una agrupacion de navegacion o enlaces, no una ficha de contenido independiente.",
        }

    if _looks_like_noise(block.text):
        return {
            **base,
            "status": "discarded_noise",
            "covered_by": [],
            "resolution_reason": "El bloque parece ruido tecnico o plantilla.",
        }

    return {
        **base,
        "status": "unresolved_relevant",
        "covered_by": [],
        "resolution_reason": "El bloque contiene senales turisticas, pero no se ha creado entidad, asociado evidencia ni justificado descarte.",
    }


def _related_entities(title: str, text: str, entities: list[Entity]) -> list[str]:
    block_key = normalize_key(" ".join([title, text]))
    related = []
    for entity in entities:
        entity_key = normalize_key(entity.name)
        tokens = [token for token in entity_key.split() if len(token) >= 4]
        if not tokens:
            continue
        if entity_key and entity_key in block_key:
            related.append(entity.name)
            continue
        token_matches = sum(1 for token in tokens if token in block_key)
        if token_matches >= min(2, len(tokens)):
            related.append(entity.name)
    return _dedupe(related)[:8]


def _looks_like_navigation(title: str, text: str) -> bool:
    title_key = normalize_key(title)
    text_key = normalize_key(text)
    words = text_key.split()
    marker_count = sum(1 for marker in NAVIGATION_MARKERS if normalize_key(marker) in text_key)
    if title_key in NAVIGATION_TITLES and len(words) <= 35:
        return True
    if marker_count >= 2 and len(words) <= 80:
        return True
    if text_key.count("saber mas") >= 2:
        return True
    return False


def _looks_like_noise(text: str) -> bool:
    text_key = normalize_key(text)
    return any(
        marker in text_key
        for marker in [
            "se ha producido un error al procesar la plantilla",
            "the following has evaluated to null",
            "document cookie",
        ]
    )


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
