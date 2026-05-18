import unittest
from pathlib import Path

from src.knowledge_base import load_kb, merge_into_kb, save_kb
from src.models import Coordinates, Entity, Evidence


class KnowledgeBaseTests(unittest.TestCase):
    def test_save_and_load_kb(self):
        path = Path("data/output/test-kb.json")
        save_kb(str(path), [Entity(name="Catedral de Burgos")])
        loaded = load_kb(str(path))

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "Catedral de Burgos")

    def test_merge_into_kb_adds_and_enriches_entities(self):
        base = Entity(
            name="Catedral de Burgos",
            images=["https://example.com/1.jpg"],
            coordinates=Coordinates(lat=1, lng=1, confidence=0.2),
            sources=[Evidence(url="https://example.com/a", block_id="block-1")],
        )
        incoming = Entity(
            name="catedral de burgos",
            types=["Cathedral"],
            images=["https://example.com/1.jpg", "https://example.com/2.jpg"],
            coordinates=Coordinates(lat=2, lng=2, confidence=0.9),
            sources=[Evidence(url="https://example.com/b", block_id="block-2")],
        )

        merged, report = merge_into_kb([base], [incoming])

        self.assertEqual(report["added"], 0)
        self.assertEqual(report["enriched"], 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].types, ["Cathedral"])
        self.assertEqual(
            merged[0].images,
            ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        )
        self.assertEqual(merged[0].coordinates.lat, 2)
        self.assertEqual(len(merged[0].sources), 2)


if __name__ == "__main__":
    unittest.main()
