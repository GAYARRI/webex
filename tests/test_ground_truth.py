import unittest

from src.ground_truth import compare_entities
from src.models import Entity
from src.text_utils import normalize_key


class GroundTruthTests(unittest.TestCase):
    def test_normalize_key_removes_accents_and_case(self):
        self.assertEqual(normalize_key("Real Alcázar"), "real alcazar")

    def test_compare_entities_reports_found_missing_and_additional(self):
        expected = [
            Entity(name="Real Alcazar", types=["Alcazar"]),
            Entity(name="Canal de Castilla", types=["TouristAttraction"]),
        ]
        actual = [
            Entity(name="real alcázar", types=["Alcazar"]),
            Entity(name="Otra entidad", types=["Event"]),
        ]

        report = compare_entities(actual, expected)

        self.assertEqual(report["purpose"], "canonical_examples_regression")
        self.assertIn("no una lista exhaustiva", report["coverage_warning"])
        self.assertEqual(report["found_count"], 1)
        self.assertEqual(report["missing_count"], 1)
        self.assertEqual(report["additional_count"], 1)
        self.assertEqual(report["found"], ["Real Alcazar"])
        self.assertEqual(report["missing"], ["Canal de Castilla"])
        self.assertEqual(report["additional"], ["Otra entidad"])
        self.assertTrue(report["type_matches"][0]["matches"])

    def test_compare_entities_warns_when_domain_is_not_in_fixture(self):
        expected = [
            Entity(
                name="Real Alcazar",
                types=["Alcazar"],
                url="https://visitasevilla.es/real-alcazar-de-sevilla/",
            )
        ]
        actual = [Entity(name="Catedral de Burgos", types=["Cathedral"])]

        report = compare_entities(
            actual,
            expected,
            source_url="https://www.aytoburgos.es/turismo",
        )

        self.assertEqual(report["expected_count"], 0)
        self.assertEqual(report["original_expected_count"], 1)
        self.assertEqual(report["actual_count"], 1)
        self.assertIn("no sirve para medir cobertura exhaustiva", report["warning"])


if __name__ == "__main__":
    unittest.main()
