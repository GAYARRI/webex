import unittest
import argparse
import json
import shutil
import uuid
from pathlib import Path

from src.main import _write_virtuoso_output
from src.models import Coordinates, Entity
from src.virtuoso_exporter import ExportDefaults, VirtuosoSchema, entity_to_payload


def _schema() -> VirtuosoSchema:
    return VirtuosoSchema(
        {
            "data": {
                "__schema": {
                    "mutationType": {"name": "Mutation"},
                    "types": [
                        {
                            "name": "Mutation",
                            "fields": [
                                {"name": "createMuseum", "args": []},
                                {"name": "createTourismentity", "args": []},
                            ],
                        },
                        {
                            "name": "MuseumInput",
                            "inputFields": [
                                {"name": "name", "type": {"kind": "NON_NULL"}},
                                {"name": "hasDescription", "type": {"kind": "NON_NULL"}},
                            ],
                        },
                        {
                            "name": "TourismEntityInput",
                            "inputFields": [
                                {"name": "name", "type": {"kind": "NON_NULL"}},
                                {"name": "hasDescription", "type": {"kind": "NON_NULL"}},
                            ],
                        },
                    ],
                }
            }
        }
    )


class VirtuosoExporterTests(unittest.TestCase):
    def test_entity_maps_to_specific_create_mutation(self):
        entity = Entity(
            name="Museo de Murcia",
            type="Museum",
            sourceUrl="https://example.com/museo",
            phone="968000000",
            email="info@example.com",
            coordinates=Coordinates(lat=37.98, lng=-1.13),
            shortDescription="Museo regional",
            longDescription="Museo regional de Murcia",
            images=["https://example.com/main.jpg", "https://example.com/second.jpg"],
            wikidataId="Q1",
        )

        payload = entity_to_payload(
            entity,
            _schema(),
            ExportDefaults(
                dti="dti-test",
                org="org-test",
                autonomous_community="Region de Murcia",
                province="Murcia",
                municipality="Murcia",
                postal_code="30001",
            ),
        )

        self.assertEqual(payload.mutation, "createMuseum")
        self.assertEqual(payload.class_name, "Museum")
        self.assertIn("mutation CreateMuseum", payload.query)
        self.assertIn("$input: MuseumRefInput!", payload.query)
        self.assertEqual(payload.variables["dti"], "dti-test")
        self.assertEqual(payload.variables["org"], "org-test")
        obj = payload.variables["input"]["object"]
        self.assertEqual(obj["name"], [{"value": "Museo de Murcia", "lang": "es"}])
        self.assertEqual(obj["hasDescription"][0]["object"]["shortDescription"][0]["value"], "Museo regional")
        self.assertEqual(obj["hasContactPoint"][0]["object"]["telephone"], ["968000000"])
        self.assertEqual(obj["hasLocation"][0]["object"]["long"], -1.13)
        self.assertEqual(obj["hasMultimedia"]["object"]["mainImage"], "https://example.com/main.jpg")
        self.assertIn("https://www.wikidata.org/wiki/Q1", obj["relatedTo"])
        self.assertEqual(payload.warnings, [])

    def test_unknown_type_falls_back_to_tourism_entity(self):
        entity = Entity(name="Entidad rara", type="UnknownThing")

        payload = entity_to_payload(entity, _schema(), ExportDefaults(dti="dti-test"))

        self.assertEqual(payload.mutation, "createTourismentity")
        self.assertEqual(payload.class_name, "TourismEntity")
        self.assertTrue(any("No GraphQL class found" in warning for warning in payload.warnings))

    def test_main_helper_writes_virtuoso_payloads_from_result(self):
        tmpdir = Path(".test_tmp") / f"virtuoso-{uuid.uuid4().hex}"
        tmpdir.mkdir(parents=True, exist_ok=False)
        try:
            schema_path = tmpdir / "introspection.json"
            output_path = Path(tmpdir) / "payloads.json"
            schema_path.write_text(json.dumps({
                "data": {
                    "__schema": {
                        "mutationType": {"name": "Mutation"},
                        "types": [
                            {
                                "name": "Mutation",
                                "fields": [
                                    {"name": "createMuseum", "args": []},
                                    {"name": "createTourismentity", "args": []},
                                ],
                            },
                            {
                                "name": "MuseumInput",
                                "inputFields": [
                                    {"name": "name", "type": {"kind": "NON_NULL"}},
                                    {"name": "hasDescription", "type": {"kind": "NON_NULL"}},
                                ],
                            },
                        ],
                    }
                }
            }), encoding="utf-8")
            args = argparse.Namespace(
                output="output/source.json",
                url="",
                virtuoso_introspection=str(schema_path),
                virtuoso_dti="dti-test",
                virtuoso_org="",
                virtuoso_lang="es",
                virtuoso_country="España",
                virtuoso_autonomous_community="Region de Murcia",
                virtuoso_province="Murcia",
                virtuoso_municipality="Murcia",
                virtuoso_postal_code="30001",
                virtuoso_external_id_prefix="webex",
            )
            result = {
                "entities": [
                    {
                        "name": "Museo",
                        "type": "Museum",
                        "shortDescription": "Descripcion",
                    }
                ]
            }

            output = _write_virtuoso_output(result, args, str(output_path))

            self.assertEqual(output["count"], 1)
            self.assertTrue(output_path.exists())
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["payloads"][0]["mutation"], "createMuseum")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            try:
                tmpdir.parent.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
