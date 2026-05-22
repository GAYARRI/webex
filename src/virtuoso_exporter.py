from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Entity


DEFAULT_CLASS = "TourismEntity"


@dataclass
class ExportDefaults:
    dti: str
    org: str = ""
    lang: str = "es"
    country: str = "España"
    autonomous_community: str = ""
    province: str = ""
    municipality: str = ""
    postal_code: str = ""
    external_id_prefix: str = "webex"


@dataclass
class GraphQLPayload:
    entity: str
    class_name: str
    mutation: str
    query: str
    variables: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "className": self.class_name,
            "mutation": self.mutation,
            "query": self.query,
            "variables": self.variables,
            "warnings": self.warnings,
        }


class VirtuosoSchema:
    def __init__(self, introspection: dict[str, Any]) -> None:
        schema = introspection.get("data", {}).get("__schema") or introspection.get("__schema") or {}
        self.types = {item.get("name"): item for item in schema.get("types", []) if item.get("name")}
        mutation_type = schema.get("mutationType", {}).get("name", "Mutation")
        mutation = self.types.get(mutation_type, {})
        self.mutations = {item.get("name"): item for item in mutation.get("fields", []) if item.get("name")}
        self.create_by_class = {
            name.removeprefix("create").lower(): name
            for name in self.mutations
            if name.startswith("create")
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "VirtuosoSchema":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def has_class(self, class_name: str) -> bool:
        return f"{class_name}Input" in self.types and self.create_mutation(class_name) is not None

    def create_mutation(self, class_name: str) -> str | None:
        return self.create_by_class.get(class_name.lower())

    def required_input_fields(self, class_name: str) -> set[str]:
        input_type = self.types.get(f"{class_name}Input", {})
        required = set()
        for field_def in input_type.get("inputFields", []) or []:
            if (field_def.get("type") or {}).get("kind") == "NON_NULL":
                required.add(field_def.get("name"))
        return required


def export_entities(
    entities: list[Entity],
    schema: VirtuosoSchema,
    defaults: ExportDefaults,
) -> list[GraphQLPayload]:
    return [entity_to_payload(entity, schema, defaults) for entity in entities if entity.name]


def entity_to_payload(
    entity: Entity,
    schema: VirtuosoSchema,
    defaults: ExportDefaults,
) -> GraphQLPayload:
    warnings: list[str] = []
    class_name = _select_class(entity, schema, warnings)
    mutation = schema.create_mutation(class_name) or schema.create_mutation(DEFAULT_CLASS)
    if not mutation:
        raise ValueError(f"No create mutation found for {class_name} or {DEFAULT_CLASS}")

    external_id = _external_id(entity, class_name, defaults.external_id_prefix)
    obj = _build_object(entity, class_name, defaults, warnings)
    _validate_required_fields(class_name, obj, schema, warnings)

    variables: dict[str, Any] = {
        "dti": defaults.dti,
        "input": {
            "externalId": external_id,
            "object": obj,
        },
    }
    if defaults.org:
        variables["org"] = defaults.org

    return GraphQLPayload(
        entity=entity.name,
        class_name=class_name,
        mutation=mutation,
        query=_mutation_query(mutation, class_name),
        variables=variables,
        warnings=warnings,
    )


def load_entities(path: str | Path) -> list[Entity]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        raw_entities = data
    elif isinstance(data, dict):
        raw_entities = data.get("entities", [])
    else:
        raw_entities = []
    return [Entity.from_dict(item) for item in raw_entities if isinstance(item, dict)]


def _select_class(entity: Entity, schema: VirtuosoSchema, warnings: list[str]) -> str:
    candidates = []
    selected = entity.classificationEvidence.get("selected") if entity.classificationEvidence else ""
    candidates.extend([entity.type, str(selected or "")])
    candidates.extend(entity.types)
    for candidate in candidates:
        class_name = _normalize_class_name(candidate)
        if class_name and schema.has_class(class_name):
            return class_name
    warnings.append(f"No GraphQL class found for entity type(s) {candidates!r}; using {DEFAULT_CLASS}")
    return DEFAULT_CLASS


def _build_object(
    entity: Entity,
    class_name: str,
    defaults: ExportDefaults,
    warnings: list[str],
) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "externalId": _external_id(entity, class_name, defaults.external_id_prefix),
        "name": [_literal(entity.name, defaults.lang)],
        "hasDescription": [_description_ref(entity, defaults, warnings)],
    }

    related_to = _related_urls(entity)
    if related_to:
        obj["relatedTo"] = related_to

    contact = _contact_ref(entity)
    if contact:
        obj["hasContactPoint"] = [contact]

    location = _location_ref(entity, defaults, warnings)
    if location:
        obj["hasLocation"] = [location]

    multimedia = _multimedia_ref(entity)
    if multimedia:
        obj["hasMultimedia"] = multimedia

    if entity.types:
        obj["hasAdditionalType"] = [item for item in entity.types if item]

    # Keep destination linkage empty unless the caller enriches it later with real URIs.
    if class_name in {"TourismDestination", "DestinationExperience", "Tour", "Route"}:
        obj.setdefault("relatedTourismDestination", [])

    return obj


