from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_OWL = "http://www.w3.org/2002/07/owl#"
_XML = "http://www.w3.org/XML/1998/namespace"
_SEGITTUR = "https://ontologia.segittur.es/turismo/def/core#"

# Branches whose full subtree is classifiable
_CLASSIFIABLE_ROOTS = [
    "HistoricalOrCulturalResource",
    "NaturalResource",
    "Route",
    "Event",
    "TourismService",
]

# Selected leaf/intermediate classes from TourismOrRelatedFacility
_SELECTED_FACILITIES = [
    "AccommodationEstablishment",
    "Aparthotel", "Camping", "GuestHouse", "Hostal", "Hostel",
    "Hotel", "Lodge", "Motel", "Residence", "Resort", "RuralHouse", "VacationRental",
    "FoodEstablishment",
    "Bar", "BeachBar", "Brewery", "CafeOrCoffeShop", "CocktailBar",
    "GastronomicMarket", "Inn", "Restaurant", "Tavern", "WineBar",
    "LeisureAndCultureFacility",
    "AmusementPark", "Aquarium", "ArtGallery", "ExhibitionHall",
    "MovieTheater", "Planetarium", "Zoo",
    "EventAttendanceFacility",
    "Auditorium", "BullRing", "CongressCentre", "MusicVenue",
    "PartyAndEntertainmentFacility",
    "NightClub", "Pub",
    "SportFacility",
    "GolfCourse", "MultiAdventureCentre", "SportsCentre", "SwimmingPool",
    "WinterSportsResort",
    "AgrotourismFacility",
    "Winery", "Vineyard", "TraditionalMarket",
]

# (local_name, parent) — parent "" means root / classifiable directly
_FALLBACK_TYPES: list[tuple[str, str]] = [
    ("HistoricalOrCulturalResource", ""),
    ("Cathedral",        "HistoricalOrCulturalResource"),
    ("Church",           "HistoricalOrCulturalResource"),
    ("Basilica",         "HistoricalOrCulturalResource"),
    ("Chapel",           "HistoricalOrCulturalResource"),
    ("Monastery",        "HistoricalOrCulturalResource"),
    ("Convent",          "HistoricalOrCulturalResource"),
    ("Museum",           "HistoricalOrCulturalResource"),
    ("ArtGallery",       "HistoricalOrCulturalResource"),
    ("Castle",           "HistoricalOrCulturalResource"),
    ("Palace",           "HistoricalOrCulturalResource"),
    ("Monument",         "HistoricalOrCulturalResource"),
    ("CultureCentre",    "HistoricalOrCulturalResource"),
    ("Theater",          "HistoricalOrCulturalResource"),
    ("Auditorium",       "HistoricalOrCulturalResource"),
    ("Garden",           "HistoricalOrCulturalResource"),
    ("Square",           "HistoricalOrCulturalResource"),
    ("ArcheologicalSite","HistoricalOrCulturalResource"),
    ("TouristAttractionSite", "HistoricalOrCulturalResource"),
    ("NaturalResource",  ""),
    ("NaturalPark",      "NaturalResource"),
    ("Trail",            "NaturalResource"),
    ("Beach",            "NaturalResource"),
    ("Cave",             "NaturalResource"),
    ("Mountain",         "NaturalResource"),
    ("Route",            ""),
    ("Event",            ""),
    ("TourismService",   ""),
    ("Tour",             "TourismService"),
    ("Hotel",            ""),
    ("Hostel",           ""),
    ("RuralHouse",       ""),
    ("Restaurant",       ""),
    ("Bar",              ""),
    ("CafeOrCoffeShop",  ""),
    ("NightClub",        ""),
    ("Pub",              ""),
]


@dataclass
class OntologyClass:
    local_name: str
    uri: str
    label_es: str = ""
    label_en: str = ""
    parent: str = ""


class OntologyIndex:
    def __init__(self, classes: list[OntologyClass]) -> None:
        self._by_name: dict[str, OntologyClass] = {c.local_name: c for c in classes}
        self._children: dict[str, list[str]] = {}
        for c in classes:
            if c.parent:
                self._children.setdefault(c.parent, []).append(c.local_name)

    # ------------------------------------------------------------------
    def get(self, name: str) -> OntologyClass | None:
        return self._by_name.get(name)

    def label_es(self, name: str) -> str:
        c = self._by_name.get(name)
        return c.label_es if c and c.label_es else name

    def uri(self, name: str) -> str:
        c = self._by_name.get(name)
        return c.uri if c else f"{_SEGITTUR}{name}"

    def subtree(self, root: str) -> list[str]:
        result: list[str] = []
        queue = [root]
        while queue:
            node = queue.pop()
            if node in self._by_name:
                result.append(node)
            queue.extend(self._children.get(node, []))
        return result

    def classifiable_types(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for root in _CLASSIFIABLE_ROOTS:
            for name in self.subtree(root):
                if name not in seen:
                    seen.add(name)
                    result.append(name)
        for name in _SELECTED_FACILITIES:
            if name in self._by_name and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def prompt_vocabulary(self) -> list[tuple[str, str]]:
        """Returns [(local_name, label_es), ...] for use in AI prompts."""
        types = self.classifiable_types()
        return [(t, self.label_es(t)) for t in types]

    def __len__(self) -> int:
        return len(self._by_name)


def load_ontology(path: str | None = None) -> OntologyIndex:
    """Load ontology from RDF file. Falls back to a minimal built-in set on failure."""
    resolved = Path(path) if path else Path("data/ontology/ontology.rdf")
    if not resolved.exists():
        return _fallback_index()
    try:
        return _parse_rdf(resolved)
    except Exception:
        return _fallback_index()


def _parse_rdf(path: Path) -> OntologyIndex:
    tree = ET.parse(str(path))
    root = tree.getroot()
    classes: list[OntologyClass] = []
    for cls in root.findall(f".//{{{_OWL}}}Class"):
        uri = cls.get(f"{{{_RDF}}}about", "")
        if not uri.startswith(_SEGITTUR):
            continue
        local_name = uri.split("#")[1]
        label_es = _find_label(cls, "es")
        label_en = _find_label(cls, "en")
        parent_elem = cls.find(f"{{{_RDFS}}}subClassOf")
        parent_uri = (
            parent_elem.get(f"{{{_RDF}}}resource", "") if parent_elem is not None else ""
        )
        parent_local = parent_uri.split("#")[1] if "#" in parent_uri else ""
        classes.append(
            OntologyClass(
                local_name=local_name,
                uri=uri,
                label_es=label_es,
                label_en=label_en,
                parent=parent_local,
            )
        )
    return OntologyIndex(classes)


def _find_label(element: ET.Element, lang: str) -> str:
    for label in element.findall(f"{{{_RDFS}}}label"):
        if label.get(f"{{{_XML}}}lang") == lang:
            return label.text or ""
    return ""


def _fallback_index() -> OntologyIndex:
    classes = [
        OntologyClass(local_name=name, uri=f"{_SEGITTUR}{name}", parent=parent)
        for name, parent in _FALLBACK_TYPES
    ]
    return OntologyIndex(classes)


# Module-level singleton — loaded once on first import
_INDEX: OntologyIndex | None = None


def get_index() -> OntologyIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = load_ontology()
    return _INDEX
