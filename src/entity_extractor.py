from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any

from .ai_client import TOURIST_TYPES, ai_available, extract_entities_with_ai
from .entity_text import relevant_text_for_entity
from .image_filters import is_image_url
from .images import is_image_relevant_to_entity_url
from .models import Coordinates, Entity, PageExtraction
from .text_utils import normalize_key


SCHEMA_TO_TOURIST_TYPE: dict[str, str] = {
    "TouristAttraction": "TouristAttractionSite",
    "Museum": "Museum",
    "Church": "Church",
    "LandmarksOrHistoricalBuildings": "HistoricalOrCulturalResource",
    "HistoricBuilding": "HistoricalOrCulturalResource",
    "CivicStructure": "Monument",
    "GovernmentBuilding": "Monument",
    "LocalBusiness": "FoodEstablishment",
    "FoodEstablishment": "FoodEstablishment",
    "Restaurant": "Restaurant",
    "CafeOrCoffeeShop": "CafeOrCoffeShop",
    "BarOrPub": "Bar",
    "Hotel": "Hotel",
    "Lodging": "AccommodationEstablishment",
    "Hostel": "Hostel",
    "BedAndBreakfast": "GuestHouse",
    "PerformingArtsTheater": "Theater",
    "MovieTheater": "MovieTheater",
    "ArtGallery": "ArtGallery",
    "Park": "NaturalPark",
    "Event": "Event",
    "MusicEvent": "Event",
    "ExhibitionEvent": "Event",
    "Festival": "Event",
    "TheaterEvent": "Event",
    "NightClub": "NightClub",
    "TouristInformationCenter": "TouristAttractionSite",
    "Library": "Library",
    "Aquarium": "Aquarium",
    "Zoo": "Zoo",
    "Winery": "Winery",
}


def extract_entities(page: PageExtraction, use_ai: bool = True, model: str | None = None) -> list[Entity]:
    if page.status != "ok":
        return []

    structured_entities = entities_from_structured_data(page)
    block_entities = entities_from_blocks(page)

    if use_ai and ai_available():
        try:
            ai_entities = extract_entities_with_ai(page, model=model)
        except Exception:
            ai_entities = []
    else:
        ai_entities = heuristic_entities(page)

    # Structured data entities go first: merge_entities() will deduplicate by key
    return clean_entities([*structured_entities, *block_entities, *ai_entities], page)


def clean_entities(entities: list[Entity], page: PageExtraction) -> list[Entity]:
    cleaned: list[Entity] = []
    for entity in entities:
        _normalize_entity(entity, page)
        if _is_valid_entity(entity, page):
            cleaned.append(entity)
    return cleaned


def classify_entities(entities: list[Entity]) -> list[Entity]:
    """Final ontology classification after all evidence has been accumulated."""
    for entity in entities:
        primary, types, evidence = _classify_entity(entity)
        entity.type = primary
        entity.types = types
        entity.classificationEvidence = evidence
    return entities


def entities_from_structured_data(page: PageExtraction) -> list[Entity]:
    entities: list[Entity] = []
    for item in page.structured_data:
        entity = _entity_from_schema_item(item, page.url)
        if entity:
            entities.append(entity)
    return entities


def entities_from_blocks(page: PageExtraction) -> list[Entity]:
    entities: list[Entity] = []
    for block in page.blocks:
        name = _block_entity_name(block.title, block.text)
        if not name:
            continue
        relevant_text = relevant_text_for_entity(name, block.text)
        entity = Entity(
            name=name,
            score=0.45,
            sourceUrl=page.url,
            url="",
            shortDescription=relevant_text[:300],
            longDescription=relevant_text[:1200],
            sourceText=relevant_text,
            description=relevant_text[:1200],
            images=[],
            evidence=relevant_text[:300] or name,
        )
        entity.images = [
            item["url"]
            for item in block.images
            if item.get("url") and is_image_relevant_to_entity_url(item["url"], entity)
        ]
        _normalize_entity(entity, page)
        if _is_valid_entity(entity, page):
            entities.append(entity)
    return entities


