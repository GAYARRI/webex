import argparse
import unittest

from src.main import _collect_urls
from src.pipeline import consolidate_entity_evidence as _consolidate_entity_evidence, sanitize_entity_images as _sanitize_entity_images
from src.serializers import build_golden_result as _build_golden_result, coverage_summary as _coverage_summary, page_summary as _page_summary
from src.models import Coordinates, ContentBlock, Entity, Evidence, PageExtraction


class OutputFormatTests(unittest.TestCase):
    def test_golden_format_matches_ground_truth_entity_shape(self):
        entity = Entity(
            name="Catedral de Burgos",
            type="TouristAttractionSite",
            types=["TouristAttraction"],
            score=0.9,
            sourceUrl="https://example.com/source",
            url="https://example.com/entity",
            relatedUrls=["https://example.com/related", "https://example.com/catedral-burgos.jpg"],
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
            classificationEvidence={"selected": "TouristAttractionSite", "confidence": 90},
        )

        _sanitize_entity_images([entity])
        result = _build_golden_result([entity])

        self.assertIsInstance(result, list)
        self.assertEqual(
            set(result[0]),
            {
                "name",
                "type",
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
                "evidence",
                "classificationEvidence",
                "sources",
            },
        )
        coords = result[0]["coordinates"]
        self.assertEqual(coords["lat"], 42.0)
        self.assertEqual(coords["lng"], -3.0)
        self.assertIn("source", coords)
        self.assertIn("confidence", coords)
        self.assertEqual(result[0]["sourceText"], "Texto fuente del bloque")
        self.assertEqual(result[0]["relatedUrls"], ["https://example.com/related"])
        self.assertIn("https://example.com/catedral-burgos.jpg", result[0]["images"])
        self.assertIsInstance(result[0]["sources"], list)
        self.assertIn("evidence", result[0])
        self.assertEqual(result[0]["type"], "TouristAttractionSite")
        self.assertEqual(result[0]["classificationEvidence"]["selected"], "TouristAttractionSite")

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
                    images=["https://example.com/catedral-wikidata.jpg"],
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
            ["https://example.com/catedral-wikidata.jpg"],
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


class SourceTraceabilityTests(unittest.TestCase):
    def test_evidence_page_url_field_explicit(self):
        source = Evidence(url="https://example.com/catedral", block_id="b1", page_url="https://example.com/catedral")
        self.assertEqual(source.page_url, "https://example.com/catedral")

    def test_evidence_from_dict_reads_page_url_field(self):
        source = Evidence.from_dict({
            "url": "https://example.com/catedral",
            "block_id": "b1",
            "page_url": "https://example.com/catedral",
        })
        self.assertEqual(source.page_url, "https://example.com/catedral")

    def test_evidence_from_dict_falls_back_to_metadata_page_url(self):
        source = Evidence.from_dict({
            "url": "https://example.com/catedral",
            "block_id": "b1",
            "metadata": {"page_url": "https://example.com/pagina"},
        })
        self.assertEqual(source.page_url, "https://example.com/pagina")

    def test_golden_output_sources_contain_page_url(self):
        entity = Entity(
            name="Catedral de Burgos",
            sources=[
                Evidence(
                    url="https://visitaburgos.es/catedral",
                    block_id="b1",
                    source_type="page_block",
                    title="Catedral de Burgos",
                    text="La Catedral de Burgos es patrimonio de la humanidad.",
                    page_url="https://visitaburgos.es/que-ver/catedral",
                )
            ],
        )
        result = _build_golden_result([entity])
        sources = result[0]["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["page_url"], "https://visitaburgos.es/que-ver/catedral")
        self.assertEqual(sources[0]["source_type"], "page_block")
        self.assertEqual(sources[0]["title"], "Catedral de Burgos")
        self.assertIn("patrimonio", sources[0]["text"])

    def test_source_exposes_full_text(self):
        long_text = "x" * 1000
        entity = Entity(
            name="Test",
            sources=[Evidence(url="https://example.com", block_id="b", text=long_text, page_url="https://example.com")],
        )
        result = _build_golden_result([entity])
        self.assertEqual(len(result[0]["sources"][0]["text"]), 1000)


if __name__ == "__main__":
    unittest.main()
