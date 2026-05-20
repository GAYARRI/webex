from __future__ import annotations

import concurrent.futures
import os
import sys
from typing import Any

import urllib3
import requests as _requests
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_IMAGE_CHECK_WORKERS = 20
_IMAGE_CHECK_TIMEOUT = 5
_IMAGE_CHECK_HEADERS = {"User-Agent": "ExtraccionWeb/1.0 (tourism-kb)"}


def _check_image_url(url: str) -> bool:
    try:
        resp = _requests.head(
            url,
            timeout=_IMAGE_CHECK_TIMEOUT,
            allow_redirects=True,
            verify=False,
            headers=_IMAGE_CHECK_HEADERS,
        )
        return resp.status_code < 400
    except Exception:
        return False


def _dedup_images(images: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for img in images:
        if img and img not in seen:
            seen.add(img)
            result.append(img)
    return result


def filter_broken_images(images: list[str], quiet: bool = False) -> list[str]:
    """Deduplicate image URLs and remove those that return HTTP errors."""
    deduped = _dedup_images(images)
    if not deduped:
        return []
    if not quiet:
        print(f"  Verificando {len(deduped)} imágenes...", file=sys.stderr, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=_IMAGE_CHECK_WORKERS) as pool:
        ok_flags = list(pool.map(_check_image_url, deduped))
    valid = [url for url, ok in zip(deduped, ok_flags) if ok]
    if not quiet:
        removed = len(deduped) - len(valid)
        if removed:
            print(f"  {removed} imágenes con enlace roto eliminadas.", file=sys.stderr, flush=True)
    return valid


def _collect_texts(entity: dict[str, Any]) -> list[str]:
    """Return non-empty, non-duplicate text fields in order of informativeness."""
    candidates = [
        entity.get("longDescription", ""),
        entity.get("description", ""),
        entity.get("shortDescription", ""),
        entity.get("sourceText", ""),
    ]
    seen: set[str] = set()
    result: list[str] = []
    for text in candidates:
        text = (text or "").strip()
        if not text or text in seen:
            continue
        # Skip if this text is a substring of one already collected
        if any(text in collected for collected in seen):
            continue
        # If a previously collected text is a substring of this one, replace it
        seen = {s for s in seen if s not in text}
        result = [t for t in result if t not in text]
        seen.add(text)
        result.append(text)
    return result


def _build_summary_no_ai(entity: dict[str, Any]) -> str:
    texts = _collect_texts(entity)
    if not texts:
        return ""
    return max(texts, key=len)


def _build_summary_ai(entity: dict[str, Any], model: str) -> str:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return _build_summary_no_ai(entity)

    texts = _collect_texts(entity)
    if not texts:
        return ""
    if len(texts) == 1 and len(texts[0]) < 200:
        return texts[0]

    from openai import OpenAI
    client = OpenAI()
    combined = "\n\n".join(texts)
    prompt = (
        "Eres un experto en turismo. A partir de los siguientes textos sobre un recurso turístico, "
        "escribe un resumen único, coherente y en español de 2-4 oraciones. "
        "No repitas información. No inventes datos que no estén en los textos.\n\n"
        f"Nombre del recurso: {entity.get('name', '')}\n\n"
        f"Textos:\n{combined}\n\nResumen:"
    )
    try:
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
        )
        text = getattr(response, "output_text", None) or ""
        return text.strip() or _build_summary_no_ai(entity)
    except Exception:
        return _build_summary_no_ai(entity)


def _collect_all_images(entity: dict[str, Any]) -> list[str]:
    all_images: list[str] = list(entity.get("images", []))
    for source in entity.get("sources", []):
        for img in source.get("images", []):
            if img:
                all_images.append(img)
    return all_images


