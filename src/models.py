from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


@dataclass
class Evidence:
    url: str
    block_id: str
    source_type: str = "page_block"
    title: str = ""
    text: str = ""
    images: list[str] = field(default_factory=list)
    coordinates: Coordinates | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    page_url: str = ""  # crawl page this evidence was extracted from

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Evidence":
        meta = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        # page_url: explicit field first, then legacy metadata stamp, then url
        page_url = (
            str(value.get("page_url", "") or "")
            or str(meta.get("page_url", "") or "")
            or str(value.get("url", "") or "")
        )
        return cls(
            url=str(value.get("url", "") or ""),
            block_id=str(value.get("block_id", "") or ""),
            source_type=str(value.get("source_type", "page_block") or "page_block"),
            title=str(value.get("title", "") or ""),
            text=str(value.get("text", "") or ""),
            images=[str(item) for item in as_list(value.get("images")) if str(item)],
            coordinates=Coordinates.from_dict(value.get("coordinates"))
            if value.get("coordinates")
            else None,
            metadata=meta,
            page_url=page_url,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["coordinates"] = asdict(self.coordinates) if self.coordinates else None
        return data


@dataclass
class ContentBlock:
    block_id: str
    url: str
    title: str = ""
    text: str = ""
    images: list[dict[str, str]] = field(default_factory=list)
    kind: str = "block"
    position: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Coordinates:
    lat: float | None = None
    lng: float | None = None
    source: str = ""
    confidence: float | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "Coordinates":
        value = value or {}
        return cls(
            lat=value.get("lat"),
            lng=value.get("lng"),
            source=str(value.get("source", "") or ""),
            confidence=value.get("confidence"),
        )


@dataclass
class Entity:
    name: str
    type: str = ""
    types: list[str] = field(default_factory=list)
    score: float | None = None
    sourceUrl: str = ""
    url: str = ""
    relatedUrls: list[str] = field(default_factory=list)
    address: str = ""
    phone: str = ""
    email: str = ""
    coordinates: Coordinates = field(default_factory=Coordinates)
    shortDescription: str = ""
    longDescription: str = ""
    sourceText: str = ""
    description: str = ""
    images: list[str] = field(default_factory=list)
    wikidataId: str = ""
    evidence: str = ""
    sources: list[Evidence] = field(default_factory=list)
    classificationEvidence: dict[str, Any] = field(default_factory=dict)
    startDate: str = ""
    endDate: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Entity":
        long_description = value.get("longDescription", value.get("longDescriptionb", ""))
        return cls(
            name=str(value.get("name", "")).strip(),
            type=str(value.get("type", "") or ""),
            types=[str(item).strip() for item in as_list(value.get("types")) if str(item).strip()],
            score=value.get("score"),
            sourceUrl=str(value.get("sourceUrl", "") or ""),
            url=str(value.get("url", "") or ""),
            relatedUrls=[str(item) for item in as_list(value.get("relatedUrls")) if str(item)],
            address=str(value.get("address", "") or ""),
            phone=str(value.get("phone", "") or ""),
            email=str(value.get("email", "") or ""),
            coordinates=Coordinates.from_dict(value.get("coordinates")),
            shortDescription=str(value.get("shortDescription", "") or ""),
            longDescription=str(long_description or ""),
            sourceText=str(value.get("sourceText", "") or ""),
            description=str(value.get("description", "") or ""),
            images=[str(item) for item in as_list(value.get("images")) if str(item)],
            wikidataId=str(value.get("wikidataId", "") or ""),
            evidence=str(value.get("evidence", "") or ""),
            sources=[
                Evidence.from_dict(item)
                for item in as_list(value.get("sources"))
                if isinstance(item, dict)
            ],
            classificationEvidence=value.get("classificationEvidence")
            if isinstance(value.get("classificationEvidence"), dict)
            else {},
            startDate=str(value.get("startDate", "") or ""),
            endDate=str(value.get("endDate", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["coordinates"] = asdict(self.coordinates)
        return data


@dataclass
class PageExtraction:
    url: str
    title: str | None
    description: str | None
    language: str | None
    main_text: str
    raw_text: str
    images: list[dict[str, str]]
    status: str
    structured_data: list[dict[str, Any]] = field(default_factory=list)
    geo_candidates: list[Coordinates] = field(default_factory=list)
    blocks: list[ContentBlock] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