def _description_ref(
    entity: Entity,
    defaults: ExportDefaults,
    warnings: list[str],
) -> dict[str, Any]:
    short = entity.shortDescription or entity.description or entity.sourceText or entity.name
    long = entity.longDescription or entity.description or entity.sourceText or short
    if not entity.shortDescription and not entity.description and not entity.sourceText:
        warnings.append("Missing description text; using entity name as shortDescription")
    return {
        "object": {
            "shortDescription": [_literal(short, defaults.lang)],
            "longDescription": [_literal(long, defaults.lang)] if long else [],
            "keyword": _keywords(entity),
            "relatedTourismDestination": [],
        }
    }


def _location_ref(
    entity: Entity,
    defaults: ExportDefaults,
    warnings: list[str],
) -> dict[str, Any] | None:
    coords = entity.coordinates
    has_coords = coords.lat is not None and coords.lng is not None
    if not has_coords and not entity.address:
        return None
    for field_name, value in {
        "autonomousCommunity": defaults.autonomous_community,
        "province": defaults.province,
        "municipality": defaults.municipality,
        "postalCode": defaults.postal_code,
    }.items():
        if not value:
            warnings.append(f"Location included without default {field_name}")
    location = {
        "country": defaults.country,
        "autonomousCommunity": defaults.autonomous_community,
        "province": defaults.province,
        "municipality": defaults.municipality,
        "postalCode": defaults.postal_code,
    }
    if entity.address:
        location["streetAddress"] = entity.address
    if has_coords:
        location["lat"] = coords.lat
        location["long"] = coords.lng
        location["asWkt"] = f"POINT({coords.lng} {coords.lat})"
    return {"object": location}


def _contact_ref(entity: Entity) -> dict[str, Any] | None:
    url = entity.url or entity.sourceUrl
    if not entity.email and not entity.phone and not url:
        return None
    return {
        "object": {
            "email": [entity.email] if entity.email else [],
            "telephone": [entity.phone] if entity.phone else [],
            "url": url,
            "app": [],
            "instantMessagingService": [],
        }
    }


def _multimedia_ref(entity: Entity) -> dict[str, Any] | None:
    images = [image for image in entity.images if image]
    if not images:
        return None
    return {
        "object": {
            "mainImage": images[0],
            "secondaryImage": images[1:],
            "video": [],
            "audio": [],
            "text": [],
            "url": [],
        }
    }


def _validate_required_fields(
    class_name: str,
    obj: dict[str, Any],
    schema: VirtuosoSchema,
    warnings: list[str],
) -> None:
    missing = sorted(field for field in schema.required_input_fields(class_name) if field not in obj)
    for field_name in missing:
        warnings.append(f"Missing required {class_name}Input.{field_name}")


def _literal(value: str, lang: str) -> dict[str, str]:
    return {"value": value.strip(), "lang": lang}


def _keywords(entity: Entity) -> list[str]:
    values = [entity.type, *entity.types]
    return sorted({item for item in values if item})


def _related_urls(entity: Entity) -> list[str]:
    values = [entity.sourceUrl, entity.url, entity.wikidataId and f"https://www.wikidata.org/wiki/{entity.wikidataId}"]
    values.extend(entity.relatedUrls)
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _external_id(entity: Entity, class_name: str, prefix: str) -> str:
    source = entity.wikidataId or entity.sourceUrl or entity.url or entity.name
    digest = hashlib.sha1(f"{class_name}|{entity.name}|{source}".encode("utf-8")).hexdigest()[:12]
    slug = _slug(entity.name) or "entity"
    return f"{prefix}:{class_name.lower()}:{slug}:{digest}"


def _slug(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def _normalize_class_name(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", value)


def _mutation_query(mutation: str, class_name: str) -> str:
    operation = f"Create{class_name}"
    input_type = f"{class_name}RefInput"
    return (
        f"mutation {operation}($dti: String!, $input: {input_type}!, $org: String) {{\n"
        f"  {mutation}(dti: $dti, input: $input, org: $org) {{\n"
        "    uri\n"
        "  }\n"
        "}"
    )
