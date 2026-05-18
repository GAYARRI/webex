from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

from .ai_client import TOURIST_TYPES, ai_available, extract_entities_with_ai
from .entity_text import relevant_text_for_entity
from .image_filters import is_image_url
from .models import Coordinates, Entity, PageExtraction
from .text_utils import normalize_key


SCHEMA_TO_TOURIST_TYPE: dict[str, str] = {
    "TouristAttraction": "TouristAttraction",
    "Museum": "Museum",
    "Church": "Church",
    "LandmarksOrHistoricalBuildings": "HistoricalSite",
    "HistoricBuilding": "HistoricalSite",
    "CivicStructure": "Monument",
    "GovernmentBuilding": "Monument",
    "LocalBusiness": "LocalBusiness",
    "FoodEstablishment": "Restaurant",
    "Restaurant": "Restaurant",
    "CafeOrCoffeeShop": "Restaurant",
    "BarOrPub": "LocalBusiness",
    "Hotel": "Hotel",
    "Lodging": "Hotel",
    "Hostel": "Hotel",
    "BedAndBreakfast": "Hotel",
    "PerformingArtsTheater": "Theater",
    "MovieTheater": "Theater",
    "ArtGallery": "ArtGallery",
    "Park": "Park",
    "Event": "CulturalEvent",
    "MusicEvent": "Festival",
    "ExhibitionEvent": "CulturalEvent",
    "Festival": "Festival",
    "TheaterEvent": "CulturalEvent",
    "NightClub": "NightClub",
    "TouristInformationCenter": "TouristInformationCenter",
    "EntertainmentBusiness": "EntertainmentBusiness",
    "Library": "Museum",
    "Aquarium": "TouristAttraction",
    "Zoo": "TouristAttraction",
    "Winery": "LocalBusiness",
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
            images=[item["url"] for item in block.images if item.get("url")],
            evidence=relevant_text[:300] or name,
        )
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
}


TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("catedral", "Church"),
    ("iglesia", "Church"),
    ("basilica", "Church"),
    ("capilla", "Church"),
    ("monasterio", "Church"),
    ("cartuja", "Church"),
    ("museo", "Museum"),
    ("centro de biodiversidad", "TouristAttraction"),
    ("centro de arte", "ArtGallery"),
    ("galeria", "ArtGallery"),
    ("castillo", "HistoricalSite"),
    ("archivo", "Museum"),
    ("palacio", "HistoricalSite"),
    ("plaza", "TouristAttraction"),
    ("parque", "Park"),
    ("jardin", "Park"),
    ("ruta", "Tour"),
    ("camino", "Tour"),
    ("festival", "Festival"),
    ("semana santa", "Festival"),
    ("concierto", "CulturalEvent"),
    ("teatro", "Theater"),
    ("hotel", "Hotel"),
    ("restaurante", "Restaurant"),
    ("oficina de turismo", "TouristInformationCenter"),
    ("pulsera turistica", "Tour"),
]


def _normalize_entity(entity: Entity, page: PageExtraction) -> None:
    entity.name = _clean_name(entity.name)
    entity.sourceUrl = entity.sourceUrl or page.url
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


def _normalize_types(types: list[str], entity: Entity) -> list[str]:
    allowed = set(TOURIST_TYPES)
    normalized = [item for item in _dedupe(types) if item in allowed]
    inferred, confidence = _infer_type(entity)
    if normalized and inferred:
        if inferred in normalized:
            return normalized
        if confidence >= 90:
            return [inferred]
    if normalized:
        return normalized
    return [inferred] if inferred else []


def _infer_type(entity: Entity) -> tuple[str, int]:
    contexts = [
        (entity.name, 100),
        (entity.shortDescription, 35),
        (entity.sourceText, 30),
        (entity.evidence, 25),
        (entity.longDescription, 15),
        (entity.description, 15),
    ]
    scores: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for order, (keyword, tourist_type) in enumerate(TYPE_KEYWORDS):
        keyword_key = normalize_key(keyword)
        for text, weight in contexts:
            if keyword_key and keyword_key in normalize_key(text):
                scores[tourist_type] = scores.get(tourist_type, 0) + weight
                first_seen.setdefault(tourist_type, order)
    if not scores:
        return "", 0
    best_type = max(
        scores,
        key=lambda tourist_type: (scores[tourist_type], -first_seen.get(tourist_type, 0)),
    )
    return best_type, scores[best_type]


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
