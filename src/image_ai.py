from __future__ import annotations

import json
import base64
import os
from urllib.parse import urlparse

import requests
import urllib3
from dotenv import load_dotenv
from requests.exceptions import SSLError

from .ai_client import _parse_response_text, configured_model
from .image_filters import is_noise_image
from .images import match_images_for_entity
from .models import Entity, Evidence, PageExtraction


VISION_BATCH_SIZE = 8
MAX_IMAGE_BYTES = 4_000_000
_MAX_PAIRS_DEFAULT = 40


def enrich_images_with_vision(
    entities: list[Entity],
    page: PageExtraction,
    model: str | None = None,
    max_entities: int = 20,
    max_images_per_entity: int = 5,
) -> list[Entity]:
    entities, _ = analyze_images_with_vision(
        entities,
        page,
        model=model,
        max_entities=max_entities,
        max_images_per_entity=max_images_per_entity,
    )
    return entities


def analyze_images_with_vision(
    entities: list[Entity],
    page: PageExtraction,
    model: str | None = None,
    max_entities: int = 20,
    max_images_per_entity: int = 5,
    strategy: str = "heuristic-first",
) -> tuple[list[Entity], dict]:
    """
    Strategies:
      heuristic-first  — heuristic-matched images sent to vision; vision appends.
      vision-first     — heuristic-matched images sent to vision; vision replaces.
      disambiguation   — one question per image: "which entity best represents this?".
                         Guarantees every entity and every image gets evaluated regardless
                         of heuristic signal. Each image is assigned to at most one entity.
      fallback         — runs disambiguation only for entities that ended up with 0 images
                         after heuristic matching. Cost-efficient: activates only when needed.
    """
    report = {
        "enabled": True,
        "status": "not_run",
        "strategy": strategy,
        "model": model or os.getenv("OPENAI_VISION_MODEL") or configured_model(),
        "candidates_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "accepted": [],
        "rejected": [],
        "errors": [],
    }
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        report["status"] = "skipped"
        report["errors"].append("OPENAI_API_KEY no esta configurada.")
        return entities, report

    if strategy == "fallback":
        return _run_fallback(entities, page, report)

    if strategy == "disambiguation":
        return _run_disambiguation(entities, page, report)

    # --- heuristic-first / vision-first path ---
    candidates = _candidate_pairs(
        entities[:max_entities],
        page,
        max_images_per_entity=max_images_per_entity,
    )
    report["candidates_count"] = len(candidates)
    if not candidates:
        report["status"] = "skipped"
        report["errors"].append("No hay pares entidad-imagen candidatos.")
        return entities, report

    data = {"matches": []}
    for batch in _batches(candidates, VISION_BATCH_SIZE):
        batch_data, error = _analyze_image_batch(batch, report["model"])
        if error:
            report["errors"].append(error)
            continue
        data["matches"].extend(batch_data.get("matches", []))

    accepted = _accepted_by_entity(data)
    rejected_items = _rejected_items(data)
    accepted_items = []
    for entity in entities:
        urls = accepted.get(entity.name, [])
        if strategy == "vision-first":
            entity.images = _dedupe(urls)
        elif urls:
            entity.images = _dedupe([*entity.images, *urls])
        for url in urls:
            accepted_items.append({"entity": entity.name, "image_url": url})
    report["status"] = "ok" if data["matches"] else "error"
    if not data["matches"] and not report["errors"]:
        report["errors"].append("La IA visual no devolvio resultados.")
    report["accepted"] = accepted_items
    report["accepted_count"] = len(accepted_items)
    report["rejected"] = rejected_items
    report["rejected_count"] = len(rejected_items)
    return entities, report


# ---------------------------------------------------------------------------
# Fallback: vision only for entities with 0 images after heuristic
# ---------------------------------------------------------------------------

def _run_fallback(
    entities: list[Entity],
    page: PageExtraction,
    report: dict,
) -> tuple[list[Entity], dict]:
    """Run disambiguation restricted to entities that have no images yet."""
    without_images = [e for e in entities if not e.images]
    if not without_images:
        report["status"] = "skipped"
        report["errors"].append("Todas las entidades ya tienen imágenes del heurístico.")
        return entities, report
    report["errors"].append(
        f"Fallback vision activado para {len(without_images)} entidades sin imagen."
    )
    _, sub_report = _run_disambiguation(without_images, page, report)
    return entities, sub_report


