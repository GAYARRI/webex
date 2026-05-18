import unittest

from src.content_coverage import analyze_content_coverage
from src.models import ContentBlock, Entity, Evidence, PageExtraction


class ContentCoverageTests(unittest.TestCase):
    def test_reports_tourist_blocks_without_entity_evidence(self):
        page = PageExtraction(
            url="https://example.com",
            title="Burgos",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://example.com",
                    title="Catedral de Burgos",
                    text="La Catedral de Burgos es patrimonio y admite visita turistica.",
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://example.com",
                    title="Museo de Burgos",
                    text="Museo con exposicion permanente.",
                ),
            ],
        )
        entities = [
            Entity(
                name="Catedral de Burgos",
                sources=[Evidence(url="https://example.com", block_id="block-1")],
            )
        ]

        report = analyze_content_coverage(page, entities)

        self.assertEqual(report["candidate_tourist_blocks"], 2)
        self.assertEqual(report["covered_candidate_blocks"], 1)
        self.assertEqual(report["uncovered_candidate_blocks"], 1)
        self.assertEqual(report["uncovered_blocks"][0]["block_id"], "block-2")
        self.assertEqual(report["uncovered_blocks"][0]["status"], "unresolved_relevant")

    def test_reports_block_covered_by_related_entities(self):
        page = PageExtraction(
            url="https://example.com",
            title="Burgos",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://example.com",
                    title="Burgos ciudad",
                    text="Descubre Burgos con la Catedral de Burgos, el Castillo de Burgos y el Camino de Santiago.",
                )
            ],
        )
        entities = [
            Entity(name="Catedral de Burgos"),
            Entity(name="Castillo de Burgos"),
            Entity(name="Camino de Santiago en Burgos"),
        ]

        report = analyze_content_coverage(page, entities)

        self.assertEqual(report["uncovered_candidate_blocks"], 0)
        self.assertEqual(
            report["block_resolution"][0]["status"],
            "covered_by_related_entities",
        )
        self.assertIn("Catedral de Burgos", report["block_resolution"][0]["covered_by"])

    def test_reports_navigation_as_discarded_navigation(self):
        page = PageExtraction(
            url="https://example.com",
            title="Burgos",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://example.com",
                    title="Que hacer",
                    text="Que hacer Rutas Urbanas Rutas Saludables Ocio y Fiestas Excursiones cercanas",
                )
            ],
        )

        report = analyze_content_coverage(page, [])

        self.assertEqual(report["uncovered_candidate_blocks"], 0)
        self.assertEqual(report["status_counts"]["discarded_navigation"], 1)


if __name__ == "__main__":
    unittest.main()
