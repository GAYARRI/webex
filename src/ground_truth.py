from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import Entity
from .text_utils import normalize_key


def load_ground_truth(path: str | Path) -> list[Entity]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Entity.from_dict(item) for item in data]


def compare_entities(
    actual: list[Entity],
    expected: list[Entity],
    source_url: str | None = None,
    scope: str = "domain",
) -> dict[str, Any]:
    purpose = "canonical_examples_regression"
    original_expected_count = len(expected)
    if source_url and scope == "domain":
        expected = filter_expected_by_domain(expected, source_url)
        if not expected:
            return {
                "purpose": purpose,
                "coverage_warning": "ground_truth.json contiene ejemplos canonicos, no una lista exhaustiva de contenido turistico.",
                "scope": scope,
                "source_url": source_url,
                "expected_count": 0,
                "original_expected_count": original_expected_count,
                "actual_count": len(actual),
                "found_count": 0,
                "missing_count": 0,
                "additional_count": len(actual),
                "found": [],
                "missing": [],
                "additional": [entity.name for entity in actual if entity.name],
                "type_matches": [],
                "warning": "No hay ejemplos canonicos en ground_truth.json para el dominio procesado. Este archivo no sirve para medir cobertura exhaustiva.",
            }

    actual_by_name = {normalize_key(entity.name): entity for entity in actual if entity.name}
    expected_by_name = {normalize_key(entity.name): entity for entity in expected if entity.name}

    found = sorted(set(actual_by_name) & set(expected_by_name))
    missing = sorted(set(expected_by_name) - set(actual_by_name))
    additional = sorted(set(actual_by_name) - set(expected_by_name))

    type_matches: list[dict[str, Any]] = []
    for key in found:
        actual_types = {normalize_key(item) for item in actual_by_name[key].types}
        expected_types = {normalize_key(item) for item in expected_by_name[key].types}
        type_matches.append(
            {
                "name": expected_by_name[key].name,
                "actualTypes": actual_by_name[key].types,
                "expectedTypes": expected_by_name[key].types,
                "matches": bool(actual_types & expected_types) if expected_types else True,
            }
        )

    return {
        "purpose": purpose,
        "coverage_warning": "ground_truth.json contiene ejemplos canonicos, no una lista exhaustiva de contenido turistico. Usa content_coverage_report para detectar contenido potencialmente no procesado.",
        "scope": scope,
        "source_url": source_url,
        "expected_count": len(expected),
        "original_expected_count": original_expected_count,
        "actual_count": len(actual),
        "found_count": len(found),
        "missing_count": len(missing),
        "additional_count": len(additional),
        "found": [expected_by_name[key].name for key in found],
        "missing": [expected_by_name[key].name for key in missing],
        "additional": [actual_by_name[key].name for key in additional],
        "type_matches": type_matches,
    }


def filter_expected_by_domain(expected: list[Entity], source_url: str) -> list[Entity]:
    source_domain = _domain(source_url)
    if not source_domain:
        return expected
    return [entity for entity in expected if _entity_has_domain(entity, source_domain)]


def _entity_has_domain(entity: Entity, domain: str) -> bool:
    urls = [entity.url, entity.sourceUrl, *entity.relatedUrls]
    return any(_domain(url) == domain for url in urls if url)


def _domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path.split("/")[0]
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host
