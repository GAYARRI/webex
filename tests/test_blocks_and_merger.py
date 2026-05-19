import unittest

from src.entity_extractor import classify_entities, clean_entities, entities_from_blocks, heuristic_entities
from src.entity_merger import attach_block_evidence, merge_entities
from src.entity_text import relevant_text_for_entity
from src.models import ContentBlock, Entity, Evidence, PageExtraction
from src.web_extractor import parse_html


class BlocksAndMergerTests(unittest.TestCase):
    def test_parse_html_extracts_blocks_with_images(self):
        page = parse_html(
            "https://example.com",
            """
            <html><body>
              <section>
                <h2>Catedral de Burgos</h2>
                <p>La Catedral de Burgos es un recurso turistico patrimonial.</p>
                <img src="/catedral.jpg" alt="Catedral">
              </section>
            </body></html>
            """,
        )

        self.assertEqual(len(page.blocks), 1)
        self.assertEqual(page.blocks[0].title, "Catedral de Burgos")
        self.assertEqual(page.blocks[0].images[0]["url"], "https://example.com/catedral.jpg")

    def test_attach_block_evidence_and_merge_entities(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
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
                    text="La Catedral de Burgos es patrimonio.",
                    images=[{"url": "https://example.com/catedral-1.jpg"}],
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://example.com",
                    title="Mas sobre Catedral de Burgos",
                    text="Nueva informacion sobre la Catedral de Burgos.",
                    images=[{"url": "https://example.com/catedral-2.jpg"}],
                ),
            ],
        )
        entities = [
            Entity(name="Catedral de Burgos", images=["https://example.com/catedral-1.jpg"]),
            Entity(name="catedral de burgos", images=["https://example.com/catedral-2.jpg"]),
        ]

        entities = attach_block_evidence(entities, page)
        merged = merge_entities(entities)

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].sources), 2)
        self.assertTrue(
            any(
                "Nueva informacion sobre la Catedral de Burgos" in source.text
                for source in merged[0].sources
            )
        )
        self.assertEqual(
            sorted(merged[0].images),
            ["https://example.com/catedral-1.jpg", "https://example.com/catedral-2.jpg"],
        )

    def test_attach_block_evidence_prefers_specific_source_text(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
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
                    title="Descubre",
                    text=(
                        "Menu Catedral Camino Castillo " * 80
                        + "La Catedral de Burgos es un simbolo patrimonial."
                    ),
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://example.com",
                    title="",
                    text=(
                        "La Catedral de Burgos es un simbolo que ha dejado huella "
                        "en la historia de Espana. Su arquitectura gotica destaca."
                    ),
                ),
            ],
        )

        entities = attach_block_evidence([Entity(name="Catedral de Burgos")], page)

        self.assertIn("arquitectura gotica", entities[0].sourceText)
        self.assertNotIn("Menu Catedral Camino Castillo Menu", entities[0].sourceText)

    def test_attach_block_evidence_extracts_contact_metadata(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
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
                    title="Centro de Biodiversidad de Burgos",
                    text=(
                        "Centro de Biodiversidad de Burgos. VISITAS GUIADAS: "
                        "947 288 719. Acceso por la carretera que sube desde la avenida del Cid."
                    ),
                )
            ],
        )

        entities = attach_block_evidence([Entity(name="Centro de Biodiversidad de Burgos")], page)

        self.assertEqual(entities[0].phone, "947 288 719")
        self.assertIn("avenida del Cid", entities[0].address)
        self.assertEqual(entities[0].sources[0].metadata["phone"], "947 288 719")

    def test_attach_block_evidence_trims_mixed_dated_blocks(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
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
                    title="",
                    text=(
                        "15 de mayo de 2026 Fiesta de las Flores 2026 "
                        "Los dias 15, 16 y 17 de mayo la ciudad acoge instalaciones florales. "
                        "03 de mayo de 2026 VIVE EL ECLIPSE EN BURGOS "
                        "El 12 de agosto se podra contemplar un eclipse solar total."
                    ),
                )
            ],
        )

        entities = attach_block_evidence([Entity(name="Fiesta de las Flores 2026")], page)

        self.assertIn("instalaciones florales", entities[0].sourceText)
        self.assertNotIn("ECLIPSE", entities[0].sourceText)

    def test_relevant_text_for_entity_splits_dated_news(self):
        text = (
            "15 de mayo de 2026 Fiesta de las Flores 2026 Programa floral. "
            "03 de mayo de 2026 VIVE EL ECLIPSE EN BURGOS Actividades astronomicas."
        )

        result = relevant_text_for_entity("Fiesta de las Flores 2026", text)

        self.assertIn("Programa floral", result)
        self.assertNotIn("ECLIPSE", result)

    def test_clean_entities_rejects_url_as_entity_name(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/es/que-ver/catedral",
            title="Catedral de Burgos",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
        )
        entities = [
            Entity(
                name="https://visitaburgosciudad.es/es/que-ver/catedral",
                types=["TouristAttraction"],
                evidence="Pagina sobre la Catedral de Burgos.",
            ),
            Entity(
                name="Catedral de Burgos",
                types=[],
                evidence="La Catedral de Burgos es un recurso turistico patrimonial destacado.",
            ),
        ]

        cleaned = clean_entities(entities, page)

        self.assertEqual([entity.name for entity in cleaned], ["Catedral de Burgos"])
        self.assertEqual(cleaned[0].types, ["Cathedral"])

    def test_heuristic_entities_are_created_from_blocks_not_page_url(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/es/que-ver/catedral",
            title="https://visitaburgosciudad.es/es/que-ver/catedral",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/es/que-ver/catedral",
                    title="Catedral de Burgos",
                    text="La Catedral de Burgos es uno de los recursos patrimoniales mas relevantes.",
                )
            ],
        )

        entities = heuristic_entities(page)

        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Catedral de Burgos")
        self.assertEqual(entities[0].types, ["Cathedral"])

    def test_heuristic_entities_ignore_navigation_titles(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="Descubre",
                    text="Que ver Catedral Camino de Santiago Museo de la Evolucion Humana.",
                )
            ],
        )

        entities = heuristic_entities(page)

        self.assertEqual(entities, [])

    def test_heuristic_entities_ignore_more_navigation_titles(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="Turismo en Familia",
                    text="Turismo en Familia Saber mas Rutas Urbanas Saber mas Gastronomia Saber mas.",
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://visitaburgosciudad.es/",
                    title="Gastronomía",
                    text="Gastronomia Saber mas Ocio y Fiestas Saber mas Planifica tu viaje Saber mas.",
                ),
            ],
        )

        entities = heuristic_entities(page)

        self.assertEqual(entities, [])

    def test_block_entities_extract_named_content_after_date(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "02 de abril de 2026 Centro de Biodiversidad de Burgos "
                        "En el parque del Castillo se localiza este recurso turistico."
                    ),
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "10 de marzo de 2026 Pulsera turistica de Burgos "
                        "Con la pulsera turistica tendras acceso a los monumentos."
                    ),
                ),
            ],
        )

        entities = entities_from_blocks(page)

        self.assertEqual(
            [entity.name for entity in entities],
            ["Centro de Biodiversidad de Burgos", "Pulsera turistica de Burgos"],
        )
        self.assertEqual(entities[0].types, ["TouristAttractionSite"])
        self.assertEqual(entities[1].types, ["Tour"])

    def test_block_entities_use_relevant_text_for_mixed_news_blocks(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "15 de mayo de 2026 Fiesta de las Flores 2026 "
                        "La ciudad acoge instalaciones florales. "
                        "03 de mayo de 2026 VIVE EL ECLIPSE EN BURGOS "
                        "Actividades de observacion astronomica."
                    ),
                ),
            ],
        )

        entities = entities_from_blocks(page)

        self.assertEqual(entities[0].name, "Fiesta de las Flores 2026")
        self.assertIn("instalaciones florales", entities[0].sourceText)
        self.assertNotIn("ECLIPSE", entities[0].sourceText)

    def test_block_entities_trim_long_news_leads(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "30 de marzo de 2026 Burgos desde el Castillo "
                        "Toda urbe medieval que se precie tiene un castillo."
                    ),
                ),
                ContentBlock(
                    block_id="block-2",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "18 de febrero de 2026 Semana Santa 2026 en Burgos "
                        "DESCARGA AQUI LA PROGRAMACION COMPLETA."
                    ),
                ),
            ],
        )

        entities = entities_from_blocks(page)

        self.assertEqual(
            [entity.name for entity in entities],
            ["Burgos desde el Castillo", "Semana Santa 2026 en Burgos"],
        )

    def test_type_inference_prioritizes_entity_name_over_context(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(
                    block_id="block-1",
                    url="https://visitaburgosciudad.es/",
                    title="",
                    text=(
                        "30 de marzo de 2026 Burgos desde el Castillo "
                        "El mirador del Castillo ofrece una panoramica de la Catedral."
                    ),
                )
            ],
        )

        entities = entities_from_blocks(page)

        self.assertEqual(entities[0].types, ["Castle"])

    def test_type_normalization_corrects_contextually_weak_existing_type(self):
        page = PageExtraction(
            url="https://visitaburgosciudad.es/",
            title="Inicio",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
        )
        entity = Entity(
            name="Burgos desde el Castillo",
            types=["Church"],
            shortDescription="Mirador del Castillo con panoramica de la Catedral.",
            evidence="Ruta panoramica desde la fortaleza del Castillo.",
        )

        cleaned = clean_entities([entity], page)

        self.assertEqual(cleaned[0].types, ["Castle"])

    def test_final_classification_corrects_wrong_extracted_type(self):
        """Strong Wikipedia evidence (title + text, confidence >= 60) overrides a wrong initial type."""
        entity = Entity(
            name="San Nicolas de Bari",
            types=["Event"],
            shortDescription="Recurso turistico de Burgos.",
        )
        entity.sources = [
            Evidence(
                url="https://es.wikipedia.org/wiki/Iglesia_de_San_Nicolas_de_Bari",
                block_id="Q5910998",
                source_type="wikipedia",
                title="Iglesia de San Nicolas de Bari",
                text="La iglesia de San Nicolas de Bari es un templo historico de Burgos.",
            )
        ]

        classify_entities([entity])

        # Wikipedia title (40) + text (20) = confidence 60 → Church overrides the wrong Event type.
        self.assertEqual(entity.type, "Church")
        self.assertEqual(entity.types, ["Church", "Event"])
        self.assertEqual(entity.classificationEvidence["selected"], "Church")

    def test_final_classification_assigns_from_name_when_no_type(self):
        """Entities with no type after extraction get a type from the name, not from sources."""
        entity = Entity(
            name="Catedral de Burgos",
            types=[],
        )
        entity.sources = [
            Evidence(
                url="https://es.wikipedia.org/wiki/Catedral_de_Burgos",
                block_id="Q190732",
                source_type="wikipedia",
                title="Catedral de Burgos",
                text="La catedral gotica de Burgos.",
            )
        ]

        classify_entities([entity])

        self.assertEqual(entity.type, "Cathedral")
        self.assertEqual(entity.types, ["Cathedral"])

    def test_cathedral_keyword_does_not_override_route_or_viewpoint_name(self):
        entities = [
            Entity(name="Ruta de los miradores de la Catedral de Burgos", types=["Cathedral"]),
            Entity(name="Miradores de la Catedral", types=["Cathedral"]),
            Entity(name="La Catedral y su entorno", types=["Cathedral"]),
            Entity(name="Conjunto Catedralicio de Burgos", types=["Cathedral"]),
        ]

        classify_entities(entities)

        self.assertEqual(entities[0].type, "Route")
        self.assertEqual(entities[1].type, "UrbanViewPoint")
        self.assertEqual(entities[2].type, "Route")
        self.assertEqual(entities[3].type, "TouristAttractionSite")
        self.assertEqual(entities[0].types, ["Route", "Cathedral"])
        self.assertEqual(entities[1].types, ["UrbanViewPoint", "Cathedral"])
        self.assertEqual(entities[2].types, ["Route", "Cathedral"])
        self.assertEqual(entities[3].types, ["TouristAttractionSite", "Cathedral"])

    def test_clean_entities_moves_image_urls_out_of_related_urls(self):
        page = PageExtraction(
            url="https://example.com",
            title="Example",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
        )
        entity = Entity(
            name="Catedral de Burgos",
            relatedUrls=[
                "https://example.com/catedral.jpg",
                "https://example.com/ficha-catedral",
            ],
            url="https://example.com/hero.png",
            evidence="La Catedral de Burgos es un recurso turistico patrimonial destacado.",
        )

        cleaned = clean_entities([entity], page)

        self.assertEqual(cleaned[0].relatedUrls, ["https://example.com/ficha-catedral"])
        self.assertEqual(
            cleaned[0].images,
            ["https://example.com/hero.png", "https://example.com/catedral.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
