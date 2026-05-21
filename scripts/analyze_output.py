from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NAV_TERMS = [
    "Que ver Catedral Camino de Santiago",
    "Qué ver Catedral Camino de Santiago",
    "Mas lugares de interes",
    "Más lugares de interés",
    "Ver mapa",
    "Reserva ahora",
    "Prepara tu viaje",
    "Durante tu estancia",
]

ADDRESS_SUSPECT_TERMS = [
    "ver mapa",
    "se llena de",
    "saber mas",
    "saber más",
    "reserva ahora",
    "circuitos de orientacion",
    "circuitos de orientación",
    "horarios",
    "fecha:",
    "precio:",
    "de lunes",
]

EDITORIAL_NAME_TERMS = [
    "sabias que",
    "sabías que",
    "curiosidades",
    "redescubre",
    "consejos para",
    "opciones unicas",
    "opciones únicas",
    "se encuentra",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostica una salida JSON de extraccion.")
    parser.add_argument("path", help="Ruta al JSON generado por src.main.")
    parser.add_argument("--samples", type=int, default=12, help="Numero de ejemplos por seccion.")
    args = parser.parse_args()

    data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    entities = data.get("entities", [])
    pages = data.get("pages", [])

    print(f"file: {args.path}")
    print(f"pages_ok: {data.get('pages_processed', 0)}")
    print(f"pages_error: {data.get('pages_error', 0)}")
    print(f"kb_total: {data.get('kb_total', '-')}")
    print(f"entities_output_count: {data.get('entities_output_count', len(entities))}")
    print(f"entities_list_count: {len(entities)}")
    print(f"with_images: {sum(bool(e.get('images')) for e in entities)}")
    print(f"max_images: {max((len(e.get('images') or []) for e in entities), default=0)}")
    print(f"with_coords: {sum(bool((e.get('coordinates') or {}).get('lat')) for e in entities)}")
    print(f"empty_summary: {sum(not e.get('summary') for e in entities)}")
    print()

    print("types:")
    for entity_type, count in Counter(e.get("type") or "" for e in entities).most_common(20):
        print(f"  {entity_type or '<empty>'}: {count}")
    print()

    _print_nav_contamination(entities)
    _print_suspect_addresses(entities, args.samples)
    _print_editorial_names(entities, args.samples)
    _print_duplicate_names(entities, args.samples)
    _print_error_pages(pages, args.samples)


def _text(entity: dict[str, Any]) -> str:
    return " ".join(
        str(entity.get(key) or "")
        for key in ("summary", "shortDescription", "longDescription", "description", "sourceText")
    )


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _print_nav_contamination(entities: list[dict[str, Any]]) -> None:
    print("content_noise:")
    found = False
    for term in NAV_TERMS:
        count = sum(term in _text(entity) for entity in entities)
        if count:
            found = True
            print(f"  {term}: {count}")
    if not found:
        print("  <none>")
    print()


def _is_suspect_address(address: str) -> bool:
    lowered = (address or "").casefold()
    return bool(address) and (
        len(address) > 90
        or len(address.split()) > 14
        or any(term in lowered for term in ADDRESS_SUSPECT_TERMS)
    )


def _print_suspect_addresses(entities: list[dict[str, Any]], samples: int) -> None:
    matches = [entity for entity in entities if _is_suspect_address(entity.get("address") or "")]
    print(f"suspect_addresses: {len(matches)}")
    for entity in matches[:samples]:
        address = (entity.get("address") or "")[:180]
        print(f"  - {entity.get('name')} [{entity.get('type')}]: {address}")
    print()


def _is_editorial_name(name: str) -> bool:
    name_key = _norm(name)
    return bool(name_key) and (
        any(term in name_key for term in EDITORIAL_NAME_TERMS)
        or len(name_key.split()) > 14
    )


def _print_editorial_names(entities: list[dict[str, Any]], samples: int) -> None:
    matches = [entity for entity in entities if _is_editorial_name(entity.get("name") or "")]
    print(f"editorial_names: {len(matches)}")
    for entity in matches[:samples]:
        print(f"  - {entity.get('name')} [{entity.get('type')}]")
    print()


def _print_duplicate_names(entities: list[dict[str, Any]], samples: int) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        groups[_norm(entity.get("name") or "")].append(entity)
    duplicates = [group for group in groups.values() if len(group) > 1]
    print(f"exact_duplicate_groups: {len(duplicates)}")
    print(f"exact_duplicate_entities: {sum(len(group) for group in duplicates)}")
    for group in duplicates[:samples]:
        values = ", ".join(f"{e.get('name')} [{e.get('type')}]" for e in group)
        print(f"  - {values}")
    print()


def _print_error_pages(pages: list[dict[str, Any]], samples: int) -> None:
    errors = [page for page in pages if page.get("status") == "error"]
    print(f"error_pages_sample: {len(errors)}")
    for page in errors[:samples]:
        print(f"  - {page.get('url')} => {page.get('error')}")


if __name__ == "__main__":
    main()
