# Feature 013: Trazabilidad de evidencias por URL de origen

## Estado

Implementado

## Contexto

Cada entidad en la KB acumula evidencias (`sources`) de múltiples páginas durante
el crawl. Sin trazabilidad de origen es imposible evaluar la idoneidad de una
evidencia ni entender por qué está asociada a una entidad.

## Requisito

Cada evidencia de una entidad debe exponer explícitamente la URL de la página
de la que proviene, visible tanto en la KB como en el JSON de salida.

## Solución

### Campo `page_url` en `Evidence`

Se añade el campo `page_url: str = ""` al dataclass `Evidence` (`models.py`).

- `tag_sources_with_page_url` escribe el campo además del sello en `metadata`
  (backward compatibility con KB antiguas).
- `Evidence.from_dict` lee `page_url` con fallback en cascada:
  1. campo explícito `page_url`
  2. `metadata["page_url"]` (sello legacy)
  3. `url` (el propio URL del bloque)

### `sources` en el JSON de salida

`_golden_entity` incluye ahora una lista `sources` con representación compacta
por evidencia:

```json
{
  "page_url":    "https://visitaburgosciudad.es/que-ver/catedral",
  "source_type": "page_block",
  "title":       "Catedral de Burgos",
  "text":        "La Catedral de Burgos es patrimonio... (máx. 500 chars)",
  "images":      ["https://..."]
}
```

El campo `text` se trunca a 500 caracteres para mantener el output manejable.

## Archivos modificados

| Fichero | Cambio |
|---------|--------|
| `src/models.py` | Campo `page_url` en `Evidence`; `from_dict` con fallback en cascada |
| `src/knowledge_base.py` | `tag_sources_with_page_url` escribe campo explícito |
| `src/main.py` | `_golden_entity` incluye `sources`; nueva función `_compact_source` |
| `tests/test_output_formats.py` | 5 tests nuevos en `SourceTraceabilityTests` |

## Tests

```
tests/test_output_formats.py — SourceTraceabilityTests (5 tests)
  test_evidence_page_url_field_explicit
  test_evidence_from_dict_reads_page_url_field
  test_evidence_from_dict_falls_back_to_metadata_page_url
  test_golden_output_sources_contain_page_url
  test_compact_source_truncates_long_text
```
