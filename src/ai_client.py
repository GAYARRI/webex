from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from .models import Entity, PageExtraction


DEFAULT_MODEL = "gpt-5.4-mini"

TOURIST_TYPES = [
    "TouristAttraction",
    "Museum",
    "Church",
    "Monument",
    "HistoricalSite",
    "Park",
    "ArtGallery",
    "Theater",
    "PerformingArtsTheater",
    "NaturalFeature",
    "Restaurant",
    "Hotel",
    "Lodging",
    "LocalBusiness",
    "CulturalEvent",
    "Festival",
    "Tour",
    "NightClub",
    "TouristInformationCenter",
    "EntertainmentBusiness",
    "TraditionalArt",
]


def configured_model() -> str:
    load_dotenv()
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def ai_available() -> bool:
    load_dotenv()
    return bool(os.getenv("OPENAI_API_KEY"))


def extract_entities_with_ai(page: PageExtraction, model: str | None = None) -> list[Entity]:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return []

    from openai import OpenAI

    client = OpenAI()
    prompt = _build_prompt(page)
    response = client.responses.create(
        model=model or configured_model(),
        input=[
            {
                "role": "system",
                "content": (
                    "Extrae entidades turisticas relevantes desde contenido web. "
                    "Devuelve solo JSON valido, sin markdown."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        text={"format": {"type": "json_object"}},
    )
    data = _parse_response_text(response)
    raw_entities = data.get("entities", []) if isinstance(data, dict) else []
    entities = [Entity.from_dict(item) for item in raw_entities if isinstance(item, dict)]
    for entity in entities:
        if not entity.url:
            entity.url = page.url
        if not entity.sourceUrl:
            entity.sourceUrl = page.url
    return entities


def _build_prompt(page: PageExtraction) -> str:
    images = [
        {
            "url": item.get("url", ""),
            "alt": item.get("alt", ""),
            "context": item.get("context", ""),
            "index": item.get("index", ""),
        }
        for item in page.images[:25]
    ]
    text = page.main_text[:10000]
    blocks = _summarize_blocks(page)
    structured_data = _summarize_structured_data(page)

    return json.dumps(
        {
            "task": (
                "Extrae entidades turisticas/culturales relevantes. "
                "Antes de extraer, analiza el bloque completo y descarta ruido. "
                "La identidad de una entidad la determina el concepto turistico, nunca la URL."
            ),
            "identity_contract": [
                "La URL es solo evidencia/fuente. Nunca uses una URL, dominio, slug, breadcrumb o ruta como name.",
                "El campo name debe ser el nombre natural del recurso, evento, lugar, servicio o institucion turistica.",
                "Si una pagina trata de un unico recurso, extrae el recurso por su nombre turistico aunque la URL sea mas visible.",
                "Si un bloque contiene varios conceptos ontologicos claros, crea varias entidades independientes con sus propias evidencias.",
                "Si otro bloque aporta texto o imagenes sobre una entidad ya existente, debe reforzar esa entidad; no crees una entidad basada en la URL.",
            ],
            "procedure": [
                "1. Evalua el contenido completo disponible: texto, titulo, descripcion, bloques, structured_data e imagenes candidatas.",
                "2. Elimina mentalmente contenido sin valor ontologico: navegacion, menus, idiomas, cookies, logos, iconos sociales, botones, banners, textos legales y errores de plantilla.",
                "3. Construye una idea general del bloque: de que trata, que recurso o experiencia describe y que intencion tiene.",
                "4. Correlaciona esa idea general con categorias ontologicas candidatas de la lista tourist_types.",
                "5. Extrae solo entidades semanticamente utiles y clasificables: recursos turisticos, patrimonio, eventos, servicios, rutas, lugares, establecimientos, experiencias o instituciones relevantes.",
                "6. No extraigas elementos de navegacion como entidades salvo que el texto del bloque los describa como recurso real.",
                "7. Usa todas las evidencias disponibles: texto, bloques (blocks), contexto de imagen, URLs, metadatos, categorias, y conocimiento externo solo como apoyo.",
                "8. Para imagenes, asocia preferentemente las del bloque (blocks) donde aparece la entidad. Descarta logos, iconos, botones, apps y decoracion.",
                "9. Si structured_data contiene la entidad (name, address, geo, telephone, etc.), usa esos campos como fuente de maxima prioridad y no los inventes.",
            ],
            "tourist_types": TOURIST_TYPES,
            "schema": {
                "entities": [
                    {
                        "name": "string",
                        "types": ["<uno o mas valores exactos de tourist_types>"],
                        "score": 0.0,
                        "sourceUrl": "string",
                        "url": "string",
                        "relatedUrls": ["string"],
                        "address": "string",
                        "phone": "string",
                        "email": "string",
                        "coordinates": {"lat": None, "lng": None},
                        "shortDescription": "string",
                        "longDescription": "string",
                        "description": "string",
                        "images": ["string"],
                        "wikidataId": "string",
                        "evidence": "string",
                    }
                ]
            },
            "rules": [
                "El campo types SOLO puede contener valores de la lista tourist_types proporcionada. Nunca uses tipos fuera de esa lista.",
                "El name debe prevalecer sobre la URL: si dudas entre un slug/URL y un nombre turistico, elige siempre el nombre turistico.",
                "No pongas la URL de la pagina en name. Ponla en sourceUrl o relatedUrls si es relevante.",
                "No extraigas breadcrumbs, items de menu, categorias de navegacion o landing labels como entidades.",
                "Si structured_data contiene la entidad, prioriza sus campos (name, address, geo, telephone, email, image) sobre el texto libre.",
                "Usa solo entidades relevantes para turismo, cultura, eventos, servicios, rutas, patrimonio, lugares o instituciones.",
                "Si no conoces un campo, usa cadena vacia, lista vacia o coordenadas null.",
                "No inventes Wikidata IDs ni coordenadas.",
                "Asigna score entre 0 y 1 segun confianza.",
                "Incluye evidence con una frase breve del texto que justifique la entidad.",
                "No incluyas entidades extraidas solo de menus de navegacion si no hay contenido descriptivo suficiente.",
                "No incluyas imagenes genericas, logos, iconos sociales, botones, imagenes de app store ni recursos decorativos.",
                "Una entidad puede tener varias imagenes, pero no repitas URLs.",
                "Prefiere menos entidades y mejor justificadas antes que muchas entidades superficiales.",
                "La clasificacion debe ser una categoria ontologica candidata de tourist_types, no una etiqueta decorativa.",
            ],
            "page": {
                "url": page.url,
                "title": page.title,
                "description": page.description,
                "language": page.language,
                "images": images,
                "text": text,
                "blocks": blocks,
                "structured_data": structured_data,
            },
        },
        ensure_ascii=False,
    )


def _summarize_blocks(page: PageExtraction) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in page.blocks:
        if not block.title and not block.images:
            continue
        result.append(
            {
                "id": block.block_id,
                "title": block.title,
                "text": block.text[:400],
                "images": [
                    {"url": img["url"], "alt": img.get("alt", "")}
                    for img in block.images[:4]
                ],
            }
        )
        if len(result) >= 15:
            break
    return result


def _summarize_structured_data(page: PageExtraction) -> list[dict[str, Any]]:
    RELEVANT_TYPES = {
        "TouristAttraction", "Museum", "Church", "LocalBusiness",
        "FoodEstablishment", "Restaurant", "Hotel", "Lodging",
        "CivicStructure", "PerformingArtsTheater", "ArtGallery",
        "Park", "Event", "MusicEvent", "Festival", "NightClub",
        "LandmarksOrHistoricalBuildings", "HistoricBuilding",
    }
    FIELDS = [
        "@type", "name", "description", "address", "geo",
        "telephone", "email", "url", "openingHours", "image",
    ]
    result: list[dict[str, Any]] = []
    for item in page.structured_data:
        schema_type = item.get("@type", "")
        if isinstance(schema_type, list):
            schema_type = schema_type[0] if schema_type else ""
        is_relevant = any(t in str(schema_type) for t in RELEVANT_TYPES)
        has_name_and_location = bool(item.get("name")) and bool(item.get("geo") or item.get("address"))
        if not (is_relevant or has_name_and_location):
            continue
        summary = {f: item[f] for f in FIELDS if f in item and item[f]}
        if summary:
            result.append(summary)
        if len(result) >= 8:
            break
    return result


def _parse_response_text(response: Any) -> dict[str, Any]:
    text = getattr(response, "output_text", None)
    if not text:
        chunks: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                value = getattr(content, "text", None)
                if value:
                    chunks.append(value)
        text = "".join(chunks)
    return json.loads(text or "{}")
