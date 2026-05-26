from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from .ai_client import configured_model
from .content_coverage import analyze_content_coverage
from .flattener import flatten_entities

CLEAN_COORDS_MIN_CONFIDENCE = 0.3


def build_golden_result(entities: Any) -> list[dict[str, Any]]:
    return [_golden_entity(e) for e in entities]


def _golden_entity(entity: Any) -> dict[str, Any]:
    return {
        "name": entity.name,
        "type": entity.type,
        "types": entity.types,
        "score": entity.score,
        "sourceUrl": entity.sourceUrl,
        "url": entity.url,
        "relatedUrls": entity.relatedUrls,
        "address": entity.address,
        "phone": entity.phone,
        "email": entity.email,
        "coordinates": {
            "lat": entity.coordinates.lat,
            "lng": entity.coordinates.lng,
            "source": entity.coordinates.source,
            "confidence": entity.coordinates.confidence,
        },
        "shortDescription": entity.shortDescription,
        "longDescription": entity.longDescription,
        "sourceText": entity.sourceText,
        "description": entity.description,
        "images": entity.images,
        "wikidataId": entity.wikidataId,
        "evidence": entity.evidence,
        "classificationEvidence": entity.classificationEvidence,
        "sources": [_source_dict(s) for s in entity.sources],
    }


def _source_dict(source: Any) -> dict[str, Any]:
    return {
        "page_url": source.page_url or source.metadata.get("page_url", "") or source.url,
        "url": source.url,
        "block_id": source.block_id,
        "source_type": source.source_type,
        "title": source.title,
        "text": source.text,
        "images": source.images,
        "metadata": source.metadata,
    }


def build_clean_result(url: str, entities: Any) -> dict[str, Any]:
    clean_entities = []
    for entity in entities:
        coords = entity.coordinates
        reliable = (
            coords.lat is not None
            and (coords.confidence is None or coords.confidence >= CLEAN_COORDS_MIN_CONFIDENCE)
        )
        clean_entities.append(
            {
                "name": entity.name,
                "type": entity.type,
                "sourceUrl": entity.sourceUrl or url,
                "types": entity.types,
                "shortDescription": entity.shortDescription,
                "longDescription": entity.longDescription,
                "images": entity.images,
                "coordinates": {
                    "lat": coords.lat,
                    "lng": coords.lng,
                    "source": coords.source or None,
                    "confidence": coords.confidence,
                }
                if reliable
                else None,
            }
        )
    return {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "entities": clean_entities,
    }


def page_summary(page: Any) -> dict[str, Any]:
    return {
        "url": page.url,
        "title": page.title,
        "description": page.description,
        "language": page.language,
        "status": page.status,
        "errors": page.errors,
        "image_count": len(page.images),
        "block_count": len(page.blocks),
        "structured_data_count": len(page.structured_data),
        "geo_candidates_count": len(page.geo_candidates),
    }


def coverage_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_blocks": report.get("total_blocks"),
        "candidate_tourist_blocks": report.get("candidate_tourist_blocks"),
        "covered_candidate_blocks": report.get("covered_candidate_blocks"),
        "uncovered_candidate_blocks": report.get("uncovered_candidate_blocks"),
        "coverage_ratio": report.get("coverage_ratio"),
        "status_counts": report.get("status_counts", {}),
    }


def apply_flatten(result: dict[str, Any], args: Any) -> dict[str, Any]:
    if not getattr(args, "flatten", False):
        return result
    entities = result.get("entities", [])
    if not entities:
        return result
    model = args.model or configured_model()
    quiet = getattr(args, "quiet", False)
    use_ai = not getattr(args, "no_ai", False)
    if not quiet:
        print(
            f"\nAplanando {len(entities)} entidades (summary + verificación de imágenes)...",
            file=sys.stderr,
            flush=True,
        )
    result["entities"] = flatten_entities(entities, use_ai=use_ai, model=model, quiet=quiet)
    result["entities_output_count"] = len(result["entities"])
    return result