def _promote_coordinates(entity: dict[str, Any]) -> dict[str, Any]:
    """Return the best coordinates: entity-level first, then wikidata, then osm, then any source."""
    coords = entity.get("coordinates") or {}
    if coords.get("lat") and coords.get("lng"):
        return coords
    priority = ["wikidata", "openstreetmap"]
    sources = entity.get("sources", [])
    for source_type in priority:
        for source in sources:
            if source.get("source_type") == source_type:
                c = source.get("coordinates") or {}
                if c.get("lat") and c.get("lng"):
                    return c
    for source in sources:
        c = source.get("coordinates") or {}
        if c.get("lat") and c.get("lng"):
            return c
    return coords


def _promote_wikidata_id(entity: dict[str, Any]) -> str:
    if entity.get("wikidataId"):
        return entity["wikidataId"]
    for source in entity.get("sources", []):
        if source.get("source_type") == "wikidata":
            url = source.get("url", "")
            # URL format: https://www.wikidata.org/wiki/QXXXXXX
            if "/wiki/Q" in url:
                qid = url.rsplit("/", 1)[-1]
                if qid.startswith("Q") and qid[1:].isdigit():
                    return qid
    return entity.get("wikidataId", "")


def _collect_reference_urls(entity: dict[str, Any]) -> list[str]:
    """Unique external reference URLs from wikidata and openstreetmap sources."""
    seen: set[str] = set()
    result: list[str] = []
    for source in entity.get("sources", []):
        if source.get("source_type") in {"wikidata", "openstreetmap", "wikipedia"}:
            url = source.get("url", "")
            if url and url not in seen:
                seen.add(url)
                result.append(url)
    return result


def flatten_entity(
    entity: dict[str, Any],
    *,
    use_ai: bool = True,
    model: str | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Promote and deduplicate all enrichment data; remove sources array."""
    if use_ai and model:
        summary = _build_summary_ai(entity, model)
    else:
        summary = _build_summary_no_ai(entity)

    all_images = _collect_all_images(entity)
    clean_images = filter_broken_images(all_images, quiet=quiet)
    coordinates = _promote_coordinates(entity)
    wikidata_id = _promote_wikidata_id(entity)
    reference_urls = _collect_reference_urls(entity)

    flat: dict[str, Any] = {"summary": summary}
    for key, value in entity.items():
        if key == "sources":
            continue
        elif key == "images":
            flat[key] = clean_images
        elif key == "coordinates":
            flat[key] = coordinates
        elif key == "wikidataId":
            flat[key] = wikidata_id
        else:
            flat[key] = value
    if reference_urls:
        flat["referenceUrls"] = reference_urls
    return flat


def flatten_entities(
    entities: list[dict[str, Any]],
    *,
    use_ai: bool = True,
    model: str | None = None,
    quiet: bool = False,
) -> list[dict[str, Any]]:
    """Flatten a list of serialised entity dicts: build summary, filter images."""
    result = []
    for i, entity in enumerate(entities, 1):
        if not quiet:
            print(
                f"  [{i}/{len(entities)}] Aplanando: {entity.get('name', '?')}",
                file=sys.stderr,
                flush=True,
            )
        result.append(flatten_entity(entity, use_ai=use_ai, model=model, quiet=quiet))
    return result


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Aplana entidades de un KB JSON")
    parser.add_argument("input", help="Fichero JSON de entrada (kb.json)")
    parser.add_argument("output", help="Fichero JSON de salida aplanado")
    parser.add_argument("--no-ai", action="store_true", help="No usar IA para el resumen")
    parser.add_argument("--model", default="gpt-4o-mini", help="Modelo OpenAI para resúmenes")
    parser.add_argument("--quiet", action="store_true", help="Sin salida de progreso")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    entities = data if isinstance(data, list) else data.get("entities", [])
    print(f"Cargadas {len(entities)} entidades desde {args.input}", file=sys.stderr)

    flat = flatten_entities(entities, use_ai=not args.no_ai, model=args.model, quiet=args.quiet)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(flat, f, ensure_ascii=False, indent=2)

    print(f"Guardado en {args.output} ({len(flat)} entidades)", file=sys.stderr)
