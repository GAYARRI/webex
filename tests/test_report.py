import unittest

from src.report import count_by_type, count_by_page, to_markdown


def _entity(name, types=None, *, lat=None, lng=None, desc="", address="", images=None, wikidata=""):
    return {
        "name": name,
        "types": types or [],
        "shortDescription": desc,
        "coordinates": {"lat": lat, "lng": lng, "confidence": 0.9} if lat is not None else {},
        "address": address,
        "images": images or [],
        "sources": [],
        "wikidataId": wikidata,
    }


class CountByTypeTests(unittest.TestCase):
    def test_counts_single_type(self):
        entities = [_entity("A", ["Cathedral"]), _entity("B", ["Cathedral"])]
        counts = count_by_type(entities)
        self.assertEqual(counts["Cathedral"], 2)

    def test_entity_with_multiple_types_counts_in_each(self):
        entities = [_entity("A", ["Cathedral", "Monument"])]
        counts = count_by_type(entities)
        self.assertEqual(counts["Cathedral"], 1)
        self.assertEqual(counts["Monument"], 1)

    def test_returns_empty_for_no_types(self):
        entities = [_entity("A", [])]
        counts = count_by_type(entities)
        self.assertEqual(counts, {})

    def test_ordered_by_frequency(self):
        entities = [
            _entity("A", ["Cathedral"]),
            _entity("B", ["Cathedral"]),
            _entity("C", ["Museum"]),
        ]
        keys = list(count_by_type(entities).keys())
        self.assertEqual(keys[0], "Cathedral")

    def test_empty_list(self):
        self.assertEqual(count_by_type([]), {})


class CountByPageTests(unittest.TestCase):
    def _entity_with_sources(self, pages):
        return {
            "name": "X", "types": [],
            "sources": [{"metadata": {"page_url": p}} for p in pages],
        }

    def test_counts_entity_once_per_page(self):
        entity = self._entity_with_sources(["https://a.com", "https://a.com"])
        counts = count_by_page([entity])
        self.assertEqual(counts["https://a.com"], 1)

    def test_two_entities_same_page(self):
        e1 = self._entity_with_sources(["https://a.com"])
        e2 = self._entity_with_sources(["https://a.com"])
        counts = count_by_page([e1, e2])
        self.assertEqual(counts["https://a.com"], 2)

    def test_entity_in_multiple_pages(self):
        entity = self._entity_with_sources(["https://a.com", "https://b.com"])
        counts = count_by_page([entity])
        self.assertEqual(counts["https://a.com"], 1)
        self.assertEqual(counts["https://b.com"], 1)

    def test_empty_sources(self):
        entity = {"name": "X", "types": [], "sources": []}
        counts = count_by_page([entity])
        self.assertEqual(counts, {})

    def test_ordered_by_frequency(self):
        e1 = self._entity_with_sources(["https://a.com"])
        e2 = self._entity_with_sources(["https://a.com"])
        e3 = self._entity_with_sources(["https://b.com"])
        counts = count_by_page([e1, e2, e3])
        self.assertEqual(list(counts.keys())[0], "https://a.com")


class ToMarkdownTests(unittest.TestCase):
    def test_contains_entity_name(self):
        entities = [_entity("Catedral de Burgos", ["Cathedral"])]
        md = to_markdown(entities)
        self.assertIn("Catedral de Burgos", md)

    def test_contains_type_summary_table(self):
        entities = [_entity("Catedral", ["Cathedral"])]
        md = to_markdown(entities)
        self.assertIn("Resumen por tipo", md)
        self.assertIn("Cathedral", md)

    def test_contains_domain_in_header(self):
        entities = []
        md = to_markdown(entities, domain="visitaburgos.es")
        self.assertIn("visitaburgos.es", md)

    def test_contains_pages_processed(self):
        entities = []
        md = to_markdown(entities, pages_processed=5)
        self.assertIn("5", md)

    def test_coordinates_shown_when_present(self):
        entities = [_entity("Catedral", lat=42.34, lng=-3.69)]
        md = to_markdown(entities)
        self.assertIn("42.34", md)
        self.assertIn("-3.69", md)

    def test_wikidata_shown_when_present(self):
        entities = [_entity("Catedral", wikidata="Q123")]
        md = to_markdown(entities)
        self.assertIn("Q123", md)

    def test_no_type_table_when_no_types(self):
        entities = [_entity("Sin tipo", [])]
        md = to_markdown(entities)
        self.assertNotIn("Resumen por tipo", md)

    def test_empty_entities_list(self):
        md = to_markdown([])
        self.assertIn("Base de conocimiento", md)
        self.assertIn("0 entidades", md)

    def test_extracted_at_used_when_provided(self):
        entities = []
        md = to_markdown(entities, extracted_at="2025-01-15")
        self.assertIn("2025-01-15", md)


if __name__ == "__main__":
    unittest.main()
