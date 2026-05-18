from __future__ import annotations

import math
import re
from typing import Any

from .entity_merger import entity_key
from .knowledge_base import _enrich
from .models import Entity
from .text_utils import normalize_key


_DEFAULT_THRESHOLD = 0.75   # raised from 0.70 to reduce spurious enrichments
_BARRIER_KM = 5.0
_PROXIMITY_KM = 0.15   # 150 m

# Tokens shorter than this or in the stoplist are not significant for name matching
_MIN_TOKEN_LEN = 4
_NAME_STOPWORDS = {
    "de", "del", "la", "las", "los", "el", "en", "por", "the", "of",
    "para", "con", "que", "sus", "una", "uno",
}

# If there is zero name overlap between candidate and incoming entity, cap the
# score at this value so that coordinates/address alone cannot trigger a match.
_NO_NAME_OVERLAP_CAP = 0.50


def resolve_into_kb(
    kb_entities: list[Entity],
    new_entities: list[Entity],
    threshold: float = _DEFAULT_THRESHOLD,
) -> tuple[list[Entity], dict]:
    """Cross-page entity resolution with fuzzy matching.

    Replaces merge_into_kb for multi-page pipelines. Uses exact-key fast path
    first, then scores against all KB candidates using contextual signals.
    """
    kb_list: list[Entity] = list(kb_entities)
    kb_index: dict[str, Entity] = {entity_key(e): e for e in kb_list}

    added: list[str] = []
    resolved_pairs: list[dict[str, Any]] = []

    for entity in new_entities:
        key = entity_key(entity)

        # Fast path: exact key (wikidataId or exact normalized name)
        if key in kb_index:
            _enrich(kb_index[key], entity)
            resolved_pairs.append({
                "base": kb_index[key].name,
                "incoming": entity.name,
                "signals": ["exact_key"],
                "score": 1.0,
            })
            continue

        # Slow path: score against all KB candidates
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


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _resolution_score(base: Entity, incoming: Entity) -> tuple[float, list[str]]:
    # Definitive: same non-empty wikidataId
    if base.wikidataId and incoming.wikidataId and base.wikidataId == incoming.wikidataId:
        return 1.0, ["wikidata_id"]

    score = 0.0
    signals: list[str] = []

    # Barrier: both have coordinates and they are far apart
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

    # Address match
    base_addr = _normalize_address(base.address)
    inc_addr = _normalize_address(incoming.address)
    if base_addr and inc_addr and base_addr == inc_addr:
        score += 0.35
        signals.append("address_match")

    # Name signals
    base_tokens = _significant_tokens(base.name)
    inc_tokens = _significant_tokens(incoming.name)

    has_name_overlap = False
    if base_tokens and inc_tokens:
        longer = base_tokens if len(base_tokens) >= len(inc_tokens) else inc_tokens
        shorter = inc_tokens if longer is base_tokens else base_tokens
        shared = base_tokens & inc_tokens

        if shared:
            has_name_overlap = True

        # Containment: shorter must have ≥ 2 tokens and be fully contained in longer.
        # A single shared token (e.g. "catedral") is too weak to confirm identity.
        if len(shorter) >= 2 and len(longer) >= 2 and shorter <= longer:
            score += 0.30
            signals.append("name_containment")
        elif shared:
            # Jaccard similarity
            union = base_tokens | inc_tokens
            jaccard = len(shared) / len(union)
            if jaccard >= 0.50:
                score += 0.20
                signals.append(f"name_jaccard_{jaccard:.2f}")

    # Barrier: no name overlap → cap score so that coordinates/address alone
    # cannot merge two entities with completely different names.
    if not has_name_overlap and score > _NO_NAME_OVERLAP_CAP:
        return _NO_NAME_OVERLAP_CAP, signals + ["capped_no_name_overlap"]

    # Shared primary type
    if base.types and incoming.types and base.types[0] == incoming.types[0]:
        score += 0.10
        signals.append("type_match")

    return score, signals


def _both_have_coords(a: Entity, b: Entity) -> bool:
    return (
        a.coordinates.lat is not None and a.coordinates.lng is not None
        and b.coordinates.lat is not None and b.coordinates.lng is not None
    )


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _normalize_address(address: str) -> str:
    return normalize_key(address or "").strip()


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
