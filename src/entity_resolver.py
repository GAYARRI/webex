from __future__ import annotations

import math
import re
from typing import Any

from .entity_merger import entity_key
from .knowledge_base import _enrich
from .models import Entity
from .text_utils import normalize_key


_DEFAULT_THRESHOLD = 0.90
_BARRIER_KM = 5.0
_PROXIMITY_KM = 0.15

_MIN_TOKEN_LEN = 4
_NAME_STOPWORDS = {
    "de", "del", "la", "las", "los", "el", "en", "por", "the", "of",
    "para", "con", "que", "sus", "una", "uno",
}


def resolve_into_kb(
    kb_entities: list[Entity],
    new_entities: list[Entity],
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[list[Entity], dict]:
    """Resolve incoming entities against the KB using strict identity signals."""
    kb_list: list[Entity] = list(kb_entities)
    kb_index: dict[str, Entity] = {entity_key(e): e for e in kb_list}
    # Secondary index by normalized name alone — catches cases where one copy
    # has a wikidataId (key "wikidata:Q…") and the other doesn't (key "name:…").
    kb_name_index: dict[str, Entity] = {
        f"name:{_strip_articles(normalize_key(e.name))}": e for e in kb_list
    }

    added: list[str] = []
    resolved_pairs: list[dict[str, Any]] = []

    for entity in new_entities:
        key = entity_key(entity)

        # Fast path: exact key means same wikidataId or exact normalized name.
        if key in kb_index:
            _enrich(kb_index[key], entity)
            resolved_pairs.append({
                "base": kb_index[key].name,
                "incoming": entity.name,
                "signals": ["exact_key"],
                "score": 1.0,
            })
            continue

        # Secondary fast path: same normalized name even when keys differ
        # (e.g. one has wikidataId and the other doesn't).
        name_key = f"name:{_strip_articles(normalize_key(entity.name))}"
        if key != name_key and name_key in kb_name_index:
            base = kb_name_index[name_key]
            _propagate_wikidata(base, entity)
            _enrich(base, entity)
            resolved_pairs.append({
                "base": base.name,
                "incoming": entity.name,
                "signals": ["name_key"],
                "score": 1.0,
            })
            continue

        best_score = 0.0
        best_candidate: Entity | None = None
        best_signals: list[str] = []

        for candidate in kb_list:
            score, signals = _resolution_score(candidate, entity)
            if score > best_score:
                best_score = score
                best_candidate = candidate
                best_signals = signals

        if best_candidate is not None and best_score >= threshold:
            _propagate_wikidata(best_candidate, entity)
            _enrich(best_candidate, entity)
            resolved_pairs.append({
                "base": best_candidate.name,
                "incoming": entity.name,
                "signals": best_signals,
                "score": round(best_score, 3),
            })
        else:
            kb_list.append(entity)
            kb_index[key] = entity
            added.append(entity.name)

    report = {
        "kb_total": len(kb_list),
        "added": len(added),
        "added_names": added,
        "enriched": len(resolved_pairs),
        "enriched_names": [p["incoming"] for p in resolved_pairs],
        "resolved_pairs": resolved_pairs,
    }
    return kb_list, report


def _resolution_score(base: Entity, incoming: Entity) -> tuple[float, list[str]]:
    if base.wikidataId and incoming.wikidataId and base.wikidataId == incoming.wikidataId:
        return 1.0, ["wikidata_id"]
    if base.wikidataId and incoming.wikidataId and base.wikidataId != incoming.wikidataId:
        return 0.0, ["barrier_different_wikidata_id"]

    if not _has_indubitable_name_match(base.name, incoming.name):
        return 0.0, ["barrier_name_not_indubitable"]

    score = 0.0
    signals: list[str] = ["indubitable_name_match"]

    if _both_have_coords(base, incoming):
        dist = _distance_km(
            base.coordinates.lat, base.coordinates.lng,
            incoming.coordinates.lat, incoming.coordinates.lng,
        )
        if dist > _BARRIER_KM:
            return 0.0, ["barrier_distance"]
        if dist <= _PROXIMITY_KM:
            score += 0.55
            signals.append("coordinates_proximity")

    base_addr = _normalize_address(base.address)
    inc_addr = _normalize_address(incoming.address)
    if base_addr and inc_addr and base_addr == inc_addr:
        score += 0.35
        signals.append("address_match")

    base_tokens = _significant_tokens(base.name)
    inc_tokens = _significant_tokens(incoming.name)
    if base_tokens and inc_tokens:
        longer = base_tokens if len(base_tokens) >= len(inc_tokens) else inc_tokens
        shorter = inc_tokens if longer is base_tokens else base_tokens
        shared = base_tokens & inc_tokens

        if len(shorter) >= 2 and shorter <= longer:
            score += 0.30
            signals.append("name_containment")
        elif shared:
            union = base_tokens | inc_tokens
            jaccard = len(shared) / len(union)
            if jaccard >= 0.50:
                score += 0.20
                signals.append(f"name_jaccard_{jaccard:.2f}")

    if base.types and incoming.types and base.types[0] == incoming.types[0]:
        score += 0.10
        signals.append("type_match")

    return score, signals


def _has_indubitable_name_match(base_name: str, incoming_name: str) -> bool:
    base_key = _strip_articles(normalize_key(base_name or ""))
    incoming_key = _strip_articles(normalize_key(incoming_name or ""))
    if not base_key or not incoming_key:
        return False
    if base_key == incoming_key:
        return True

    base_tokens = _significant_tokens(base_key)
    incoming_tokens = _significant_tokens(incoming_key)
    if not base_tokens or not incoming_tokens:
        return False
    longer = base_tokens if len(base_tokens) >= len(incoming_tokens) else incoming_tokens
    shorter = incoming_tokens if longer is base_tokens else base_tokens

    # A single-token alias such as "La Catedral" is not enough to enrich an
    # existing entity unless a shared external ID proves identity.
    if len(shorter) < 2:
        return False
    return shorter <= longer


def _both_have_coords(a: Entity, b: Entity) -> bool:
    return (
        a.coordinates.lat is not None and a.coordinates.lng is not None
        and b.coordinates.lat is not None and b.coordinates.lng is not None
    )


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _normalize_address(address: str) -> str:
    return normalize_key(address or "").strip()


def _strip_articles(text: str) -> str:
    words = text.split()
    while words and words[0] in {"el", "la", "los", "las", "un", "una", "the", "a", "an"}:
        words = words[1:]
    return " ".join(words)


def _significant_tokens(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", normalize_key(text or ""))
    return frozenset(
        t for t in tokens
        if len(t) >= _MIN_TOKEN_LEN and t not in _NAME_STOPWORDS
    )


def _propagate_wikidata(base: Entity, incoming: Entity) -> None:
    if base.wikidataId and not incoming.wikidataId:
        incoming.wikidataId = base.wikidataId
    elif incoming.wikidataId and not base.wikidataId:
        base.wikidataId = incoming.wikidataId
