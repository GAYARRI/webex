from __future__ import annotations

import atexit
import json
import math
import re
import time
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .models import Coordinates, Entity, Evidence, PageExtraction
from .text_utils import compact_text


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIMEDIA_FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
WIKIPEDIA_SUMMARY_URL = "https://{language}.wikipedia.org/api/rest_v1/page/summary/{title}"
NOMINATIM_MIN_INTERVAL_SECONDS = 1.1
NOMINATIM_MIN_CONFIDENCE = 0.05
_GEOCODE_CACHE: dict[str, tuple[Coordinates, dict[str, Any]] | None] = {}
_WIKIDATA_CACHE: dict[str, tuple[Coordinates, str] | None] = {}
_WIKIDATA_DATA_CACHE: dict[str, dict | None] = {}
_WIKIPEDIA_SUMMARY_CACHE: dict[tuple[str, str], dict[str, str] | None] = {}
_LAST_NOMINATIM_REQUEST = 0.0

# ---------------------------------------------------------------------------
# Disk cache — persists Wikidata, Wikipedia and Nominatim results across runs
# ---------------------------------------------------------------------------

_DISK_CACHE_PATH = Path(__file__).parent.parent / ".cache" / "geo_cache.json"
_disk_cache: dict[str, dict] = {}


def _load_disk_cache() -> None:
    global _disk_cache
    try:
        if _DISK_CACHE_PATH.exists():
            _disk_cache = json.loads(_DISK_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _disk_cache = {}


def _save_disk_cache() -> None:
    try:
        _DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DISK_CACHE_PATH.write_text(
            json.dumps(_disk_cache, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


_load_disk_cache()
atexit.register(_save_disk_cache)


def extract_structured_data(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            items.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                items.extend(item for item in graph if isinstance(item, dict))
            items.append(parsed)
    return items


def extract_geo_candidates(soup: BeautifulSoup, structured_data: list[dict[str, Any]]) -> list[Coordinates]:
    candidates: list[Coordinates] = []
    candidates.extend(_geo_from_structured_data(structured_data))
    candidates.extend(_geo_from_meta(soup))
    candidates.extend(_geo_from_text(str(soup)))
    return _unique_coordinates(candidates)


def enrich_entity_coordinates(
    entity: Entity,
    page: PageExtraction,
    geocode: bool = False,
    timeout: int = 12,
) -> Entity:
    if entity.coordinates.lat is not None and entity.coordinates.lng is not None:
        if not entity.coordinates.source:
            entity.coordinates.source = "entity"
        return entity

    if page.geo_candidates:
        best = max(page.geo_candidates, key=lambda c: c.confidence or 0)
        # Use the best candidate directly if it has high confidence (e.g. json-ld, meta)
        if best.confidence is not None and best.confidence >= 0.7:
            entity.coordinates = Coordinates(
                lat=best.lat,
                lng=best.lng,
                source=best.source or "page",
                confidence=best.confidence,
            )
            return entity
        # Fall back to the single-candidate behaviour for low-confidence page data
        if len(page.geo_candidates) == 1:
            entity.coordinates = Coordinates(
                lat=best.lat,
                lng=best.lng,
                source=best.source or "page",
                confidence=best.confidence or 0.65,
            )
            return entity

    if geocode:
        wikidata_candidate = wikidata_coordinates(entity, page, timeout=timeout)
        if wikidata_candidate:
            candidate, qid = wikidata_candidate
            entity.coordinates = candidate
            if not entity.wikidataId:
                entity.wikidataId = qid
            _add_wikidata_evidence(entity, qid, candidate, timeout=timeout)
        else:
            geocode_result = geocode_entity(entity, page, timeout=timeout)
            if geocode_result:
                candidate, metadata = geocode_result
                entity.coordinates = candidate
                if not entity.address and metadata.get("address"):
                    entity.address = str(metadata["address"])
                _add_openstreetmap_evidence(entity, candidate, page, metadata=metadata)
    return entity


def wikidata_coordinates(
    entity: Entity,
    page: PageExtraction,
    timeout: int = 12,
) -> tuple[Coordinates, str] | None:
    city_context = _city_context(page)
    qids = [entity.wikidataId] if entity.wikidataId else _wikidata_search(entity.name, timeout=timeout)
    for qid in qids:
        if not qid:
            continue
        candidate = _wikidata_entity_coordinates(qid, city_context=city_context, timeout=timeout)
        if candidate:
            return candidate, qid
    return None


def _wikidata_search(name: str, timeout: int = 12) -> list[str]:
    queries = [_ascii_query(name), name]
    qids: list[str] = []
    for query in queries:
        if not query:
            continue
        cache_key = f"search:{query}"
        if cache_key in _WIKIDATA_CACHE:
            cached = _WIKIDATA_CACHE[cache_key]
            if cached:
                qids.append(cached[1])
            continue
        try:
            response = requests.get(
                WIKIDATA_SEARCH_URL,
                params={
                    "action": "wbsearchentities",
                    "search": query,
                    "language": "es",
                    "format": "json",
                    "limit": 3,
                },
                headers={"User-Agent": "ExtraccionWebSemantica/0.1"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            _WIKIDATA_CACHE[cache_key] = None
            continue
        for item in data.get("search", []):
            qid = item.get("id")
            if qid and qid not in qids:
                qids.append(qid)
    return qids[:5]


def _fetch_wikidata_entity(qid: str, timeout: int = 12) -> dict | None:
    if qid in _WIKIDATA_DATA_CACHE:
        return _WIKIDATA_DATA_CACHE[qid]
    disk_section = _disk_cache.get("wikidata_entities", {})
    if qid in disk_section:
        _WIKIDATA_DATA_CACHE[qid] = disk_section[qid]
        return disk_section[qid]
    try:
        response = requests.get(
            WIKIDATA_ENTITY_URL.format(qid=qid),
            headers={"User-Agent": "ExtraccionWebSemantica/0.1"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()["entities"][qid]
    except Exception:
        _WIKIDATA_DATA_CACHE[qid] = None
        return None
    _WIKIDATA_DATA_CACHE[qid] = data
    _disk_cache.setdefault("wikidata_entities", {})[qid] = data
    return data


def _wikidata_entity_coordinates(
    qid: str,
    city_context: dict[str, float | str] | None = None,
    timeout: int = 12,
) -> Coordinates | None:
    cache_key = f"entity:{qid}|{city_context.get('name') if city_context else ''}"
    if cache_key in _WIKIDATA_CACHE:
        cached = _WIKIDATA_CACHE[cache_key]
        return cached[0] if cached else None
    data = _fetch_wikidata_entity(qid, timeout=timeout)
    if data is None:
        _WIKIDATA_CACHE[cache_key] = None
        return None
    for claim in data.get("claims", {}).get("P625", []):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            lat = float(value["latitude"])
            lng = float(value["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if city_context and not _is_near_city(lat, lng, city_context):
            continue
        coord = Coordinates(lat=lat, lng=lng, source="wikidata", confidence=0.85)
        _WIKIDATA_CACHE[cache_key] = (coord, qid)
        return coord
    _WIKIDATA_CACHE[cache_key] = None
    return None


def wikidata_images_for_entity(entity: Entity, timeout: int = 12) -> list[str]:
    if not entity.wikidataId:
        return []
    data = _fetch_wikidata_entity(entity.wikidataId, timeout=timeout)
    if data is None:
        return []
    urls: list[str] = []
    for claim in data.get("claims", {}).get("P18", []):
        try:
            filename: str = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if not filename:
            continue
        safe = quote(filename.replace(" ", "_"), safe="")
        urls.append(WIKIMEDIA_FILE_URL.format(filename=safe))
    return urls


def enrich_entities_wikidata_images(
    entities: list[Entity],
    timeout: int = 12,
) -> list[Entity]:
    for entity in entities:
        if not entity.wikidataId:
            continue
        wd_images = wikidata_images_for_entity(entity, timeout=timeout)
        if not wd_images:
            continue
        existing = [img for img in entity.images if img not in wd_images]
        entity.images = [*wd_images, *existing]
        _add_wikidata_evidence(entity, entity.wikidataId, entity.coordinates, images=wd_images, timeout=timeout)
    return entities


WIKIMEDIA_COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
_COMMONS_GEOSEARCH_CACHE: dict[tuple[float, float], list[str]] = {}


def _wikimedia_commons_geosearch(lat: float, lng: float, radius_m: int = 200, limit: int = 5, timeout: int = 10) -> list[str]:
    cache_key = (round(lat, 5), round(lng, 5))
    if cache_key in _COMMONS_GEOSEARCH_CACHE:
        return _COMMONS_GEOSEARCH_CACHE[cache_key]
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lng}",
        "gsradius": radius_m,
        "gslimit": limit,
        "gsnamespace": 6,
        "format": "json",
    }
    try:
        resp = requests.get(
            WIKIMEDIA_COMMONS_API_URL,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "ExtraccionWeb/1.0 (tourism-kb)"},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("geosearch", [])
        urls: list[str] = []
        for item in results:
            title = item.get("title", "")
            if title.startswith("File:"):
                filename = quote(title[5:].replace(" ", "_"), safe="")
                urls.append(WIKIMEDIA_FILE_URL.format(filename=filename))
        _COMMONS_GEOSEARCH_CACHE[cache_key] = urls
        return urls
    except Exception:
        _COMMONS_GEOSEARCH_CACHE[cache_key] = []
        return []


def enrich_entities_geosearch_images(entities: list[Entity], timeout: int = 10) -> list[Entity]:
    """Level-3 fallback: assign Wikimedia Commons images by coordinates for entities still without images."""
    for entity in entities:
        if entity.images:
            continue
        if entity.coordinates.lat is None or entity.coordinates.lng is None:
            continue
        urls = _wikimedia_commons_geosearch(entity.coordinates.lat, entity.coordinates.lng, timeout=timeout)
        if urls:
            entity.images = urls
    return entities


def enrich_entities_external_context(
    entities: list[Entity],
    page: PageExtraction,
    timeout: int = 12,
    include_osm_lookup: bool = False,
) -> list[Entity]:
    for entity in entities:
        if entity.wikidataId:
            _add_wikidata_evidence(entity, entity.wikidataId, entity.coordinates, timeout=timeout)
            _add_wikipedia_evidence(entity, entity.wikidataId, timeout=timeout)
        if include_osm_lookup and entity.coordinates.lat is not None and not _has_source(entity, "openstreetmap"):
            geocode_result = geocode_entity(entity, page, timeout=timeout)
            if geocode_result:
                candidate, metadata = geocode_result
                _add_openstreetmap_evidence(entity, candidate, page, metadata=metadata)
    return entities


def _extract_p31_qids(data: dict | None) -> list[str]:
    """Return Wikidata 'instance of' (P31) QIDs from a fetched entity dict."""
    if not data:
        return []
    qids: list[str] = []
    for claim in data.get("claims", {}).get("P31", []):
        try:
            qid = claim["mainsnak"]["datavalue"]["value"]["id"]
            if qid:
                qids.append(qid)
        except (KeyError, TypeError):
            continue
    return qids


def _add_wikidata_evidence(
    entity: Entity,
    qid: str,
    coordinates: Coordinates | None = None,
    images: list[str] | None = None,
    timeout: int = 12,
) -> None:
    data = _fetch_wikidata_entity(qid, timeout=timeout)
    text = _wikidata_text(data) if data else ""
    p31_qids = _extract_p31_qids(data)
    evidence = Evidence(
        url=f"https://www.wikidata.org/wiki/{qid}",
        block_id=qid,
        source_type="wikidata",
        title=qid,
        text=text,
        images=images or wikidata_images_for_entity(entity, timeout=timeout),
        coordinates=coordinates if coordinates and coordinates.lat is not None else None,
        metadata={"wikidataId": qid, "p31_qids": p31_qids},
    )
    _append_evidence(entity, evidence)


def _wikidata_text(data: dict | None) -> str:
    if not data:
        return ""
    labels = data.get("labels", {})
    descriptions = data.get("descriptions", {})
    aliases = data.get("aliases", {})
    label = _language_value(labels, ["es", "en"])
    description = _language_value(descriptions, ["es", "en"])
    alias_values = []
    for lang in ["es", "en"]:
        for item in aliases.get(lang, [])[:5]:
            value = item.get("value")
            if value:
                alias_values.append(value)
    parts = [part for part in [label, description] if part]
    if alias_values:
        parts.append("Alias: " + ", ".join(alias_values))
    return compact_text(". ".join(parts))


def _add_wikipedia_evidence(entity: Entity, qid: str, timeout: int = 12) -> None:
    data = _fetch_wikidata_entity(qid, timeout=timeout)
    summary = _wikipedia_summary_from_wikidata(data, timeout=timeout)
    if not summary:
        return
    evidence = Evidence(
        url=summary["url"],
        block_id=qid,
        source_type="wikipedia",
        title=summary["title"],
        text=summary["extract"],
        images=[summary["image"]] if summary.get("image") else [],
        metadata={"wikidataId": qid, "language": summary["language"]},
    )
    _append_evidence(entity, evidence)


def _wikipedia_summary_from_wikidata(data: dict | None, timeout: int = 12) -> dict[str, str] | None:
    if not data:
        return None
    sitelinks = data.get("sitelinks", {})
    for language, site_key in [("es", "eswiki"), ("en", "enwiki")]:
        site = sitelinks.get(site_key)
        title = site.get("title") if isinstance(site, dict) else ""
        if not title:
            continue
        summary = _fetch_wikipedia_summary(language, str(title), timeout=timeout)
        if summary:
            return summary
    return None


def _fetch_wikipedia_summary(language: str, title: str, timeout: int = 12) -> dict[str, str] | None:
    cache_key = (language, title)
    if cache_key in _WIKIPEDIA_SUMMARY_CACHE:
        return _WIKIPEDIA_SUMMARY_CACHE[cache_key]
    disk_key = f"{language}:{title}"
    disk_section = _disk_cache.get("wikipedia_summaries", {})
    if disk_key in disk_section:
        result = disk_section[disk_key]
        _WIKIPEDIA_SUMMARY_CACHE[cache_key] = result
        return result
    try:
        response = requests.get(
            WIKIPEDIA_SUMMARY_URL.format(language=language, title=quote(title.replace(" ", "_"), safe="")),
            headers={"User-Agent": "ExtraccionWebSemantica/0.1"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        _WIKIPEDIA_SUMMARY_CACHE[cache_key] = None
        return None
    extract = compact_text(str(data.get("extract") or ""))
    if not extract:
        _WIKIPEDIA_SUMMARY_CACHE[cache_key] = None
        return None
    thumbnail = data.get("thumbnail")
    image = ""
    if isinstance(thumbnail, dict):
        image = str(thumbnail.get("source") or "")
    result = {
        "language": language,
        "title": str(data.get("title") or title),
        "extract": extract,
        "url": str(data.get("content_urls", {}).get("desktop", {}).get("page") or ""),
        "image": image,
    }
    if not result["url"]:
        result["url"] = f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"
    _WIKIPEDIA_SUMMARY_CACHE[cache_key] = result
    _disk_cache.setdefault("wikipedia_summaries", {})[disk_key] = result
    return result


def _language_value(values: dict, languages: list[str]) -> str:
    for lang in languages:
        item = values.get(lang)
        if isinstance(item, dict) and item.get("value"):
            return str(item["value"])
    return ""


def _add_openstreetmap_evidence(
    entity: Entity,
    coordinates: Coordinates,
    page: PageExtraction,
    metadata: dict[str, Any] | None = None,
) -> None:
    metadata = metadata or {}
    query = compact_text(", ".join(part for part in [entity.name, _city_hint(page), "Spain"] if part))
    display_name = str(metadata.get("display_name") or "")
    evidence = Evidence(
        url=f"https://www.openstreetmap.org/search?query={quote(query)}" if query else "https://www.openstreetmap.org/",
        block_id=entity.name,
        source_type="openstreetmap",
        title="OpenStreetMap / Nominatim",
        text=compact_text(display_name or f"Resultado de geocodificacion para {query}."),
        images=[],
        coordinates=coordinates,
        metadata={
            **metadata,
            "query": query,
            "source": coordinates.source,
            "confidence": coordinates.confidence,
        },
    )
    _append_evidence(entity, evidence)


def _append_evidence(entity: Entity, evidence: Evidence) -> None:
    key = (evidence.url, evidence.block_id, evidence.source_type)
    existing = {(item.url, item.block_id, item.source_type) for item in entity.sources}
    if key not in existing:
        entity.sources.append(evidence)


def _has_source(entity: Entity, source_type: str) -> bool:
    return any(source.source_type == source_type for source in entity.sources)


def geocode_entity(entity: Entity, page: PageExtraction, timeout: int = 12) -> tuple[Coordinates, dict[str, Any]] | None:
    city_context = _city_context(page)
    for query in _build_geocode_queries(entity, page):
        candidate = _geocode_query(query, city_context=city_context, timeout=timeout)
        if candidate:
            return candidate
    return None


def enrich_entities_coordinates(
    entities: list[Entity],
    page: PageExtraction,
    geocode: bool = False,
) -> list[Entity]:
    return [enrich_entity_coordinates(entity, page, geocode=geocode) for entity in entities]


def _geocode_query(
    query: str,
    city_context: dict[str, float | str] | None = None,
    timeout: int = 12,
) -> tuple[Coordinates, dict[str, Any]] | None:
    global _LAST_NOMINATIM_REQUEST
    cache_key = f"{query}|{city_context.get('name') if city_context else ''}"
    if cache_key in _GEOCODE_CACHE:
        cached = _GEOCODE_CACHE[cache_key]
        if cached is None:
            return None
        cached_coord, cached_metadata = cached
        coord = Coordinates(
            lat=cached_coord.lat,
            lng=cached_coord.lng,
            source=cached_coord.source,
            confidence=cached_coord.confidence,
        )
        return coord, dict(cached_metadata)
    disk_section = _disk_cache.get("nominatim", {})
    if cache_key in disk_section:
        entry = disk_section[cache_key]
        if entry is None:
            _GEOCODE_CACHE[cache_key] = None
            return None
        coord = Coordinates(**entry["coord"])
        _GEOCODE_CACHE[cache_key] = (coord, entry["metadata"])
        return coord, dict(entry["metadata"])

    elapsed = time.monotonic() - _LAST_NOMINATIM_REQUEST
    if elapsed < NOMINATIM_MIN_INTERVAL_SECONDS:
        time.sleep(NOMINATIM_MIN_INTERVAL_SECONDS - elapsed)

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 1},
            headers={"User-Agent": "ExtraccionWebSemantica/0.1"},
            timeout=timeout,
        )
        _LAST_NOMINATIM_REQUEST = time.monotonic()
        response.raise_for_status()
        data = response.json()
    except Exception:
        _GEOCODE_CACHE[cache_key] = None
        return None
    for item in data:
        try:
            lat = float(item["lat"])
            lng = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if city_context and not _is_near_city(lat, lng, city_context):
            continue
        importance = item.get("importance")
        confidence = float(importance) if isinstance(importance, int | float) else 0.6
        if confidence < NOMINATIM_MIN_CONFIDENCE:
            continue
        coord = Coordinates(lat=lat, lng=lng, source="openstreetmap", confidence=confidence)
        expected_city = str(city_context["name"]) if city_context else ""
        metadata = _nominatim_metadata(item, expected_city=expected_city)
        _GEOCODE_CACHE[cache_key] = (coord, metadata)
        _disk_cache.setdefault("nominatim", {})[cache_key] = {"coord": asdict(coord), "metadata": metadata}
        return coord, metadata
    _GEOCODE_CACHE[cache_key] = None
    _disk_cache.setdefault("nominatim", {})[cache_key] = None
    return None


def _nominatim_metadata(item: dict[str, Any], expected_city: str = "") -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ["osm_type", "osm_id", "category", "type", "display_name", "importance"]:
        if key in item and item[key] not in (None, ""):
            metadata[key] = item[key]
    address = item.get("address")
    if isinstance(address, dict):
        metadata["address_parts"] = address
        formatted = _format_nominatim_address(address, expected_city=expected_city)
        if formatted:
            metadata["address"] = formatted
    elif item.get("display_name"):
        metadata["address"] = str(item["display_name"])
    return metadata


def _format_nominatim_address(address: dict[str, Any], expected_city: str = "") -> str:
    road = address.get("road") or address.get("pedestrian") or address.get("footway")
    house_number = address.get("house_number")
    city = address.get("city") or address.get("town") or address.get("village")
    postcode = address.get("postcode")
    if expected_city and city:
        expected_key = _ascii_query(expected_city.casefold())
        city_key = _ascii_query(city.casefold())
        if expected_key not in city_key and city_key not in expected_key:
            return ""
    parts = [
        compact_text(" ".join(str(part) for part in [road, house_number] if part)),
        str(postcode or ""),
        str(city or ""),
    ]
    return compact_text(", ".join(part for part in parts if part))


def _build_geocode_queries(entity: Entity, page: PageExtraction) -> list[str]:
    city_hint = _city_hint(page)
    address = entity.address if entity.address and len(entity.address.split()) <= 10 else ""
    queries = [
        compact_text(", ".join(part for part in [entity.name, address] if part)),
        compact_text(", ".join(part for part in [entity.name, city_hint, "Spain"] if part)),
        compact_text(entity.name),
    ]
    unique: list[str] = []
    for query in queries:
        query = _ascii_query(query)
        if query and query not in unique:
            unique.append(query)
    return unique


CITY_CENTERS: dict[str, dict[str, float | str]] = {
    "avila": {"name": "Ávila", "lat": 40.65660, "lng": -4.70024, "radius_km": 20.0},
    "barcelona": {"name": "Barcelona", "lat": 41.38879, "lng": 2.15899, "radius_km": 40.0},
    "bilbao": {"name": "Bilbao", "lat": 43.26300, "lng": -2.93500, "radius_km": 30.0},
    "burgos": {"name": "Burgos", "lat": 42.34399, "lng": -3.69691, "radius_km": 25.0},
    "cadiz": {"name": "Cádiz", "lat": 36.52700, "lng": -6.28850, "radius_km": 25.0},
    "cordoba": {"name": "Córdoba", "lat": 37.88839, "lng": -4.77938, "radius_km": 30.0},
    "girona": {"name": "Girona", "lat": 41.98311, "lng": 2.82493, "radius_km": 20.0},
    "granada": {"name": "Granada", "lat": 37.17604, "lng": -3.58881, "radius_km": 30.0},
    "leon": {"name": "León", "lat": 42.59873, "lng": -5.57028, "radius_km": 25.0},
    "madrid": {"name": "Madrid", "lat": 40.41650, "lng": -3.70256, "radius_km": 40.0},
    "malaga": {"name": "Málaga", "lat": 36.72016, "lng": -4.42034, "radius_km": 30.0},
    "pamplona": {"name": "Pamplona", "lat": 42.81272, "lng": -1.64323, "radius_km": 20.0},
    "salamanca": {"name": "Salamanca", "lat": 40.96527, "lng": -5.66362, "radius_km": 25.0},
    "san sebastian": {"name": "San Sebastián", "lat": 43.31828, "lng": -1.98143, "radius_km": 25.0},
    "santander": {"name": "Santander", "lat": 43.46472, "lng": -3.80444, "radius_km": 25.0},
    "santiago de compostela": {"name": "Santiago de Compostela", "lat": 42.87854, "lng": -8.54451, "radius_km": 20.0},
    "segovia": {"name": "Segovia", "lat": 40.94803, "lng": -4.11839, "radius_km": 20.0},
    "sevilla": {"name": "Sevilla", "lat": 37.38909, "lng": -5.98446, "radius_km": 35.0},
    "toledo": {"name": "Toledo", "lat": 39.86283, "lng": -4.02732, "radius_km": 25.0},
    "valencia": {"name": "Valencia", "lat": 39.46990, "lng": -0.37630, "radius_km": 35.0},
    "valladolid": {"name": "Valladolid", "lat": 41.65225, "lng": -4.72453, "radius_km": 35.0},
    "zaragoza": {"name": "Zaragoza", "lat": 41.65606, "lng": -0.87734, "radius_km": 35.0},
}


def _city_from_structured_data(structured_data: list[dict]) -> str:
    for item in structured_data:
        address = item.get("address")
        if isinstance(address, dict):
            city = str(address.get("addressLocality") or "").strip()
            if city:
                return city
        city = str(item.get("addressLocality") or "").strip()
        if city:
            return city
    return ""


def _city_hint(page: PageExtraction) -> str:
    # Priority 1: JSON-LD structured data (most reliable)
    city = _city_from_structured_data(page.structured_data)
    if city:
        return city

    # Priority 2: URL, title and description text match against known cities
    text = " ".join(part for part in [page.url, page.title or "", page.description or ""] if part)
    lowered = text.casefold()
    for city_key in CITY_CENTERS:
        if city_key in lowered:
            return str(CITY_CENTERS[city_key]["name"])
    return ""


def _city_context(page: PageExtraction) -> dict[str, float | str] | None:
    city = _city_hint(page)
    if not city:
        return None
    key = unicodedata.normalize("NFKD", city.casefold())
    key = "".join(char for char in key if not unicodedata.combining(char))
    return CITY_CENTERS.get(key)


def _is_near_city(lat: float, lng: float, city_context: dict[str, float | str]) -> bool:
    distance = _distance_km(
        lat,
        lng,
        float(city_context["lat"]),
        float(city_context["lng"]),
    )
    return distance <= float(city_context["radius_km"])


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _ascii_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKD", query)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _geo_from_structured_data(items: list[dict[str, Any]]) -> list[Coordinates]:
    candidates: list[Coordinates] = []
    for item in items:
        geo = item.get("geo")
        if isinstance(geo, dict):
            coord = _coordinate_from_values(geo.get("latitude"), geo.get("longitude"), "json-ld", 0.9)
            if coord:
                candidates.append(coord)
        candidates.extend(_geo_from_structured_data(_child_dicts(item)))
    return candidates


def _child_dicts(item: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for value in item.values():
        if isinstance(value, dict):
            children.append(value)
        elif isinstance(value, list):
            children.extend(child for child in value if isinstance(child, dict))
    return children


def _geo_from_meta(soup: BeautifulSoup) -> list[Coordinates]:
    candidates: list[Coordinates] = []
    lat = _meta_value(soup, ["place:location:latitude", "geo.position:lat", "latitude"])
    lng = _meta_value(soup, ["place:location:longitude", "geo.position:long", "longitude"])
    coord = _coordinate_from_values(lat, lng, "meta", 0.8)
    if coord:
        candidates.append(coord)

    position = _meta_value(soup, ["geo.position", "ICBM"])
    if position:
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)", position)
        if match:
            coord = _coordinate_from_values(match.group(1), match.group(2), "meta", 0.8)
            if coord:
                candidates.append(coord)
    return candidates


def _meta_value(soup: BeautifulSoup, names: list[str]) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return str(tag["content"])
    return None


def _geo_from_text(text: str) -> list[Coordinates]:
    patterns = [
        r'"(?:lat|latitude)"\s*:\s*(-?\d+(?:\.\d+)?).*?"(?:lng|lon|longitude)"\s*:\s*(-?\d+(?:\.\d+)?)',
        r"(?:lat|latitude)\s*[=:]\s*(-?\d+(?:\.\d+)?).*?(?:lng|lon|longitude)\s*[=:]\s*(-?\d+(?:\.\d+)?)",
    ]
    candidates: list[Coordinates] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            coord = _coordinate_from_values(match.group(1), match.group(2), "page-pattern", 0.7)
            if coord:
                candidates.append(coord)
    return candidates


def _coordinate_from_values(
    lat_value: Any,
    lng_value: Any,
    source: str,
    confidence: float,
) -> Coordinates | None:
    try:
        lat = float(lat_value)
        lng = float(lng_value)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return Coordinates(lat=lat, lng=lng, source=source, confidence=confidence)


def _unique_coordinates(candidates: list[Coordinates]) -> list[Coordinates]:
    seen: set[tuple[float | None, float | None]] = set()
    unique: list[Coordinates] = []
    for candidate in candidates:
        key = (candidate.lat, candidate.lng)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique
