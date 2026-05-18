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


def count_by_page(entities: list[dict[str, Any]]) -> dict[str, int]:
    """Return number of entities that have at least one source from each page URL."""
    counts: Counter[str] = Counter()
    for entity in entities:
        seen_pages: set[str] = set()
        for source in entity.get("sources") or []:
            if not isinstance(source, dict):
                continue
            # Prefer explicit metadata stamp; fall back to source url for legacy KB data
            page_url = (
                source.get("metadata", {}).get("page_url")
                or source.get("url")
                or ""
            )
            if page_url and page_url not in seen_pages:
                seen_pages.add(page_url)
                counts[page_url] += 1
    return dict(counts.most_common())


def zero_contribution_pages(pages_report: list[dict[str, Any]]) -> list[str]:
    """Return URLs of pages that were crawled successfully but added no entities."""
    return [
        p["url"]
        for p in pages_report
        if p.get("status") == "ok"
        and p.get("added", 0) == 0
        and p.get("enriched", 0) == 0
    ]


def print_type_counts(report_path: str) -> None:
    path = Path(report_path)
    if not path.exists():
        print(f"Fichero no encontrado: {report_path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    entities = data.get("entities", [])

    counts = count_by_type(entities)
    print("=== Entidades por clase ===")
    if not counts:
        print("  (sin datos)")
    else:
        max_len = max(len(t) for t in counts)
        for type_name, count in counts.items():
            print(f"{type_name:<{max_len + 2}} {count}")
        print("-" * (max_len + 8))
        print(f"{'Total':<{max_len + 2}} {len(entities)}")

    print()
    page_counts = count_by_page(entities)
    print("=== Entidades por pagina de origen ===")
    if not page_counts:
        print("  (sin datos de pagina)")
    else:
        max_url = max(len(u) for u in page_counts)
        for page_url, count in page_counts.items():
            print(f"{page_url:<{max_url + 2}} {count}")

    pages_report = (
        data.get("pages")
        or data.get("crawl_report", {}).get("pages")
        or data.get("batch_report", {}).get("pages")
        or []
    )
    if pages_report:
        zero_pages = zero_contribution_pages(pages_report)
        print()
        print("=== Paginas sin aportacion ===")
        if not zero_pages:
            print("  (todas las paginas aportaron entidades)")
        else:
            for url in zero_pages:
                print(f"  {url}")
            print(f"  Total: {len(zero_pages)} de {len(pages_report)} paginas procesadas")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m src.report <fichero.json>", file=sys.stderr)
        sys.exit(1)
    print_type_counts(sys.argv[1])