def _entity_from_schema_item(item: dict[str, Any], source_url: str) -> Entity | None:
    schema_type = item.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = schema_type[0] if schema_type else ""

    tourist_type = SCHEMA_TO_TOURIST_TYPE.get(str(schema_type))
    if not tourist_type:
        return None

    name = _text(item.get("name"))
    if not name:
        return None

    address = _parse_address(item.get("address"))
    coordinates = _parse_geo(item.get("geo"))
    images = _parse_images(item.get("image"))
    description = _text(item.get("description", ""))
    url = _text(item.get("url", "")) or source_url
    phone = _text(item.get("telephone", ""))
    email = _text(item.get("email", ""))

    return Entity(
        name=name,
        types=[tourist_type],
        score=0.9,
        sourceUrl=source_url,
        url=url,
        address=address,
        phone=phone,
        email=email,
        coordinates=coordinates,
        shortDescription=description[:300] if description else "",
        longDescription=description,
        description=description,
        images=images,
        evidence=f"Extraido de structured data ({schema_type})",
    )


def _text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("@value") or value.get("name") or "").strip()
    return ""


def _parse_address(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts = [
            value.get("streetAddress", ""),
            value.get("postalCode", ""),
            value.get("addressLocality", ""),
            value.get("addressRegion", ""),
        ]
        return ", ".join(p for p in parts if p).strip(", ")
    return ""


def _parse_geo(value: Any) -> Coordinates:
    if not isinstance(value, dict):
        return Coordinates()
    try:
        lat = float(value.get("latitude") or 0)
        lng = float(value.get("longitude") or 0)
        if lat and lng and -90 <= lat <= 90 and -180 <= lng <= 180:
            return Coordinates(lat=lat, lng=lng, source="json-ld", confidence=0.95)
    except (TypeError, ValueError):
        pass
    return Coordinates()


def _parse_images(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl") or ""
        return [str(url)] if url else []
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_parse_images(item))
        return result
    return []


def heuristic_entities(page: PageExtraction) -> list[Entity]:
    return entities_from_blocks(page)


NAVIGATION_NAMES = {
    "inicio",
    "home",
    "que ver",
    "que hacer",
    "donde dormir",
    "dormir",
    "comer",
    "comprar",
    "agenda",
    "actualidad",
    "contacto",
    "descubre",
    "gastronomia",
    "mapa web",
    "buscar",
    "menu",
    "para tocar la catedral",
    "planifica tu viaje",
    "turismo",
    "turismo en familia",
    "descubre",
    "sumergete",
    "profesionales",
    "servicios",
    "blog",
    "noticias",
    "novedades",
    "informacion practica",
    "alojamientos",
    "area de profesionales",
    "noticias del sector",
    "datos api",
}


TYPE_KEYWORDS: list[tuple[str, str]] = [
    # HistoricalOrCulturalResource subtree
    ("catedral", "Cathedral"),
    ("iglesia", "Church"),
    ("basilica", "Basilica"),
    ("capilla", "Chapel"),
    ("monasterio", "Monastery"),
    ("convento", "Convent"),
    ("cartuja", "Monastery"),
    ("ermita", "Church"),
    ("santuario", "Sanctuary"),
    ("museo", "Museum"),
    ("archivo", "Museum"),
    ("biblioteca", "Library"),
    ("galeria de arte", "ArtGallery"),
    ("galeria", "ArtGallery"),
    ("sala de exposiciones", "ExhibitionHall"),
    ("centro cultural", "CultureCentre"),
    ("centro de arte", "ArtGallery"),
    ("castillo", "Castle"),
    ("alcazar", "Alcazar"),
    ("palacio", "Palace"),
    ("muralla", "Wall"),
    ("torre", "Tower"),
    ("arco", "Arch"),
    ("puente", "Bridge"),
    ("acueducto", "Aqueduct"),
    ("yacimiento", "ArcheologicalSite"),
    ("anfiteatro", "Amphitheatre"),
    ("plaza", "Square"),
    ("jardin", "Garden"),
    ("mirador urbano", "UrbanViewPoint"),
    ("mirador", "UrbanViewPoint"),
    ("monumento", "Monument"),
    ("teatro", "Theater"),
    ("auditorio", "Auditorium"),
    # NaturalResource subtree
    ("parque natural", "NaturalPark"),
    ("parque", "NaturalPark"),
    ("sendero", "Trail"),
    ("cueva", "Cave"),
    ("playa", "Beach"),
    ("montana", "Mountain"),
    ("valle", "Valley"),
    ("mirador natural", "NaturalViewPoint"),
    # Route
    ("ruta", "Route"),
    ("camino", "Route"),
    # Event
    ("festival", "Event"),
    ("semana santa", "Event"),
    ("concierto", "Event"),
    ("feria", "Event"),
    ("fiesta", "Event"),
    ("eclipse", "Event"),
    # TourismService
    ("visita guiada", "Tour"),
    ("pulsera turistica", "Tour"),
    ("experiencia", "DestinationExperience"),
    # TourismOrRelatedFacility (selected)
    ("hotel", "Hotel"),
    ("hostal", "Hostal"),
    ("albergue", "Hostel"),
    ("casa rural", "RuralHouse"),
    ("restaurante", "Restaurant"),
    ("cafeteria", "CafeOrCoffeShop"),
    ("bar", "Bar"),
    ("bodega", "Winery"),
    ("sala de conciertos", "MusicVenue"),
    ("centro de biodiversidad", "TouristAttractionSite"),
]


def _is_valid_address(address: str) -> bool:
    if not address:
        return False
    words = address.split()
    return len(words) <= 10 and len(address) <= 120


def _normalize_entity(entity: Entity, page: PageExtraction) -> None:
    entity.name = _clean_name(entity.name)
    entity.sourceUrl = entity.sourceUrl or page.url
    if not _is_valid_address(entity.address):
        entity.address = ""
    if entity.url and is_image_url(entity.url):
        entity.images = _dedupe([*entity.images, entity.url])
        entity.url = ""
    if entity.url == page.url:
        entity.url = ""
    related_urls = []
    for url in [*entity.relatedUrls, entity.url]:
        if not url:
            continue
        if is_image_url(url):
            entity.images = _dedupe([*entity.images, url])
            continue
        related_urls.append(url)
    entity.relatedUrls = _dedupe(related_urls)
    entity.images = _dedupe(entity.images)
    entity.types = _normalize_types(entity.types, entity)
    if not entity.shortDescription and entity.description:
        entity.shortDescription = entity.description[:300]
    if not entity.longDescription and entity.description:
        entity.longDescription = entity.description


def _clean_name(name: str) -> str:
    name = _text(name)
    for separator in ("|", " - "):
        if separator in name:
            parts = [part.strip() for part in name.split(separator) if part.strip()]
            if parts:
                name = min(parts, key=len)
    return name.strip(" \t\r\n-_/|")


def _block_entity_name(title: str, text: str) -> str:
    title = _clean_name(title)
    title_key = normalize_key(title)
    if title and title_key not in NAVIGATION_NAMES:
        return title

    text = _text(text)
    name = _name_after_date(text)
    if name:
        return name
    return ""


def _name_after_date(text: str) -> str:
    import re

    pattern = (
        r"^\s*\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s+de\s+\d{4}\s+"
        r"(.+?)(?=\s+(?:Con|En|El|La|Los|Las|Una|Un|Del|Durante|Toda|Descarga|DESCARGA|Burgos Film Commission)\s)"
    )
    match = re.search(pattern, text)
    if not match:
        return ""
    name = _clean_name(match.group(1))
    if len(normalize_key(name).split()) > 12:
        return ""
    if len(normalize_key(name).split()) < 2:
        return ""
    return name


def _normalize_types(types: list[str], entity: Entity, final: bool = False) -> list[str]:
    allowed = set(TOURIST_TYPES)
    normalized = [item for item in _dedupe(types) if item in allowed]
    inferred, confidence = _infer_type(entity)[:2]
    if final and inferred:
        # Very high confidence (name-based, >= 90): cleans up accumulated generic types.
        if confidence >= 90:
            return [inferred]
        if inferred in normalized:
            return normalized
        # Override requires confidence >= 60 (title + text from sources, not just
        # a single Wikipedia title). For entities with no type yet, a single strong
        # source title (>= 40) is enough to fill the gap.
        if confidence >= 60 or (not normalized and confidence >= 40):
            return [inferred]
    if normalized and inferred:
        if confidence >= 90:
            # Strong name-based inference wins: drop generic co-types (e.g. Monument+Church
            # when Cathedral is clearly inferred from the entity name).
            return [inferred]
        if inferred in normalized:
            return normalized
    if normalized:
        return normalized
    return [inferred] if inferred else []


def _classify_entity(entity: Entity) -> tuple[str, list[str], dict[str, Any]]:
    allowed = set(TOURIST_TYPES)
    existing = [item for item in _dedupe(entity.types) if item in allowed]
    inferred, confidence, signals = _infer_type(entity)
    primary = _select_primary_type(existing, inferred, confidence)
    related = _related_types(existing, primary, inferred)
    evidence = {
        "selected": primary,
        "confidence": confidence,
        "signals": signals,
        "candidates": related,
    }
    return primary, related, evidence


def _select_primary_type(existing: list[str], inferred: str, confidence: int) -> str:
    if inferred:
        if confidence >= 60 or not existing or inferred in existing:
            return inferred
    return existing[0] if existing else inferred


def _related_types(existing: list[str], primary: str, inferred: str) -> list[str]:
    result: list[str] = []
    for item in [primary, inferred, *existing]:
        if item and item not in result:
            result.append(item)
    return result


def _infer_type(entity: Entity, name_only: bool = False) -> tuple[str, int, list[str]]:
    # Page-scraped description fields (shortDescription, description, etc.) are excluded
    # because they reflect page context, not the entity itself.
    override = _name_primary_type(entity.name)
    if override:
        return override, 110, [f"name_primary:{override}"]

    contexts: list[tuple[str, int]] = [(entity.name, 100)]
    if not name_only:
        for source in entity.sources:
            if source.source_type in {"wikidata", "wikipedia"}:
                contexts.append((source.title, 40))
                contexts.append((source.text, 20))
    scores: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    signals_by_type: dict[str, list[str]] = {}
    for order, (keyword, tourist_type) in enumerate(TYPE_KEYWORDS):
        keyword_key = normalize_key(keyword)
        for text, weight in contexts:
            if _contains_keyword(normalize_key(text), keyword_key):
                scores[tourist_type] = scores.get(tourist_type, 0) + weight
                first_seen.setdefault(tourist_type, order)
                signals_by_type.setdefault(tourist_type, []).append(
                    f"{tourist_type}: keyword '{keyword}' (+{weight})"
                )
    if not scores:
        return "", 0, []
    best_type = max(
        scores,
        key=lambda tourist_type: (scores[tourist_type], -first_seen.get(tourist_type, 0)),
    )
    return best_type, scores[best_type], signals_by_type.get(best_type, [])


def _name_primary_type(name: str) -> str:
    name_key = normalize_key(name)
    if not name_key:
        return ""
    if _contains_keyword(name_key, "ruta"):
        return "Route"
    if "museo de " in name_key:
        return "Museum"
    if "centro de interpretacion" in name_key:
        return "TouristAttractionSite"
    if _contains_keyword(name_key, "festival") or _contains_keyword(name_key, "fiesta"):
        return "Event"
    if _contains_keyword(name_key, "mirador") or _contains_keyword(name_key, "miradores"):
        return "UrbanViewPoint"
    if "conjunto catedralicio" in name_key:
        return "TouristAttractionSite"
    if "catedral y su entorno" in name_key or "catedral de burgos y su entorno" in name_key:
        return "Route"
    return ""


def _contains_keyword(text_key: str, keyword_key: str) -> bool:
    if not text_key or not keyword_key:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(keyword_key)}(?![a-z0-9])"
    return re.search(pattern, text_key) is not None


def _is_valid_entity(entity: Entity, page: PageExtraction) -> bool:
    name_key = normalize_key(entity.name)
    if len(name_key) < 3:
        return False
    if _is_url_like_name(entity.name, page.url):
        return False
    if name_key in NAVIGATION_NAMES:
        return False
    if not entity.types and not _has_substantive_evidence(entity):
        return False
    return True


def _is_url_like_name(name: str, page_url: str) -> bool:
    raw = (name or "").strip().casefold()
    if "://" in raw or raw.startswith("www."):
        return True
    if "/" in raw or "\\" in raw:
        return True
    if any(raw.endswith(suffix) for suffix in (".com", ".es", ".org", ".net", ".eu")):
        return True
    host = urlparse(page_url).netloc.casefold().removeprefix("www.")
    host_key = normalize_key(host.rsplit(":", 1)[0])
    raw_key = normalize_key(raw)
    return bool(host_key and raw_key in {host_key, host_key.replace(" ", "")})


def _has_substantive_evidence(entity: Entity) -> bool:
    text = " ".join(
        [
            entity.shortDescription,
            entity.longDescription,
            entity.description,
            entity.evidence,
        ]
    )
    return len(normalize_key(text).split()) >= 8


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
