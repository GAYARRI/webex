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
from .crawler import SiteCrawl
from .entity_resolver import resolve_into_kb
from .knowledge_base import load_kb, save_kb, tag_sources_with_page_url
from .report import count_by_type, to_markdown
from .text_utils import is_boilerplate_text, normalize_key
from .web_extractor import extract_page, fetch_html, parse_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MVP de extraccion web semantica.")
    parser.add_argument("url", nargs="?", help="URL publica HTTP o HTTPS.")
    parser.add_argument(
        "--urls",
        nargs="+",
        metavar="URL",
        help="Varias URLs para procesamiento batch (requiere --kb).",
    )
    parser.add_argument(
        "--urls-file",
        metavar="PATH",
        help="Fichero con una URL por linea para procesamiento batch (requiere --kb).",
    )
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
        "--merge-threshold",
        type=float,
        default=0.70,
        metavar="FLOAT",
        help="Umbral de similitud para fusionar entidades entre paginas (0-1, default 0.70).",
    )
    parser.add_argument(
        "--format",
        choices=["full", "clean", "golden"],
        default="full",
        help="Formato de salida. 'golden' emite una lista compatible con ground_truth.json.",
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Procesa el site completo a partir de la URL raiz, descubriendo enlaces internos.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        metavar="N",
        help="Numero maximo de paginas a procesar en modo --crawl (default: 50).",
    )
    parser.add_argument(
        "--output-md",
        metavar="PATH",
        help="Ruta para guardar el informe en formato Markdown.",
    )
    parser.add_argument(
        "--no-sitemap",
        action="store_true",
        help="Desactiva la descubrimiento de URLs via sitemap.xml en modo --crawl.",
    )
    parser.add_argument(
        "--lang",
        default="",
        metavar="CODE",
        help="Filtra URLs por idioma en modo --crawl (ej: es, en, fr). Descarta paginas con prefijo de otro idioma.",
    )
    return parser


