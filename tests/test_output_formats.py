import argparse
import unittest

from src.main import (
    _build_golden_result,
    _collect_urls,
    _consolidate_entity_evidence,
    _coverage_summary,
    _page_summary,
    _sanitize_entity_images,
)
from src.models import Coordinates, ContentBlock, Entity, Evidence, PageExtraction


class OutputFormatTests(unittest.TestCase):
    def test_golden_format_matches_ground_truth_entity_shape(self):
        entity = Entity(
            name="Catedral de Burgos",
            types=["TouristAttraction"],
            score=0.9,
            sourceUrl="https://example.com/source",
            url="https://example.com/entity",
            relatedUrls=["https://example.com/related", "https://example.com/image.jpg"],
            address="Plaza de Santa Maria",
            phone="947000000",
            email="info@example.com",
            coordinates=Coordinates(lat=42.0, lng=-3.0, source="wikidata", confidence=0.8),
            shortDescription="Breve",
            longDescription="Larga",
            sourceText="Texto fuente del bloque",
            description="Contexto",
            images=["https://example.com/catedral.jpg"],
            wikidataId="Q1",
        )

        _sanitize_entity_images([entity])
        result = _build_golden_result([entity])

        self.assertIsInstance(result, list)
        self.assertEqual(
            set(result[0]),
            {
                "name",
                "types",
                "score",
                "sourceUrl",
                "url",
                "relatedUrls",
                "address",
                "phone",
                "email",
                "coordinates",
                "shortDescription",
                "longDescription",
                "sourceText",
                "description",
                "images",
                "wikidataId",
            },
        )
        self.assertEqual(result[0]["coordinates"], {"lat": 42.0, "lng": -3.0})
        self.assertEqual(result[0]["sourceText"], "Texto fuente del bloque")
        self.assertEqual(result[0]["relatedUrls"], ["https://example.com/related"])
        self.assertIn("https://example.com/image.jpg", result[0]["images"])
        self.assertNotIn("sources", result[0])
        self.assertNotIn("evidence", result[0])

    def test_sanitize_entity_images_removes_icons(self):
        entity = Entity(
            name="Catedral",
            images=[
                "https://example.com/clock.png",
                "https://example.com/catedral.jpg",
                "https://example.com/catedral.jpg",
            ],
        )

        _sanitize_entity_images([entity])

        self.assertEqual(entity.images, ["https://example.com/catedral.jpg"])

    def test_consolidates_external_source_images_and_urls_before_output(self):
        entity = Entity(
            name="Catedral",
            sources=[
                Evidence(
                    url="https://www.wikidata.org/wiki/Q1",
                    block_id="Q1",
                    source_type="wikidata",
                    text="Contexto externo de Wikidata.",
                    images=["https://example.com/wikidata.jpg"],
                    metadata={"address": "Plaza Mayor", "phone": "947 000 000"},
                ),
                Evidence(
                    url="https://example.com/page",
                    block_id="block-1",
                    source_type="page_block",
                    images=["https://example.com/page.jpg"],
                ),
            ],
        )

        _consolidate_entity_evidence([entity])
        _sanitize_entity_images([entity])
        result = _build_golden_result([entity])

        self.assertEqual(
            result[0]["images"],
            ["https://example.com/wikidata.jpg"],
        )
        self.assertEqual(result[0]["relatedUrls"], ["https://www.wikidata.org/wiki/Q1"])
        self.assertEqual(result[0]["address"], "Plaza Mayor")
        self.assertEqual(result[0]["phone"], "947 000 000")
        self.assertIn("Contexto externo de Wikidata", result[0]["longDescription"])

    def test_page_summary_does_not_expose_blocks(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
            description="Description",
            language="es",
            main_text="Texto",
            raw_text="Texto",
            images=[{"url": "https://example.com/a.jpg"}],
            status="ok",
            blocks=[ContentBlock(block_id="block-1", url="https://example.com", text="Texto")],
        )

        summary = _page_summary(page)

        self.assertNotIn("blocks", summary)
        self.assertEqual(summary["block_count"], 1)
        self.assertEqual(summary["image_count"], 1)

    def test_coverage_summary_does_not_expose_block_details(self):
        summary = _coverage_summary(
            {
                "total_blocks": 3,
                "candidate_tourist_blocks": 2,
                "covered_candidate_blocks": 1,
                "uncovered_candidate_blocks": 1,
                "coverage_ratio": 0.5,
                "status_counts": {"unresolved_relevant": 1},
                "block_resolution": [{"block_id": "block-1"}],
                "uncovered_blocks": [{"block_id": "block-2"}],
            }
        )

        self.assertNotIn("block_resolution", summary)
        self.assertNotIn("uncovered_blocks", summary)
        self.assertEqual(summary["status_counts"], {"unresolved_relevant": 1})

    def test_collect_urls_from_urls_arg(self):
        args = argparse.Namespace(urls=["https://a.com", "https://b.com"], urls_file=None, url=None)
        self.assertEqual(_collect_urls(args), ["https://a.com", "https://b.com"])

    def test_collect_urls_from_urls_file(self, tmp_path=None):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("https://a.com\n# comentario\nhttps://b.com\n\n")
            tmp = f.name
        try:
            args = argparse.Namespace(urls=None, urls_file=tmp, url=None)
            self.assertEqual(_collect_urls(args), ["https://a.com", "https://b.com"])
        finally:
            os.unlink(tmp)

    def test_collect_urls_fallback_to_single_url(self):
        args = argparse.Namespace(urls=None, urls_file=None, url="https://single.com")
        self.assertEqual(_collect_urls(args), ["https://single.com"])


if __name__ == "__main__":
    unittest.main()
