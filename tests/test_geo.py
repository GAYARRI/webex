import unittest
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from src.geo import (
    _wikipedia_summary_from_wikidata,
    _build_geocode_queries,
    _city_context,
    _is_near_city,
    enrich_entities_external_context,
    enrich_entity_coordinates,
    extract_geo_candidates,
    extract_structured_data,
)
from src.models import Coordinates, Entity, PageExtraction


class GeoTests(unittest.TestCase):
    def test_extracts_coordinates_from_json_ld(self):
        soup = BeautifulSoup(
            """
            <script type="application/ld+json">
            {
              "@type": "Place",
              "name": "Catedral de Burgos",
              "geo": {
                "@type": "GeoCoordinates",
                "latitude": 42.3409,
                "longitude": -3.7044
              }
            }
            </script>
            """,
            "lxml",
        )

        structured_data = extract_structured_data(soup)
        candidates = extract_geo_candidates(soup, structured_data)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].lat, 42.3409)
        self.assertEqual(candidates[0].lng, -3.7044)
        self.assertEqual(candidates[0].source, "json-ld")

    def test_extracts_coordinates_from_meta_position(self):
        soup = BeautifulSoup(
            '<meta name="geo.position" content="42.3409;-3.7044">',
            "lxml",
        )

        candidates = extract_geo_candidates(soup, [])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source, "meta")

    def test_enrichment_keeps_existing_entity_coordinates(self):
        entity = Entity(
            name="X",
            coordinates=Coordinates(lat=1.0, lng=2.0, source="ai", confidence=0.5),
        )
        page = _page()

        enriched = enrich_entity_coordinates(entity, page)

        self.assertEqual(enriched.coordinates.lat, 1.0)
        self.assertEqual(enriched.coordinates.source, "ai")

    def test_enrichment_uses_single_page_candidate(self):
        entity = Entity(name="X")
        page = _page(geo_candidates=[Coordinates(lat=42.0, lng=-3.0, source="json-ld")])

        enriched = enrich_entity_coordinates(entity, page)

        self.assertEqual(enriched.coordinates.lat, 42.0)
        self.assertEqual(enriched.coordinates.lng, -3.0)
        self.assertEqual(enriched.coordinates.source, "json-ld")

    def test_build_geocode_queries_keeps_queries_clean(self):
        entity = Entity(name="Catedral de Burgos", address="")
        page = _page()
        page.url = "https://visitaburgosciudad.es/"
        page.title = "Inicio - Visita Burgos"

        queries = _build_geocode_queries(entity, page)

        self.assertIn("Catedral de Burgos, Burgos, Spain", queries)
        self.assertIn("Catedral de Burgos", queries)

    def test_build_geocode_queries_uses_plausible_long_address(self):
        entity = Entity(
            name="Plaza de toros",
            address="Paseo de Hemingway, Segundo Ensanche, Pamplona, Navarra, 31002, Espana",
        )
        page = _page()
        page.url = "https://visitpamplonairuna.com/"
        page.title = "Pamplona Iruna"

        queries = _build_geocode_queries(entity, page)

        self.assertIn(
            "Paseo de Hemingway, Segundo Ensanche, Pamplona, Navarra, 31002, Espana, Pamplona, Spain",
            queries,
        )
        self.assertIn(
            "Plaza de toros, Paseo de Hemingway, Segundo Ensanche, Pamplona, Navarra, 31002, Espana",
            queries,
        )

    def test_city_context_filters_far_coordinates(self):
        page = _page()
        page.url = "https://visitaburgosciudad.es/"
        context = _city_context(page)

        self.assertIsNotNone(context)
        self.assertTrue(_is_near_city(42.3407344, -3.7045635, context))
        self.assertFalse(_is_near_city(9.9374837, -84.1867511, context))

    def test_wikipedia_summary_uses_wikidata_sitelink(self):
        wikidata = {
            "sitelinks": {
                "eswiki": {"title": "Iglesia de San Nicolas de Bari (Burgos)"}
            }
        }
        response = Mock()
        response.json.return_value = {
            "title": "Iglesia de San Nicolas de Bari",
            "extract": "La iglesia de San Nicolas de Bari es un templo historico de Burgos.",
            "content_urls": {
                "desktop": {
                    "page": "https://es.wikipedia.org/wiki/Iglesia_de_San_Nicolas_de_Bari"
                }
            },
            "thumbnail": {"source": "https://upload.wikimedia.org/san-nicolas.jpg"},
        }
        response.raise_for_status.return_value = None

        with patch("src.geo.requests.get", return_value=response):
            summary = _wikipedia_summary_from_wikidata(wikidata)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["language"], "es")
        self.assertIn("templo historico", summary["extract"])
        self.assertEqual(summary["image"], "https://upload.wikimedia.org/san-nicolas.jpg")

    def test_external_context_adds_wikipedia_evidence_from_qid(self):
        entity = Entity(name="Iglesia de San Nicolas de Bari", wikidataId="Q5910998")
        page = _page()

        with (
            patch(
                "src.geo._fetch_wikidata_entity",
                return_value={
                    "labels": {"es": {"value": "Iglesia de San Nicolas de Bari"}},
                    "descriptions": {"es": {"value": "templo de Burgos"}},
                    "aliases": {},
                    "sitelinks": {"eswiki": {"title": "Iglesia de San Nicolas de Bari"}},
                },
            ),
            patch(
                "src.geo._fetch_wikipedia_summary",
                return_value={
                    "language": "es",
                    "title": "Iglesia de San Nicolas de Bari",
                    "extract": "Contexto amplio desde Wikipedia sobre el templo.",
                    "url": "https://es.wikipedia.org/wiki/Iglesia_de_San_Nicolas_de_Bari",
                    "image": "https://upload.wikimedia.org/san-nicolas.jpg",
                },
            ),
        ):
            enriched = enrich_entities_external_context([entity], page)

        source_types = [source.source_type for source in enriched[0].sources]
        self.assertIn("wikidata", source_types)
        self.assertIn("wikipedia", source_types)

    def test_external_context_does_not_query_osm_by_default(self):
        entity = Entity(
            name="Castillo de Burgos",
            wikidataId="Q4099435",
            coordinates=Coordinates(lat=42.3428, lng=-3.70722, source="wikidata"),
        )

        with (
            patch("src.geo._fetch_wikidata_entity", return_value={"sitelinks": {}}),
            patch("src.geo.geocode_entity") as geocode,
        ):
            enrich_entities_external_context([entity], _page())

        geocode.assert_not_called()


def _page(geo_candidates=None):
    return PageExtraction(
        url="https://example.com",
        title="Example",
        description=None,
        language="es",
        main_text="Texto",
        raw_text="Texto",
        images=[],
        status="ok",
        geo_candidates=geo_candidates or [],
    )


if __name__ == "__main__":
    unittest.main()
