import unittest
from pathlib import Path

from src.knowledge_base import load_kb, merge_into_kb, save_kb, tag_sources_with_page_url
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


    def test_tag_sources_with_page_url_stamps_metadata(self):
        entity = Entity(
            name="Catedral de Burgos",
            sources=[
                Evidence(url="https://example.com/a", block_id="block-1"),
                Evidence(url="https://example.com/b", block_id="block-2", metadata={"page_url": "https://already.com"}),
            ],
        )

        tag_sources_with_page_url([entity], "https://visitaburgos.es")

        self.assertEqual(entity.sources[0].metadata["page_url"], "https://visitaburgos.es")
        # pre-existing page_url must not be overwritten
        self.assertEqual(entity.sources[1].metadata["page_url"], "https://already.com")

    def test_batch_accumulates_entities_from_two_pages(self):
        page_a_entities = [
            Entity(
                name="Catedral de Burgos",
                sources=[Evidence(url="https://a.com", block_id="b1")],
            )
        ]
        page_b_entities = [
            Entity(
                name="Catedral de Burgos",
                images=["https://example.com/img.jpg"],
                sources=[Evidence(url="https://b.com", block_id="b2")],
            ),
            Entity(name="Castillo de Burgos"),
        ]

        tag_sources_with_page_url(page_a_entities, "https://a.com")
        kb, _ = merge_into_kb([], page_a_entities)

        tag_sources_with_page_url(page_b_entities, "https://b.com")
        kb, report = merge_into_kb(kb, page_b_entities)

        self.assertEqual(report["added"], 1)        # Castillo is new
        self.assertEqual(report["enriched"], 1)     # Catedral is enriched
        self.assertEqual(len(kb), 2)

        catedral = next(e for e in kb if "Catedral" in e.name)
        self.assertEqual(len(catedral.sources), 2)
        page_urls = {s.metadata.get("page_url") for s in catedral.sources}
        self.assertIn("https://a.com", page_urls)
        self.assertIn("https://b.com", page_urls)


if __name__ == "__main__":
    unittest.main()