def _process_page(
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
    entities = enrich_entities_coordinates(entities, page, geocode=args.geocode)
    if args.geocode:
        entities = enrich_entities_wikidata_images(entities)
        entities = enrich_entities_external_context(entities, page)
    entities = _consolidate_entity_evidence(entities)
    entities = _sanitize_entity_images(entities)
    return entities, page, image_analysis_report


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv()
    model = args.model or configured_model()
    entities, page, image_analysis_report = _process_page(args.url, args)

    output_format = getattr(args, "format", "full")
    use_clean = output_format == "clean"
    use_golden = output_format == "golden"

    # Knowledge base: load → tag → resolve → save
    kb_report: dict[str, Any] | None = None
    if args.kb:
        kb_entities = load_kb(args.kb)
        tag_sources_with_page_url(entities, args.url)
        threshold = getattr(args, "merge_threshold", 0.70)
        kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
        kb_entities = _sanitize_entity_images(kb_entities)
        save_kb(args.kb, kb_entities)
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


def _collect_urls(args: argparse.Namespace) -> list[str]:
    if getattr(args, "urls", None):
        return list(args.urls)
    if getattr(args, "urls_file", None):
        lines = Path(args.urls_file).read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    if getattr(args, "url", None):
        return [args.url]
    return []


def run_batch(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv()
    urls = _collect_urls(args)
    model = args.model or configured_model()

    kb_entities: list[Any] = load_kb(args.kb) if args.kb else []
    pages_report: list[dict[str, Any]] = []
    added_total = 0
    enriched_total = 0

    threshold = getattr(args, "merge_threshold", 0.70)
    for url in urls:
        try:
            entities, _page, _img_report = _process_page(url, args)
            tag_sources_with_page_url(entities, url)
            kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
            kb_entities = _sanitize_entity_images(kb_entities)
            if args.kb:
                save_kb(args.kb, kb_entities)
            added_total += kb_report["added"]
            enriched_total += kb_report["enriched"]
            pages_report.append({
                "url": url,
                "status": "ok",
                "added": kb_report["added"],
                "enriched": kb_report["enriched"],
                "added_names": kb_report["added_names"],
                "enriched_names": kb_report["enriched_names"],
            })
        except Exception as exc:
            pages_report.append({
                "url": url,
                "status": "error",
                "error": f"{exc.__class__.__name__}: {exc}",
            })

    batch_report = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "model": None if args.no_ai else model,
        "pages_processed": sum(1 for p in pages_report if p["status"] == "ok"),
        "pages_error": sum(1 for p in pages_report if p["status"] == "error"),
        "added_total": added_total,
        "enriched_total": enriched_total,
        "kb_total": len(kb_entities),
        "pages": pages_report,
    }

    output_format = getattr(args, "format", "full")
    if output_format == "golden":
        return {"batch_report": batch_report, "entities": _build_golden_result(kb_entities)}
    elif output_format == "clean":
        first_url = urls[0] if urls else ""
        result = _build_clean_result(first_url, kb_entities)
        result["batch_report"] = batch_report
        return result
    else:
        return {**batch_report, "entities": _build_golden_result(kb_entities)}


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


_MAX_ENTITY_IMAGES = 10


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
        entity.images = _rank_and_cap_images(clean_images, entity, _MAX_ENTITY_IMAGES)
        entity.relatedUrls = _dedupe_urls(clean_related_urls)
    return entities


def _rank_and_cap_images(images: list[str], entity: Any, max_count: int) -> list[str]:
    """Sort images by slug relevance to entity name, keep top max_count."""
    from urllib.parse import unquote, urlparse as _up
    name_words = {w for w in normalize_key(entity.name).split() if len(w) >= 4}
    if not name_words:
        return images[:max_count]

    def _slug_score(url: str) -> int:
        slug = normalize_key(_up(unquote(url)).path.replace("/", " "))
        return sum(1 for w in name_words if w in slug)

    scored = sorted(range(len(images)), key=lambda i: _slug_score(images[i]), reverse=True)
    return [images[i] for i in scored[:max_count]]


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


def run_crawl(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv()
    if not args.url:
        raise ValueError("--crawl requiere una URL raiz.")
    model = args.model or configured_model()
    threshold = getattr(args, "merge_threshold", 0.70)

    use_sitemap = not getattr(args, "no_sitemap", False)
    quiet = getattr(args, "quiet", False)

    def _progress(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr, flush=True)

    _progress(f"Crawl iniciado: {args.url}  (max {args.max_pages} paginas)")
    if use_sitemap:
        _progress("  Buscando sitemap.xml ...")

    lang = getattr(args, "lang", "") or ""
    crawl = SiteCrawl(args.url, args.max_pages, use_sitemap=use_sitemap, lang=lang)

    if use_sitemap:
        if crawl.sitemap_urls_found:
            _progress(f"  Sitemap encontrado: {crawl.sitemap_urls_found} URLs cargadas en cola")
        else:
            _progress("  Sitemap no encontrado, modo BFS puro")

    kb_entities: list[Any] = load_kb(args.kb) if args.kb else []
    pages_report: list[dict[str, Any]] = []
    added_total = 0
    enriched_total = 0

    for url in crawl:
        n = crawl.visited_count
        _progress(f"[{n}/{args.max_pages}] {url}")
        try:
            resolved_url, html, fetch_warnings = fetch_html(url)
            page = parse_html(resolved_url, html, errors=fetch_warnings)
            entities = extract_entities(page, use_ai=not args.no_ai, model=model)
            entities = enrich_entities_images(entities, page)
            if args.analyze_images:
                entities, _ = analyze_images_with_vision(
                    entities, page, model=model, strategy=args.image_strategy
                )
            entities = attach_block_evidence(entities, page)
            entities = merge_entities(entities)
            entities = enrich_entities_coordinates(entities, page, geocode=args.geocode)
            if args.geocode:
                entities = enrich_entities_wikidata_images(entities)
                entities = enrich_entities_external_context(entities, page)
            entities = _consolidate_entity_evidence(entities)
            entities = _sanitize_entity_images(entities)
            tag_sources_with_page_url(entities, url)
            kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
            kb_entities = _sanitize_entity_images(kb_entities)
            if args.kb:
                save_kb(args.kb, kb_entities)
            added_total += kb_report["added"]
            enriched_total += kb_report["enriched"]
            pages_report.append({
                "url": url,
                "status": "ok",
                "added": kb_report["added"],
                "enriched": kb_report["enriched"],
            })
            _progress(
                f"       +{kb_report['added']} nuevas  "
                f"~{kb_report['enriched']} enriquecidas  "
                f"KB total: {len(kb_entities)}"
            )
            crawl.feed(html, url)
        except Exception as exc:
            pages_report.append({
                "url": url,
                "status": "error",
                "error": f"{exc.__class__.__name__}: {exc}",
            })
            _progress(f"       ERROR: {exc.__class__.__name__}: {exc}")

    ok_count = sum(1 for p in pages_report if p["status"] == "ok")
    err_count = sum(1 for p in pages_report if p["status"] == "error")
    _progress(
        f"\nCrawl completado: {ok_count} páginas OK · {err_count} errores · "
        f"{len(kb_entities)} entidades en KB  "
        f"(+{added_total} nuevas, ~{enriched_total} enriquecidas)"
    )

    crawl_report = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "model": None if args.no_ai else model,
        "pages_processed": ok_count,
        "pages_error": err_count,
        "added_total": added_total,
        "enriched_total": enriched_total,
        "kb_total": len(kb_entities),
        "pages": pages_report,
    }

    output_format = getattr(args, "format", "full")
    if output_format == "golden":
        return {"crawl_report": crawl_report, "entities": _build_golden_result(kb_entities)}
    elif output_format == "clean":
        result = _build_clean_result(args.url, kb_entities)
        result["crawl_report"] = crawl_report
        return result
    else:
        return {**crawl_report, "entities": _build_golden_result(kb_entities)}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    is_crawl = getattr(args, "crawl", False)
    is_batch = bool(getattr(args, "urls", None) or getattr(args, "urls_file", None))

    if is_crawl:
        if not args.url:
            parser.error("--crawl requiere una URL raiz.")
        result = run_crawl(args)
    elif is_batch:
        result = run_batch(args)
    else:
        if not args.url:
            parser.error("Se requiere una URL o --urls / --urls-file.")
        result = run(args)

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output, encoding="utf-8")

    output_md = getattr(args, "output_md", None)
    if output_md:
        entities_for_md = result.get("entities", [])
        crawl_report = result.get("crawl_report") or result.get("batch_report") or {}
        from urllib.parse import urlparse as _urlparse
        source_url = getattr(args, "url", "") or ""
        domain = _urlparse(source_url).netloc.removeprefix("www.") if source_url else ""
        md_content = to_markdown(
            entities_for_md,
            domain=domain,
            pages_processed=crawl_report.get("pages_processed", 0),
            extracted_at=result.get("extracted_at", ""),
        )
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(md_content, encoding="utf-8")

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
