import unittest

from src.models import Coordinates, Entity, Evidence, as_list


class ModelTests(unittest.TestCase):
    def test_as_list_normalizes_empty_and_scalar_values(self):
        self.assertEqual(as_list(None), [])
        self.assertEqual(as_list(""), [])
        self.assertEqual(as_list("x"), ["x"])
        self.assertEqual(as_list(["x"]), ["x"])

    def test_entity_accepts_ground_truth_shapes(self):
        entity = Entity.from_dict(
            {
                "name": "Real Alcazar",
                "types": ["Alcazar"],
                "relatedUrls": "https://example.com/related",
                "images": "https://example.com/image.jpg",
                "coordinates": {"lat": 1.0, "lng": 2.0},
                "sourceText": "Texto del bloque",
            }
        )

        self.assertEqual(entity.name, "Real Alcazar")
        self.assertEqual(entity.relatedUrls, ["https://example.com/related"])
        self.assertEqual(entity.images, ["https://example.com/image.jpg"])
        self.assertEqual(entity.coordinates.lat, 1.0)
        self.assertEqual(entity.coordinates.lng, 2.0)
        self.assertEqual(entity.sourceText, "Texto del bloque")

    def test_entity_accepts_long_description_typo(self):
        entity = Entity.from_dict({"name": "X", "longDescriptionb": "texto"})

        self.assertEqual(entity.longDescription, "texto")

    def test_evidence_accepts_external_source_shape(self):
        evidence = Evidence.from_dict(
            {
                "url": "https://www.wikidata.org/wiki/Q744420",
                "block_id": "Q744420",
                "source_type": "wikidata",
                "title": "Catedral de Burgos",
                "text": "catedral gotica",
                "images": ["https://commons.wikimedia.org/wiki/Special:FilePath/x.jpg"],
                "coordinates": {"lat": 42.0, "lng": -3.0, "source": "wikidata"},
                "metadata": {"wikidataId": "Q744420"},
            }
        )

        self.assertEqual(evidence.source_type, "wikidata")
        self.assertIsInstance(evidence.coordinates, Coordinates)
        self.assertEqual(evidence.metadata["wikidataId"], "Q744420")


if __name__ == "__main__":
    unittest.main()