# ---------------------------------------------------------------------------
# Disambiguation: one question per image → one entity assignment
# ---------------------------------------------------------------------------

def _run_disambiguation(
    entities: list[Entity],
    page: PageExtraction,
    report: dict,
) -> tuple[list[Entity], dict]:
    content_images = [
        img for img in page.images
        if img.get("url") and not _is_bad_vision_candidate(img.get("url", ""))
    ]
    report["candidates_count"] = len(content_images)
    if not content_images:
        report["status"] = "skipped"
        report["errors"].append("No hay imagenes candidatas para desambiguar.")
        return entities, report

    entity_index = [
        {
            "name": e.name,
            "description": (e.shortDescription or e.description or "")[:120],
        }
        for e in entities
    ]
    entity_name_map = {e.name.lower(): e.name for e in entities}

    assignments: dict[str, list[str]] = {}
    rejected: list[dict] = []

    for batch in _image_batches(content_images, VISION_BATCH_SIZE):
        items, error = _classify_image_batch(batch, entity_index, report["model"])
        if error:
            report["errors"].append(error)
            continue
        for item in items:
            url = str(item.get("image_url", ""))
            raw_entity = str(item.get("entity") or "").strip()
            reason = str(item.get("reason", ""))
            resolved = _resolve_entity_name(raw_entity, entity_name_map)
            if resolved:
                assignments.setdefault(resolved, []).append(url)
            else:
                rejected.append({"entity": raw_entity or "ninguna", "image_url": url, "reason": reason})

    accepted_items = []
    for entity in entities:
        urls = _dedupe(assignments.get(entity.name, []))
        entity.images = urls
        if urls:
            entity.sources.append(Evidence(
                url=page.url,
                block_id=f"vision_fallback:{entity.name}",
                source_type="vision_fallback",
                images=urls,
                page_url=page.url,
            ))
        for url in urls:
            accepted_items.append({"entity": entity.name, "image_url": url})

    report["accepted"] = accepted_items
    report["accepted_count"] = len(accepted_items)
    report["rejected"] = rejected
    report["rejected_count"] = len(rejected)
    report["status"] = "ok" if accepted_items or rejected else "error"
    if not accepted_items and not rejected and not report["errors"]:
        report["errors"].append("La IA visual no devolvio resultados.")
    return entities, report


def _classify_image_batch(
    images: list[dict],
    entity_index: list[dict],
    model: str,
) -> tuple[list[dict], str | None]:
    from openai import OpenAI

    client = OpenAI()
    entities_text = "\n".join(
        f"- {e['name']}: {e['description']}" for e in entity_index
    )
    content: list[dict] = [
        {
            "type": "input_text",
            "text": (
                "Entidades turísticas disponibles:\n"
                f"{entities_text}\n\n"
                "Para cada imagen que se muestra a continuación, indica qué entidad de la lista "
                "representa MEJOR visualmente. Usa el contenido visual como criterio principal; "
                "el texto de apoyo (alt, contexto) es orientativo. "
                "Si la imagen es decorativa, un logo, un mapa genérico o no corresponde claramente "
                "a ninguna entidad específica, indica 'ninguna'. "
                "Asigna cada imagen a UNA SOLA entidad. "
                "Si varias podrían asociarse, elige la más específica y representativa. "
                "Devuelve solo JSON válido con esta forma exacta:\n"
                '{"assignments":[{"image_url":"...","entity":"nombre exacto de la lista o ninguna","reason":"..."}]}'
            ),
        }
    ]
    for image in images:
        url = image.get("url", "")
        meta = {
            "url": url,
            "alt": image.get("alt", ""),
            "context": image.get("context", "")[:200],
        }
        image_data = _image_data_url(url) or url
        content.append({"type": "input_text", "text": json.dumps(meta, ensure_ascii=False)})
        content.append({"type": "input_image", "image_url": image_data})

    try:
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": content}],
            text={"format": {"type": "json_object"}},
        )
        data = _parse_response_text(response)
        return data.get("assignments", []), None
    except Exception as exc:
        return [], f"{exc.__class__.__name__}: {exc}"


def _resolve_entity_name(raw: str, entity_name_map: dict[str, str]) -> str | None:
    """Match AI-returned name (may have minor variation) to canonical entity name."""
    if not raw or raw.lower().strip() in {"ninguna", "none", "ninguno", ""}:
        return None
    normalized = raw.lower().strip()
    if normalized in entity_name_map:
        return entity_name_map[normalized]
    for key, name in entity_name_map.items():
        if normalized in key or key in normalized:
            return name
    return None


