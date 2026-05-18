from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .ai_client import configured_model
from .content_coverage import analyze_content_coverage
from .entity_extractor import extract_entities
from .entity_merger import attach_block_evidence, merge_entities
from .geo import enrich_entities_coordinates, enrich_entities_external_context, enrich_entities_wikidata_images
from .ground_truth import compare_entities, load_ground_truth
from .image_ai import analyze_images_with_vision
from .image_filters import is_image_url, is_noise_image
from .images import enrich_entities_images
from .knowledge_base import load_kb, merge_into_kb, save_kb
from .web_extractor import extract_page


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MVP de extraccion web semantica.")
    parser.add_argument("url", help="URL publica HTTP o HTTPS.")
    parser.add_argument("--output", help="Ruta opcional para guardar el JSON.")
    parser.add_argument("--quiet", action="store_true", help="No imprime el JSON en consola.")
    parser.add_argument("--ground-truth", help="Ruta a ground_truth.json.")
    parser.add_argument(
        "--ground-truth-scope",
        choices=["domain", "all"],
        default="domain",
        help="Ambito de comparacion del golden set. Por defecto compara solo mismo dominio.",
    )
    parser.add_argument("--no-ai", action="store_true", help="Desactiva extraccion asistida por IA.")
    parser.add_argument(
        "--geocode",
        action="store_true",
        help="Permite consultar OpenStreetMap/Nominatim para completar coordenadas.",
    )
    parser.add_argument(
        "--analyze-images",
        action="store_true",
        help="Usa IA visual para validar relacion entre imagenes candidatas y entidades.",
    )
    parser.add_argument(
        "--image-strategy",
        choices=["heuristic-first", "vision-first", "disambiguation"],
        default="heuristic-first",
        help=(
            "Estrategia de imagenes. "
            "heuristic-first: vision valida y complementa las imagenes del heurístico. "
            "vision-first: vision reemplaza las imagenes del heurístico. "
            "disambiguation: vision evalua TODAS las imagenes de la pagina para resolver "
            "casos donde el heuristico no puede emparejar (slugs opacos, contextos ambiguos)."
        ),
    )
    parser.add_argument("--model", default=None, help="Modelo OpenAI. Por defecto usa OPENAI_MODEL.")
    parser.add_argument(
        "--kb",
        default=None,
        metavar="PATH",
        help="Ruta al fichero JSON de base de conocimiento acumulativa.",
    )
    parser.add_argument(
        "--format",
        choices=["full", "clean", "golden"],
        default="full",
        help="Formato de salida. 'golden' emite una lista compatible con ground_truth.json.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv()
    page = extract_page(args.url)
    model = args.model or configured_model()
    entities = extract_entities(page, use_ai=not args.no_ai, model=model)
    entities = enrich_entities_images(entities, page)
    image_analysis_report = {
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
    entities = enrich_entities_coordinates(entities, page, geocode=args.geocode)
    if args.geocode:
        entities = enrich_entities_wikidata_images(entities)
        entities = enrich_entities_external_context(entities, page)
    entities = _consolidate_entity_evidence(entities)
    entities = _sanitize_entity_images(entities)

    output_format = getattr(args, "format", "full")
    use_clean = output_format == "clean"
    use_golden = output_format == "golden"

    # Knowledge base: load → merge → save
    kb_report: dict[str, Any] | None = None
    if args.kb:
        kb_entities = load_kb(args.kb)
        kb_entities, kb_report = merge_into_kb(kb_entities, entities)
        kb_entities = _sanitize_entity_images(kb_entities)
        save_kb(args.kb, kb_entities)
        # In compact modes, output the full KB (all accumulated entities)
        if use_clean or use_golden:
            entities = kb_entities

    if use_golden:
        result = _build_golden_result(entities)
    elif use_clean:
        result = _build_clean_result(page.url, entities)
        result["content_coverage_report"] = analyze_content_coverage(page, entities)
        if kb_report:
            result["kb_report"] = kb_report
    else:
        result = {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "model": None if args.no_ai else model,
            "page": _page_summary(page),
            "entities": _build_golden_result(entities),
            "image_analysis_report": image_analysis_report,
            "content_coverage_report": _coverage_summary(analyze_content_coverage(page, entities)),
        }
        if kb_report:
            result["kb_report"] = kb_report

    if args.ground_truth and not use_clean and not use_golden:
        expected = load_ground_truth(args.ground_truth)
        result["ground_truth_report"] = compare_entities(
            entities,
            expected,
            source_url=page.url,
            scope=args.ground_truth_scope,
        )

    return result


CLEAN_COORDS_MIN_CONFIDENCE = 0.3


def _build_clean_result(url: str, entities: Any) -> dict[str, Any]:
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


def _page_summary(page) -> dict[str, Any]:
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


def _coverage_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_blocks": report.get("total_blocks"),
        "candidate_tourist_blocks": report.get("candidate_tourist_blocks"),
        "covered_candidate_blocks": report.get("covered_candidate_blocks"),
        "uncovered_candidate_blocks": report.get("uncovered_candidate_blocks"),
        "coverage_ratio": report.get("coverage_ratio"),
        "status_counts": report.get("status_counts", {}),
    }


def _build_golden_result(entities: Any) -> list[dict[str, Any]]:
    return [_golden_entity(entity) for entity in entities]


def _golden_entity(entity) -> dict[str, Any]:
    return {
        "name": entity.name,
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
        },
        "shortDescription": entity.shortDescription,
        "longDescription": entity.longDescription,
        "sourceText": entity.sourceText,
        "description": entity.description,
        "images": entity.images,
        "wikidataId": entity.wikidataId,
    }


def _sanitize_entity_images(entities: Any) -> Any:
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
            if not image or image in seen or is_noise_image(image):
                continue
            seen.add(image)
            clean_images.append(image)
        entity.images = clean_images
        entity.relatedUrls = _dedupe_urls(clean_related_urls)
    return entities


def _consolidate_entity_evidence(entities: Any) -> Any:
    for entity in entities:
        for source in entity.sources:
            if source.url and source.source_type not in {"page_block", "page"}:
                entity.relatedUrls = [*entity.relatedUrls, source.url]
                entity.images = [*entity.images, *source.images]
                if source.text:
                    entity.longDescription = _append_context(entity.longDescription, source.text)
                    entity.description = _append_context(entity.description, source.text)
            if not entity.address and source.metadata.get("address"):
                entity.address = str(source.metadata["address"])
            if not entity.phone and source.metadata.get("phone"):
                entity.phone = str(source.metadata["phone"])
    return entities


def _append_context(current: str, incoming: str) -> str:
    current = (current or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming in current:
        return current
    if current in incoming:
        return incoming
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")
    if not args.quiet:
        _print_output(output)


def _print_output(output: str) -> None:
    try:
        print(output)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
