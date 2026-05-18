import unittest

from src.entity_resolver import resolve_into_kb, _resolution_score
from src.knowledge_base import _merge_text
from src.models import Coordinates, Entity, Evidence


def _entity(name, *, wikidata="", lat=None, lng=None, address="", types=None, desc=""):
    return Entity(
        name=name,
        wikidataId=wikidata,
        coordinates=Coordinates(lat=lat, lng=lng, confidence=0.9 if lat else None),
        address=address,
        types=types or [],
        shortDescription=desc,
        longDescription=desc,
    )


class MergeTextTests(unittest.TestCase):
    def test_returns_incoming_when_base_empty(self):
        self.assertEqual(_merge_text("", "nuevo texto"), "nuevo texto")

    def test_returns_base_when_incoming_empty(self):
        self.assertEqual(_merge_text("texto base", ""), "texto base")

    def test_discards_clone(self):
        self.assertEqual(_merge_text("El texto completo aqui", "completo"), "El texto completo aqui")

    def test_replaces_subset_with_superset(self):
        self.assertEqual(_merge_text("corto", "corto con mas informacion"), "corto con mas informacion")

    def test_concatenates_distinct_texts(self):
        result = _merge_text("Descripcion A.", "Descripcion B.")
        self.assertIn("Descripcion A.", result)
        self.assertIn("Descripcion B.", result)


class ResolutionScoreTests(unittest.TestCase):
    def test_same_wikidata_is_definitive(self):
        a = _entity("Catedral de Burgos", wikidata="Q123")
        b = _entity("La Catedral", wikidata="Q123")
        score, signals = _resolution_score(a, b)
        self.assertEqual(score, 1.0)
        self.assertIn("wikidata_id", signals)

    def test_different_wikidata_scores_zero(self):
        a = _entity("Catedral", wikidata="Q123")
        b = _entity("Museo", wikidata="Q456")
        score, _ = _resolution_score(a, b)
        self.assertLess(score, 0.70)

    def test_coordinates_far_apart_returns_zero(self):
        a = _entity("Catedral de Burgos", lat=42.340, lng=-3.699)
        b = _entity("Catedral de Madrid",  lat=40.416, lng=-3.703)
        score, signals = _resolution_score(a, b)
        self.assertEqual(score, 0.0)
        self.assertIn("barrier_distance", signals)

    def test_coordinates_proximity_adds_signal(self):
        a = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        b = _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Cathedral"])
        score, signals = _resolution_score(a, b)
        self.assertIn("coordinates_proximity", signals)
        self.assertGreaterEqual(score, 0.70)

    def test_name_containment_with_proximity_merges(self):
        a = _entity("Camino de Santiago por Burgos", lat=42.3408, lng=-3.6997, types=["Route"])
        b = _entity("Camino de Santiago",            lat=42.3410, lng=-3.6995, types=["Route"])
        score, signals = _resolution_score(a, b)
        self.assertIn("name_containment", signals)
        self.assertGreaterEqual(score, 0.70)

    def test_address_match_adds_signal(self):
        a = _entity("Catedral de Burgos", address="Plaza de Santa Maria, Burgos")
        b = _entity("La Catedral",        address="Plaza de Santa Maria, Burgos")
        score, signals = _resolution_score(a, b)
        self.assertIn("address_match", signals)

    def test_single_token_name_below_threshold_without_location(self):
        a = _entity("Museo")
        b = _entity("Museo de Arte Contemporaneo de Burgos")
        score, _ = _resolution_score(a, b)
        self.assertLess(score, 0.70)


class ResolveIntoKbTests(unittest.TestCase):
    def test_exact_name_match_enriches(self):
        base = _entity("Catedral de Burgos", desc="Descripcion A.")
        incoming = _entity("catedral de burgos", desc="Descripcion B.")
        kb, report = resolve_into_kb([base], [incoming])
        self.assertEqual(len(kb), 1)
        self.assertEqual(report["enriched"], 1)
        self.assertEqual(report["added"], 0)

    def test_fuzzy_name_with_coords_merges(self):
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Cathedral"])
        kb, report = resolve_into_kb([base], [incoming])
        self.assertEqual(len(kb), 1)
        self.assertEqual(report["enriched"], 1)

    def test_different_entities_create_new(self):
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997)
        incoming = _entity("Castillo de Burgos", lat=42.3510, lng=-3.6950)
        kb, report = resolve_into_kb([base], [incoming])
        self.assertEqual(len(kb), 2)
        self.assertEqual(report["added"], 1)

    def test_wikidata_propagates_to_incoming(self):
        base     = _entity("Catedral de Burgos", wikidata="Q123", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        incoming = _entity("La Catedral",                         lat=42.3409, lng=-3.6998, types=["Cathedral"])
        kb, _ = resolve_into_kb([base], [incoming])
        # Only one entity in KB, base still has wikidataId
        self.assertEqual(kb[0].wikidataId, "Q123")

    def test_descriptions_accumulate_not_replace(self):
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997,
                           types=["Cathedral"], desc="Descripcion original completa.")
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998,
                           types=["Cathedral"], desc="Informacion adicional nueva.")
        kb, _ = resolve_into_kb([base], [incoming])
        self.assertIn("Descripcion original completa.", kb[0].longDescription)
        self.assertIn("Informacion adicional nueva.", kb[0].longDescription)

    def test_clone_description_not_duplicated(self):
        text = "La catedral es un recurso patrimonial."
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997,
                           types=["Cathedral"], desc=text)
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998,
                           types=["Cathedral"], desc=text)
        kb, _ = resolve_into_kb([base], [incoming])
        self.assertEqual(kb[0].longDescription.count(text), 1)

    def test_sources_traceability_preserved(self):
        src_a = Evidence(url="https://a.com", block_id="b1",
                        metadata={"page_url": "https://a.com"})
        src_b = Evidence(url="https://b.com", block_id="b2",
                        metadata={"page_url": "https://b.com"})
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        base.sources = [src_a]
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Cathedral"])
        incoming.sources = [src_b]
        kb, _ = resolve_into_kb([base], [incoming])
        page_urls = {s.metadata.get("page_url") for s in kb[0].sources}
        self.assertIn("https://a.com", page_urls)
        self.assertIn("https://b.com", page_urls)

    def test_report_includes_resolved_pairs(self):
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Cathedral"])
        _, report = resolve_into_kb([base], [incoming])
        self.assertEqual(len(report["resolved_pairs"]), 1)
        pair = report["resolved_pairs"][0]
        self.assertIn("signals", pair)
        self.assertIn("score", pair)

    def test_threshold_respected(self):
        # proximity(0.55) + containment(0.30) = 0.85 → merges at 0.70, not at 0.90
        base     = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        incoming = _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Monument"])
        kb_low,  _ = resolve_into_kb([base], [incoming], threshold=0.70)
        self.assertEqual(len(kb_low), 1)   # merges at 0.70
        base2    = _entity("Catedral de Burgos", lat=42.3408, lng=-3.6997, types=["Cathedral"])
        incoming2= _entity("La Catedral",        lat=42.3409, lng=-3.6998, types=["Monument"])
        kb_high, _ = resolve_into_kb([base2], [incoming2], threshold=0.90)
        self.assertEqual(len(kb_high), 2)  # does not merge at 0.90


if __name__ == "__main__":
    unittest.main()