def _image_batches(images: list[dict], size: int) -> list[list[dict]]:
    return [images[i : i + size] for i in range(0, len(images), size)]


# ---------------------------------------------------------------------------
# Heuristic-first / vision-first helpers (pair-based)
# ---------------------------------------------------------------------------

def _candidate_pairs(
    entities: list[Entity],
    page: PageExtraction,
    max_images_per_entity: int,
) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    page_images_by_url = {image.get("url", ""): image for image in page.images}
    all_content_urls = [
        img.get("url", "")
        for img in page.images
        if img.get("url", "") and not _is_bad_vision_candidate(img.get("url", ""))
    ]
    for entity in entities:
        candidate_urls = match_images_for_entity(entity, page)
        if not candidate_urls:
            candidate_urls = all_content_urls[:max_images_per_entity]
        for url in candidate_urls[:max_images_per_entity]:
            image = page_images_by_url.get(url, {})
            if not url:
                continue
            pairs.append(
                {
                    "entity": entity.name,
                    "entity_description": entity.shortDescription or entity.description,
                    "image_url": url,
                    "image_alt": image.get("alt", ""),
                    "image_context": image.get("context", ""),
                }
            )
    return pairs[:_MAX_PAIRS_DEFAULT]


def _analyze_image_batch(pairs: list[dict[str, str]], model: str) -> tuple[dict, str | None]:
    from openai import OpenAI

    client = OpenAI()
    content = [
        {
            "type": "input_text",
            "text": (
                "Analiza si cada imagen esta relacionada con la entidad propuesta. "
                "Se te presentan pares (entidad, imagen); cada par incluye el nombre de la entidad, "
                "su descripcion, la URL de la imagen, su texto alternativo y el contexto textual de la pagina. "
                "Usa el contenido visual de la imagen como criterio principal. "
                "El contexto textual y el alt son datos de apoyo, pero la imagen puede estar correctamente "
                "asociada aunque el slug de la URL sea opaco (p.ej. 'ermitasanamaro02' es la ermita de San Amaro). "
                "Acepta la imagen si muestra el recurso, lugar, evento o contexto descrito por la entidad. "
                "Acepta varias imagenes por entidad cuando todas son relevantes. "
                "Rechaza logos, iconos, banners, botones, capturas de app e imagenes decorativas sin relacion. "
                "Devuelve solo JSON valido con esta forma exacta: "
                '{"matches":[{"entity":"...","image_url":"...","related":true,"reason":"..."}]}. '
                "Marca related=false si la relacion no esta clara o la imagen es decorativa."
            ),
        }
    ]
    for pair in pairs:
        image_url = _image_data_url(pair["image_url"]) or pair["image_url"]
        content.append({"type": "input_text", "text": json.dumps(pair, ensure_ascii=False)})
        content.append({"type": "input_image", "image_url": image_url})

    try:
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": content}],
            text={"format": {"type": "json_object"}},
        )
        return _parse_response_text(response), None
    except Exception as exc:
        return {"matches": []}, f"{exc.__class__.__name__}: {exc}"


def _batches(values: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _is_bad_vision_candidate(url: str) -> bool:
    return is_noise_image(url)


def _image_data_url(url: str) -> str | None:
    try:
        headers = {"User-Agent": "ExtraccionWebSemantica/0.1"}
        try:
            response = requests.get(url, headers=headers, timeout=15)
        except SSLError:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
    except Exception:
        return None
    content = response.content
    if not content or len(content) > MAX_IMAGE_BYTES:
        return None
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        content_type = _content_type_from_url(url)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _content_type_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def _accepted_by_entity(data: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in data.get("matches", []):
        if not isinstance(item, dict) or not item.get("related"):
            continue
        entity = str(item.get("entity", ""))
        image_url = str(item.get("image_url", ""))
        if entity and image_url:
            result.setdefault(entity, []).append(image_url)
    return result


def _rejected_items(data: dict) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in data.get("matches", []):
        if not isinstance(item, dict) or item.get("related"):
            continue
        entity = str(item.get("entity", ""))
        image_url = str(item.get("image_url", ""))
        reason = str(item.get("reason", ""))
        if entity and image_url:
            result.append({"entity": entity, "image_url": image_url, "reason": reason})
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
