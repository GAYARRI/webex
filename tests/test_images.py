import unittest

from src.images import enrich_entities_images, match_images_for_entity
from src.models import Entity, PageExtraction


class ImageTests(unittest.TestCase):
    def test_matches_image_by_url_slug(self):
        page = _page(
            [
                {
                    "url": "https://example.com/documents/catedral104-vidriera-entrada",
                    "alt": "Descripcion de la imagen",
                    "source": "page",
                }
            ]
        )
        entity = Entity(name="Catedral de Burgos", types=["monumento"])

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, ["https://example.com/documents/catedral104-vidriera-entrada"])

    def test_filters_generic_social_images(self):
        page = _page(
            [
                {"url": "https://example.com/facebook.png", "alt": "", "source": "page"},
                {"url": "https://example.com/castillo-burgos.jpg", "alt": "", "source": "page"},
            ]
        )
        entity = Entity(name="Castillo de Burgos")

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, ["https://example.com/castillo-burgos.jpg"])

    def test_discards_existing_images_without_name_match_in_url(self):
        page = _page(
            [
                {"url": "https://example.com/centro-biodiversidad-1", "alt": "", "source": "page"},
            ]
        )
        entity = Entity(name="Centro de Biodiversidad de Burgos", images=["https://example.com/manual.jpg"])

        enrich_entities_images([entity], page)

        self.assertNotIn("https://example.com/manual.jpg", entity.images)
        self.assertIn("https://example.com/centro-biodiversidad-1", entity.images)

    def test_does_not_match_only_generic_centro_word(self):
        page = _page(
            [
                {"url": "https://example.com/centro-biodiversidad-1", "alt": "", "source": "page"},
            ]
        )
        entity = Entity(name="Centro de Arte Caja de Burgos")

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_ignores_oversized_global_context(self):
        # Context longer than _CONTEXT_MAX_WORDS words is treated as global noise and scored 0.
        long_context = " ".join(["Catedral de Burgos"] + ["ruido"] * 210)
        page = _page(
            [
                {
                    "url": "https://example.com/imagen-generica.jpg",
                    "alt": "",
                    "source": "page",
                    "context": long_context,
                }
            ]
        )
        entity = Entity(name="Catedral de Burgos", types=["monumento"])

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_filters_app_store_images(self):
        page = _page(
            [
                {
                    "url": "https://example.com/googleplay-en-3",
                    "alt": "",
                    "source": "page",
                    "context": "Camino de Santiago",
                }
            ]
        )
        entity = Entity(name="Camino de Santiago")

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_context_with_entity_name_is_not_enough_without_url_match(self):
        """Image assignment requires an explicit entity-name signal in the image URL."""
        page = _page(
            [
                {
                    "url": "https://example.com/imagen-generica.jpg",
                    "alt": "",
                    "source": "page",
                    "index": "1",
                    "context": "La Catedral de Burgos es el principal monumento gotico de la ciudad.",
                },
            ]
        )
        entity = Entity(name="Catedral de Burgos", types=["monumento"])

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_alt_text_alone_is_sufficient_for_match(self):
        """Alt text describing the entity is enough even when the URL slug is opaque."""
        page = _page(
            [
                {
                    "url": "https://example.com/imagen-generica.jpg",
                    "alt": "Catedral de Burgos",
                    "source": "page",
                },
            ]
        )
        entity = Entity(name="Catedral de Burgos", types=["monumento"])

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, ["https://example.com/imagen-generica.jpg"])

    def test_unrelated_alt_text_is_rejected(self):
        """Alt text that does not mention the entity name produces no match."""
        page = _page(
            [
                {
                    "url": "https://example.com/imagen-generica.jpg",
                    "alt": "Vista panorámica del río",
                    "source": "page",
                },
            ]
        )
        entity = Entity(name="Catedral de Burgos", types=["monumento"])

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_context_without_entity_name_is_rejected(self):
        """Images whose context does not mention any name keyword are rejected."""
        page = _page(
            [
                {
                    "url": "https://example.com/imagen-generica.jpg",
                    "alt": "",
                    "source": "page",
                    "context": "Visita el centro historico",
                },
            ]
        )
        entity = Entity(name="Catedral de Burgos")

        matches = match_images_for_entity(entity, page)

        self.assertEqual(matches, [])

    def test_entity_images_are_deduplicated(self):
        page = _page(
            [
                {
                    "url": "https://example.com/catedral.jpg",
                    "alt": "Catedral",
                    "source": "page",
                    "context": "Catedral de Burgos",
                },
            ]
        )
        entity = Entity(name="Catedral de Burgos", images=["https://example.com/catedral.jpg"])

        enrich_entities_images([entity], page)

        self.assertEqual(entity.images, ["https://example.com/catedral.jpg"])


def _page(images):
    return PageExtraction(
        url="https://example.com",
        title="Example",
        description=None,
        language="es",
        main_text="Texto",
        raw_text="Texto",
        images=images,
        status="ok",
    )


if __name__ == "__main__":
    unittest.main()
