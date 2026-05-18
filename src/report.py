"""
Report generation: Markdown output and entity-type counts.

Standalone usage:
    python -m src.report <kb_file.json>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def count_by_type(entities: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entity in entities:
        for t in entity.get("types") or []:
            if t:
                counts[t] += 1
    return dict(counts.most_common())


def to_markdown(
    entities: list[dict[str, Any]],
    *,
    domain: str = "",
    pages_processed: int = 0,
    extracted_at: str = "",
) -> str:
    ts = extracted_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header_parts = [f"Generado: {ts}"]
    if pages_processed:
        header_parts.append(f"{pages_processed} páginas procesadas")
    header_parts.append(f"{len(entities)} entidades")

    lines: list[str] = [
        f"# Base de conocimiento turística{' — ' + domain if domain else ''}",
        "",
        f"*{' · '.join(header_parts)}*",
        "",
        "---",
        "",
    ]

    # Type summary table
    counts = count_by_type(entities)
    if counts:
        lines += [
            "## Resumen por tipo",
            "",
            "| Tipo | Entidades |",
            "|------|-----------|",
        ]
        for type_name, count in counts.items():
            lines.append(f"| {type_name} | {count} |")
        lines += ["", "---", ""]

    # Entity cards
    lines.append("## Entidades")
    lines.append("")
    for entity in entities:
        name = entity.get("name") or "Sin nombre"
        types = ", ".join(entity.get("types") or []) or "—"
        short_desc = (entity.get("shortDescription") or "").strip()
        coords = entity.get("coordinates") or {}
        lat = coords.get("lat")
        lng = coords.get("lng")
        address = (entity.get("address") or "").strip()
        images = entity.get("images") or []
        sources = entity.get("sources") or []
        wikidata = (entity.get("wikidataId") or "").strip()

        # Count distinct page_url values in sources
        page_urls = {
            s.get("metadata", {}).get("page_url")
            for s in sources
            if isinstance(s, dict) and s.get("metadata", {}).get("page_url")
        }

        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"**Tipo:** {types}  ")
        if short_desc:
            lines.append(f"**Descripción:** {short_desc[:300]}  ")
        if lat is not None and lng is not None:
            conf = coords.get("confidence")
            conf_str = f" *(confianza: {conf:.2f})*" if conf is not None else ""
            lines.append(f"**Coordenadas:** {lat}, {lng}{conf_str}  ")
        if address:
            lines.append(f"**Dirección:** {address}  ")
        if images:
            lines.append(f"**Imágenes:** {len(images)}  ")
        if sources:
            pages_str = f" · {len(page_urls)} página{'s' if len(page_urls) != 1 else ''}" if page_urls else ""
            lines.append(f"**Fuentes:** {len(sources)} evidencias{pages_str}  ")
        if wikidata:
            lines.append(f"**Wikidata:** {wikidata}  ")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def print_type_counts(kb_path: str) -> None:
    path = Path(kb_path)
    if not path.exists():
        print(f"Fichero no encontrado: {kb_path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    entities = data.get("entities", [])
    counts = count_by_type(entities)
    if not counts:
        print("No hay entidades con tipo en la KB.")
        return
    max_len = max(len(t) for t in counts)
    for type_name, count in counts.items():
        print(f"{type_name:<{max_len + 2}} {count}")
    print(f"{'─' * (max_len + 8)}")
    print(f"{'Total':<{max_len + 2}} {len(entities)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m src.report <kb_file.json>", file=sys.stderr)
        sys.exit(1)
    print_type_counts(sys.argv[1])
