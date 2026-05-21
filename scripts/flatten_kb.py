"""Aplica el proceso de flatten a un fichero KB JSON existente."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.ai_client import configured_model
from src.flattener import flatten_entities


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Aplana un KB JSON: summary unificado + imágenes verificadas.")
    parser.add_argument("input", help="Ruta al fichero KB JSON de entrada.")
    parser.add_argument("output", help="Ruta al fichero JSON de salida.")
    parser.add_argument("--no-ai", action="store_true", help="Usa merge inteligente en vez de llamadas a OpenAI.")
    parser.add_argument("--quiet", action="store_true", help="Sin progreso en stderr.")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    entities = data.get("entities", [])
    if not entities:
        print("No hay entidades en el fichero.", file=sys.stderr)
        sys.exit(1)

    model = configured_model() if not args.no_ai else None
    use_ai = not args.no_ai

    if not args.quiet:
        mode = f"AI ({model})" if use_ai else "merge inteligente (sin AI)"
        print(f"Aplanando {len(entities)} entidades — modo: {mode}", file=sys.stderr, flush=True)

    flat = flatten_entities(entities, use_ai=use_ai, model=model, quiet=args.quiet)
    data["entities"] = flat

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en: {out_path}  ({out_path.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
