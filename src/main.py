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
from .entity_extractor import classify_entities, extract_entities
from .entity_merger import attach_block_evidence, merge_entities
from .ground_truth import compare_entities, load_ground_truth
from .knowledge_base import filter_low_quality_entities, load_crawled_urls, load_kb, save_kb, tag_sources_with_page_url
from .crawler import SiteCrawl
from .entity_resolver import resolve_into_kb
from .models import Entity
from .pipeline import consolidate_entity_evidence, process_page, sanitize_entity_images
from .report import to_markdown
from .serializers import apply_flatten, build_clean_result, build_golden_result, coverage_summary, page_summary
from .virtuoso_exporter import ExportDefaults, VirtuosoSchema, export_entities
from .web_extractor import fetch_html, parse_html


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
    parser.add_argument(
        "--urls-rss",
        metavar="URL",
        help="Feed RSS/Atom del que extraer URLs de artículos para procesamiento batch (requiere --kb).",
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
        "--no-vision",
        action="store_true",
        help="Compatibilidad: la vision por LLM ya esta desactivada por defecto.",
    )
    parser.add_argument(
        "--image-strategy",
        choices=["heuristic-first", "vision-first", "disambiguation", "fallback"],
        default="heuristic-first",
        help=(
            "Estrategia de imagenes. "
            "heuristic-first: vision valida y complementa las imagenes del heurístico. "
            "vision-first: vision reemplaza las imagenes del heurístico. "
            "disambiguation: vision evalua TODAS las imagenes de la pagina para resolver "
            "casos donde el heuristico no puede emparejar (slugs opacos, contextos ambiguos). "
            "fallback: vision solo actua para entidades sin imagen tras el heuristico."
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
        default=0.75,
        metavar="FLOAT",
        help="Umbral de similitud para fusionar entidades entre paginas (0-1, default 0.75).",
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
        default=None,
        metavar="N",
        help="Numero maximo de paginas a procesar en modo --crawl. Sin limite por defecto.",
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
    parser.add_argument(
        "--no-flatten",
        action="store_false",
        dest="flatten",
        default=True,
        help="Desactiva el post-proceso de aplanado (summary unificado + verificación de imágenes rotas).",
    )
    parser.add_argument(
        "--wikidata-coords",
        action="store_true",
        help=(
            "Busca coordenadas en Wikidata para entidades sin wikidataId conocido "
            "(sin OSM). Más rápido que --geocode."
        ),
    )
    parser.add_argument(
        "--discover-rss",
        metavar="URL",
        help="Descubre feeds RSS de un sitio web y los muestra filtrados por --topic.",
    )
    parser.add_argument(
        "--topic",
        metavar="KEYWORD",
        default="",
        help="Filtra los feeds RSS descubiertos por palabra clave (ej: turismo, viajes).",
    )
    parser.add_argument(
        "--read-rss",
        metavar="URL",
        help="Lee y muestra los artículos de un feed RSS o Atom.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="Número máximo de artículos a mostrar con --read-rss (default: 20).",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=0,
        metavar="N",
        help="Muestra solo artículos de los últimos N días con --read-rss.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Muestra el resumen de cada artículo con --read-rss.",
    )
    parser.add_argument(
        "--json-to-md",
        metavar="PATH",
        help="Convierte un JSON de salida existente a Markdown (usar con --output-md).",
    )
    parser.add_argument(
        "--virtuoso-output",
        metavar="PATH",
        help="Ruta para guardar payloads GraphQL/Virtuoso generados desde las entidades extraidas.",
    )
    parser.add_argument(
        "--virtuoso-introspection",
        default="Introspection.json",
        metavar="PATH",
        help="Ruta al introspection.json de GraphQL/Virtuoso.",
    )
    parser.add_argument(
        "--virtuoso-dti",
        default="",
        metavar="VALUE",
        help="Valor dti requerido por las mutations GraphQL/Virtuoso.",
    )
    parser.add_argument("--virtuoso-org", default="", metavar="VALUE", help="Valor org para Virtuoso.")
    parser.add_argument("--virtuoso-lang", default="es", metavar="CODE", help="Idioma de literales Virtuoso.")
    parser.add_argument(
        "--virtuoso-country",
        default="España",
        metavar="VALUE",
        help="Pais por defecto para LocationInput.",
    )
    parser.add_argument(
        "--virtuoso-autonomous-community",
        default="",
        metavar="VALUE",
        help="Comunidad autonoma por defecto para LocationInput.",
    )
    parser.add_argument(
        "--virtuoso-province",
        default="",
        metavar="VALUE",
        help="Provincia por defecto para LocationInput.",
    )
    parser.add_argument(
        "--virtuoso-municipality",
        default="",
        metavar="VALUE",
        help="Municipio por defecto para LocationInput.",
    )
    parser.add_argument(
        "--virtuoso-postal-code",
        default="",
        metavar="VALUE",
        help="Codigo postal por defecto para LocationInput.",
    )
    parser.add_argument(
        "--virtuoso-external-id-prefix",
        default="webex",
        metavar="VALUE",
        help="Prefijo para externalId estable en Virtuoso.",
    )
    return parser


def _collect_urls(args: argparse.Namespace) -> list[str]:
    if getattr(args, "urls", None):
        return list(args.urls)
    if getattr(args, "urls_file", None):
        lines = Path(args.urls_file).read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    if getattr(args, "url", None):
        return [args.url]
    return []


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv()
    model = args.model or configured_model()
    entities, page, image_analysis_report = process_page(args.url, args)

    output_format = getattr(args, "format", "full")
    use_clean = output_format == "clean"
    use_golden = output_format == "golden"

    kb_report: dict[str, Any] | None = None
    if args.kb:
        kb_entities = load_kb(args.kb)
        tag_sources_with_page_url(entities, args.url)
        threshold = getattr(args, "merge_threshold", 0.70)
        kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
        kb_entities = classify_entities(kb_entities)
        kb_entities = sanitize_entity_images(kb_entities)
        save_kb(args.kb, kb_entities)
        if use_clean or use_golden:
            entities = kb_entities

    if use_golden:
        result = build_golden_result(entities)
    elif use_clean:
        result = build_clean_result(page.url, entities)
        result["content_coverage_report"] = analyze_content_coverage(page, entities)
        if kb_report:
            result["kb_report"] = kb_report
    else:
        result = {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "model": None if args.no_ai else model,
            "page": page_summary(page),
            "entities": build_golden_result(entities),
            "image_analysis_report": image_analysis_report,
            "content_coverage_report": coverage_summary(analyze_content_coverage(page, entities)),
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

    return apply_flatten(result, args)


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
            entities, _page, _img_report = process_page(url, args)
            tag_sources_with_page_url(entities, url)
            kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
            kb_entities = classify_entities(kb_entities)
            kb_entities = sanitize_entity_images(kb_entities)
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
        result = {"batch_report": batch_report, "entities": build_golden_result(kb_entities)}
    elif output_format == "clean":
        first_url = urls[0] if urls else ""
        result = build_clean_result(first_url, kb_entities)
        result["batch_report"] = batch_report
    else:
        result = {**batch_report, "entities": build_golden_result(kb_entities)}
    return apply_flatten(result, args)


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

    limit_str = f"max {args.max_pages} paginas" if args.max_pages else "sin limite de paginas"
    _progress(f"Crawl iniciado: {args.url}  ({limit_str})")
    if use_sitemap:
        _progress("  Buscando sitemap.xml ...")

    lang = getattr(args, "lang", "") or ""
    kb_path = args.kb or getattr(args, "output", None)
    crawled_urls: set[str] = load_crawled_urls(kb_path) if kb_path else set()
    if crawled_urls:
        _progress(f"  Retomando crawl: {len(crawled_urls)} paginas ya procesadas, saltando...")

    crawl = SiteCrawl(
        args.url, args.max_pages,
        use_sitemap=use_sitemap, lang=lang,
        already_visited=crawled_urls,
    )

    if use_sitemap:
        if crawl.sitemap_urls_found:
            _progress(f"  Sitemap encontrado: {crawl.sitemap_urls_found} URLs cargadas en cola")
        else:
            _progress("  Sitemap no encontrado, modo BFS puro")

    kb_entities: list[Any] = load_kb(kb_path) if kb_path else []
    pages_report: list[dict[str, Any]] = []
    added_total = 0
    enriched_total = 0

    for url in crawl:
        n = crawl.visited_count
        total = args.max_pages or crawl.total_known
        _progress(f"[{n}/{total}] {url}")
        try:
            resolved_url, html, fetch_warnings = fetch_html(url)
            page = parse_html(resolved_url, html, errors=fetch_warnings)
            entities = _process_crawl_page(page, args, model)
            entities = filter_low_quality_entities(entities)
            tag_sources_with_page_url(entities, url)
            kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
            kb_entities = sanitize_entity_images(kb_entities)
            crawled_urls.add(url)
            if kb_path:
                save_kb(kb_path, kb_entities, crawled_urls=crawled_urls)
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
            if not crawl.sitemap_urls_found:
                crawl.feed(html, url)
        except Exception as exc:
            pages_report.append({
                "url": url,
                "status": "error",
                "error": f"{exc.__class__.__name__}: {exc}",
            })
            _progress(f"       ERROR: {exc.__class__.__name__}: {exc}")

    kb_entities = classify_entities(kb_entities)
    if kb_path:
        save_kb(kb_path, kb_entities, crawled_urls=crawled_urls)

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
        result = {"crawl_report": crawl_report, "entities": build_golden_result(kb_entities)}
    elif output_format == "clean":
        result = build_clean_result(args.url, kb_entities)
        result["crawl_report"] = crawl_report
    else:
        result = {**crawl_report, "entities": build_golden_result(kb_entities)}
    return apply_flatten(result, args)


def _process_crawl_page(page: Any, args: argparse.Namespace, model: str) -> list[Any]:
    """Process a pre-fetched page within a crawl loop (page already downloaded)."""
    from .geo import (
        enrich_entities_coordinates,
        enrich_entities_external_context,
        enrich_entities_geosearch_images,
        enrich_entities_wikidata_images,
    )
    from .image_ai import analyze_images_with_vision
    from .images import enrich_entities_images

    wikidata_coords = getattr(args, "wikidata_coords", False)
    entities = extract_entities(page, use_ai=not args.no_ai, model=model)
    entities = enrich_entities_images(entities, page)
    if args.analyze_images:
        entities, _ = analyze_images_with_vision(
            entities, page, model=model, strategy=args.image_strategy
        )
    entities = attach_block_evidence(entities, page)
    entities = merge_entities(entities)
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
    return entities


def run_rss_batch(args: argparse.Namespace) -> dict[str, Any]:
    from .models import ContentBlock, PageExtraction
    from .rss_reader import read_rss

    load_dotenv()
    model = args.model or configured_model()
    threshold = getattr(args, "merge_threshold", 0.70)
    quiet = getattr(args, "quiet", False)

    def _progress(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr, flush=True)

    articles = read_rss(args.urls_rss, limit=200)
    _progress(f"RSS: {len(articles)} artículos cargados desde {args.urls_rss}")

    kb_path = args.kb or getattr(args, "output", None)
    kb_entities: list[Any] = load_kb(kb_path) if kb_path else []
    pages_report: list[dict[str, Any]] = []
    added_total = 0
    enriched_total = 0

    for i, article in enumerate(articles, 1):
        url = article.get("url", "") or f"rss://article/{i}"
        title = article.get("title", "")
        summary = article.get("summary", "")
        source = article.get("source", "")
        published = article.get("published", "")
        text = f"{title}\n\n{summary}".strip()

        _progress(f"[{i}/{len(articles)}] {title[:80]}")

        try:
            page = PageExtraction(
                url=url,
                title=title,
                description=summary,
                language="es",
                main_text=text,
                raw_text=text,
                images=[],
                status="ok",
                blocks=[
                    ContentBlock(
                        block_id="rss-0",
                        url=url,
                        title=title,
                        text=summary,
                        images=[],
                    )
                ],
                structured_data=[],
                geo_candidates=[],
                errors=[],
            )
            entities = extract_entities(page, use_ai=not args.no_ai, model=model)
            entities = merge_entities(entities)
            entities = classify_entities(entities)
            entities = sanitize_entity_images(entities)
            for entity in entities:
                if not entity.sourceUrl:
                    entity.sourceUrl = url
                if source and not entity.description:
                    entity.description = f"Fuente: {source} ({published})"
            tag_sources_with_page_url(entities, url)
            kb_entities, kb_report = resolve_into_kb(kb_entities, entities, threshold=threshold)
            kb_entities = sanitize_entity_images(kb_entities)
            if kb_path:
                save_kb(kb_path, kb_entities)
            added_total += kb_report["added"]
            enriched_total += kb_report["enriched"]
            pages_report.append({"url": url, "title": title, "status": "ok",
                                  "added": kb_report["added"], "enriched": kb_report["enriched"]})
            _progress(f"       +{kb_report['added']} nuevas  ~{kb_report['enriched']} enriquecidas  KB total: {len(kb_entities)}")
        except Exception as exc:
            pages_report.append({"url": url, "title": title, "status": "error",
                                  "error": f"{exc.__class__.__name__}: {exc}"})
            _progress(f"       ERROR: {exc.__class__.__name__}: {exc}")

    kb_entities = classify_entities(kb_entities)
    if kb_path:
        save_kb(kb_path, kb_entities)

    ok_count = sum(1 for p in pages_report if p["status"] == "ok")
    err_count = sum(1 for p in pages_report if p["status"] == "error")
    _progress(f"\nRSS batch completado: {ok_count} artículos · {len(kb_entities)} entidades en KB (+{added_total} nuevas)")

    batch_report = {
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
        result = {"batch_report": batch_report, "entities": build_golden_result(kb_entities)}
    elif output_format == "clean":
        result = build_clean_result(args.urls_rss, kb_entities)
        result["batch_report"] = batch_report
    else:
        result = {**batch_report, "entities": build_golden_result(kb_entities)}
    return apply_flatten(result, args)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    json_to_md = getattr(args, "json_to_md", None)
    if json_to_md:
        from urllib.parse import urlparse as _urlparse
        data = json.loads(Path(json_to_md).read_text(encoding="utf-8"))
        entities = data.get("entities", [])
        crawl_report = data.get("crawl_report") or data.get("batch_report") or {}
        source_url = crawl_report.get("pages", [{}])[0].get("url", "") if crawl_report.get("pages") else ""
        domain = _urlparse(source_url).netloc.removeprefix("www.") if source_url else Path(json_to_md).stem
        md_content = to_markdown(
            entities,
            domain=domain,
            pages_processed=crawl_report.get("pages_processed", 0),
            extracted_at=data.get("extracted_at", ""),
        )
        output_md = getattr(args, "output_md", None)
        if output_md:
            Path(output_md).parent.mkdir(parents=True, exist_ok=True)
            Path(output_md).write_text(md_content, encoding="utf-8")
            print(f"Markdown guardado en {output_md}")
        else:
            print(md_content)
        return

    discover_rss_url = getattr(args, "discover_rss", None)
    if discover_rss_url:
        from .rss_discover import discover_rss
        topic = getattr(args, "topic", "") or ""
        feeds = discover_rss(discover_rss_url, topic=topic)
        if not feeds:
            print("No se encontraron feeds RSS" + (f" con tema '{topic}'" if topic else "") + ".")
        else:
            for feed in feeds:
                title = f"  [{feed['title']}]" if feed["title"] else ""
                print(f"{feed['url']}{title}")
        return

    read_rss_url = getattr(args, "read_rss", None)
    if read_rss_url:
        from .rss_reader import print_articles, read_rss
        articles = read_rss(
            read_rss_url,
            limit=getattr(args, "limit", 20),
            since_days=getattr(args, "since_days", 0),
        )
        print_articles(articles, show_summary=getattr(args, "summary", False))
        return

    is_crawl = getattr(args, "crawl", False)
    is_rss_batch = bool(getattr(args, "urls_rss", None))
    is_batch = bool(getattr(args, "urls", None) or getattr(args, "urls_file", None))

    if is_crawl:
        if not args.url:
            parser.error("--crawl requiere una URL raiz.")
        result = run_crawl(args)
    elif is_rss_batch:
        result = run_rss_batch(args)
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
        from urllib.parse import urlparse as _urlparse
        entities_for_md = result.get("entities", [])
        crawl_report = result.get("crawl_report") or result.get("batch_report") or {}
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

    virtuoso_output = getattr(args, "virtuoso_output", None)
    if virtuoso_output:
        if not getattr(args, "virtuoso_dti", ""):
            parser.error("--virtuoso-output requiere --virtuoso-dti.")
        _write_virtuoso_output(result, args, virtuoso_output)

    if not args.quiet:
        _print_output(output)


def _write_virtuoso_output(result: dict[str, Any], args: argparse.Namespace, output_path: str) -> dict[str, Any]:
    raw_entities = result.get("entities", [])
    entities = [Entity.from_dict(item) for item in raw_entities if isinstance(item, dict)]
    schema = VirtuosoSchema.from_file(getattr(args, "virtuoso_introspection", "Introspection.json"))
    defaults = ExportDefaults(
        dti=getattr(args, "virtuoso_dti", ""),
        org=getattr(args, "virtuoso_org", ""),
        lang=getattr(args, "virtuoso_lang", "es"),
        country=getattr(args, "virtuoso_country", "España"),
        autonomous_community=getattr(args, "virtuoso_autonomous_community", ""),
        province=getattr(args, "virtuoso_province", ""),
        municipality=getattr(args, "virtuoso_municipality", ""),
        postal_code=getattr(args, "virtuoso_postal_code", ""),
        external_id_prefix=getattr(args, "virtuoso_external_id_prefix", "webex"),
    )
    payloads = export_entities(entities, schema, defaults)
    output = {
        "source": getattr(args, "output", "") or getattr(args, "url", "") or "",
        "count": len(payloads),
        "warningCount": sum(len(item.warnings) for item in payloads),
        "payloads": [item.to_dict() for item in payloads],
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _print_output(output: str) -> None:
    try:
        print(output)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
