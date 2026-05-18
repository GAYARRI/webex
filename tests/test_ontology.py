import unittest

from src.ontology import OntologyIndex, OntologyClass, load_ontology, _SEGITTUR


class OntologyTests(unittest.TestCase):
    def setUp(self):
        self.index = load_ontology("data/ontology/ontology.rdf")

    def test_loads_segittur_classes(self):
        self.assertGreater(len(self.index), 100)

    def test_cathedral_has_spanish_label(self):
        label = self.index.label_es("Cathedral")
        self.assertIn("atedral", label)

    def test_castle_has_spanish_label(self):
        label = self.index.label_es("Castle")
        self.assertIn("astillo", label)

    def test_cathedral_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Cathedral", types)

    def test_church_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Church", types)

    def test_monastery_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Monastery", types)

    def test_event_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Event", types)

    def test_route_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Route", types)

    def test_hotel_is_in_classifiable_types(self):
        types = self.index.classifiable_types()
        self.assertIn("Hotel", types)

    def test_subtree_includes_all_historical_resources(self):
        subtree = self.index.subtree("HistoricalOrCulturalResource")
        self.assertIn("Cathedral", subtree)
        self.assertIn("Castle", subtree)
        self.assertIn("Museum", subtree)
        self.assertIn("Monastery", subtree)

    def test_prompt_vocabulary_includes_label(self):
        vocab = self.index.prompt_vocabulary()
        cathedral_entry = next((v for v in vocab if v[0] == "Cathedral"), None)
        self.assertIsNotNone(cathedral_entry)
        self.assertIn("atedral", cathedral_entry[1])

    def test_uri_returns_full_segittur_uri(self):
        uri = self.index.uri("Cathedral")
        self.assertTrue(uri.startswith(_SEGITTUR))
        self.assertIn("Cathedral", uri)

    def test_fallback_when_ontology_missing(self):
        fallback = load_ontology("nonexistent/path.rdf")
        types = fallback.classifiable_types()
        self.assertIn("Cathedral", types)
        self.assertIn("Museum", types)
        self.assertGreater(len(types), 10)


if __name__ == "__main__":
    unittest.main()
