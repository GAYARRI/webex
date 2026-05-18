"""Tests for Feature 012 — evidence quality controls."""
import unittest

from src.entity_merger import _matching_blocks
from src.knowledge_base import _merge_text, merge_into_kb
from src.models import ContentBlock, Coordinates, Entity, Evidence, PageExtraction
from src.text_utils import is_boilerplate_text


class BoilerplateDetectionTests(unittest.TestCase):
    def test_visitas_pattern(self):
        self.assertTrue(is_boilerplate_text("1487 visitas"))
        self.assertTrue(is_boilerplate_text("Tiene 23 visita registradas"))

    def test_saber_mas_pattern(self):
        self.assertTrue(is_boilerplate_text("Saber más sobre esto"))
        self.assertTrue(is_boilerplate_text("saber mas información"))

    def test_ir_a_pattern(self):
        self.assertTrue(is_boilerplate_text("Ir a Catedral"))

    def test_ver_mas_pattern(self):
        self.assertTrue(is_boilerplate_text("Ver más"))
        self.assertTrue(is_boilerplate_text("Leer más detalles"))

    def test_normal_text_not_flagged(self):
        self.assertFalse(is_boilerplate_text("La Catedral de Burgos es un monumento gótico."))
        self.assertFalse(is_boilerplate_text("Descripcion A."))
        self.assertFalse(is_boilerplate_text(""))
        self.assertFalse(is_boilerplate_text(None))


class MergeTextBoilerplateTests(unittest.TestCase):
    def test_rejects_boilerplate_incoming(self):
        result = _merge_text("Catedral gótica del siglo XIII.", "1487 visitas")
        self.assertEqual(result, "Catedral gótica del siglo XIII.")

    def test_rejects_boilerplate_as_first_value(self):
        result = _merge_text("", "Saber más sobre el monumento")
        self.assertEqual(result, "")

    def test_accepts_normal_incoming(self):
        result = _merge_text("Catedral gótica.", "Construida en el siglo XIII.")
        self.assertIn("Catedral gótica", result)
        self.assertIn("Construida en el siglo XIII", result)

    def test_still_dedupes_clones(self):
        result = _merge_text("Catedral gótica.", "Catedral gótica.")
        self.assertEqual(result, "Catedral gótica.")

    def test_still_replaces_subset_with_superset(self):
        result = _merge_text("Catedral gótica", "Catedral gótica del siglo XIII.")
        self.assertEqual(result, "Catedral gótica del siglo XIII.")


class KBTypeMergeTests(unittest.TestCase):
    def test_specific_type_replaces_generic_on_enrich(self):
        """Cathedral must win over Monument+Church accumulated in a stale KB."""
        base = Entity(name="Catedral de Burgos", types=["Monument", "Church"])
        incoming = Entity(name="Catedral de Burgos", types=["Cathedral"])
        kb, _ = merge_into_kb([base], [incoming])
        self.assertEqual(kb[0].types, ["Cathedral"])

    def test_unknown_types_filtered_out_on_enrich(self):
        """HistoricalSite and TouristAttraction are not in the ontology — must be dropped."""
        base = Entity(name="Catedral de Burgos", types=["HistoricalSite", "TouristAttraction"])
        incoming = Entity(name="Catedral de Burgos", types=["Cathedral"])
        kb, _ = merge_into_kb([base], [incoming])
        self.assertNotIn("HistoricalSite", kb[0].types)
        self.assertNotIn("TouristAttraction", kb[0].types)
        self.assertIn("Cathedral", kb[0].types)


class KBImageCapTests(unittest.TestCase):
    def test_enrich_caps_images_at_max(self):
        base = Entity(
            name="Catedral de Burgos",
            images=[f"https://example.com/{i}.jpg" for i in range(8)],
        )
        incoming = Entity(
            name="Catedral de Burgos",
            images=[f"https://example.com/{i}.jpg" for i in range(8, 20)],
        )
        kb, _ = merge_into_kb([base], [incoming])
        self.assertLessEqual(len(kb[0].images), 10)

    def test_enrich_does_not_add_duplicates(self):
        base = Entity(name="Castillo", images=["https://example.com/a.jpg"])
        incoming = Entity(name="Castillo", images=["https://example.com/a.jpg", "https://example.com/b.jpg"])
        kb, _ = merge_into_kb([base], [incoming])
        self.assertEqual(kb[0].images.count("https://example.com/a.jpg"), 1)


class MatchingBlocksCapTests(unittest.TestCase):
    def _make_page(self, n_matching_blocks: int) -> PageExtraction:
        blocks = [
            ContentBlock(
                block_id=f"block-{i}",
                url="https://example.com",
                title="Catedral de Burgos",
                text=f"La Catedral de Burgos. Bloque {i}.",
            )
            for i in range(n_matching_blocks)
        ]
        return PageExtraction(
            url="https://example.com",
            title="Test",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=blocks,
        )

    def test_caps_at_five_blocks(self):
        page = self._make_page(10)
        entity = Entity(name="Catedral de Burgos")
        result = _matching_blocks(entity, page)
        self.assertLessEqual(len(result), 5)

    def test_returns_all_when_fewer_than_five(self):
        page = self._make_page(3)
        entity = Entity(name="Catedral de Burgos")
        result = _matching_blocks(entity, page)
        self.assertEqual(len(result), 3)

    def test_penalises_very_large_blocks(self):
        big_text = "Catedral de Burgos " + "palabra " * 700
        small_text = "La Catedral de Burgos es un monumento gótico."
        page = PageExtraction(
            url="https://example.com",
            title="Test",
            description=None,
            language="es",
            main_text="",
            raw_text="",
            images=[],
            status="ok",
            blocks=[
                ContentBlock(block_id="big", url="https://example.com", title="Catedral de Burgos", text=big_text),
                ContentBlock(block_id="small", url="https://example.com", title="Catedral de Burgos", text=small_text),
            ],
        )
        entity = Entity(name="Catedral de Burgos")
        result = _matching_blocks(entity, page)
        self.assertEqual(result[0].block_id, "small")


if __name__ == "__main__":
    unittest.main()
