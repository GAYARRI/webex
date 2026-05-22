from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.virtuoso_exporter import ExportDefaults, VirtuosoSchema, export_entities, load_entities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convierte outputs de entidades Webex a payloads GraphQL para Virtuoso."
    )
    parser.add_argument("input", help="JSON generado por el pipeline actual.")
    parser.add_argument("--introspection", default="Introspection.json", help="Ruta al introspection.json.")
    parser.add_argument("--output", required=True, help="Ruta del JSON de payloads GraphQL.")
    parser.add_argument("--dti", required=True, help="Valor dti requerido por las mutations.")
    parser.add_argument("--org", default="", help="Valor org opcional para las mutations.")
    parser.add_argument("--lang", default="es", help="Idioma de literales multilingues.")
    parser.add_argument("--country", default="España", help="Pais por defecto para LocationInput.")
    parser.add_argument("--autonomous-community", default="", help="Comunidad autonoma por defecto.")
    parser.add_argument("--province", default="", help="Provincia por defecto.")
    parser.add_argument("--municipality", default="", help="Municipio por defecto.")
    parser.add_argument("--postal-code", default="", help="Codigo postal por defecto.")
    parser.add_argument("--external-id-prefix", default="webex", help="Prefijo para externalId estable.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    schema = VirtuosoSchema.from_file(args.introspection)
    entities = load_entities(args.input)
    defaults = ExportDefaults(
        dti=args.dti,
        org=args.org,
        lang=args.lang,
        country=args.country,
        autonomous_community=args.autonomous_community,
        province=args.province,
        municipality=args.municipality,
        postal_code=args.postal_code,
        external_id_prefix=args.external_id_prefix,
    )
    payloads = export_entities(entities, schema, defaults)
    output = {
        "source": args.input,
        "count": len(payloads),
        "warningCount": sum(len(item.warnings) for item in payloads),
        "payloads": [item.to_dict() for item in payloads],
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Payloads GraphQL guardados en {out_path} ({len(payloads)} entidades)")
    if output["warningCount"]:
        print(f"Warnings: {output['warningCount']}")


if __name__ == "__main__":
    main()
