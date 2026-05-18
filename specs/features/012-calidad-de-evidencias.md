# Feature 012: Calidad de evidencias en crawl multi-página

## Estado

Implementado

## Contexto

Al procesar un site completo (Feature 011) la KB acumula entidades procedentes de
decenas de páginas. Se observó que la calidad de las evidencias se degradaba
progresivamente:

1. **Imágenes no relacionadas**: entidades acumulaban hasta 44 imágenes incluyendo
   fotos de biodiversidad, eclipses y flores provenientes de secciones laterales
   o widgets del CMS (Liferay). La presencia de una keyword del nombre de entidad
   en un bloque de 200 palabras era condición suficiente para asignar todas sus
   imágenes.

2. **Texto contaminado con boilerplate**: campos de descripción mostraban cadenas
   como "burgos burgos 12 jun - 1487 visitas" procedentes de widgets de navegación
   del CMS. Estos patrones se concatenaban sin filtrar porque los controles previos
   solo descartaban clones exactos.

3. **Bloques de evidencia excesivos**: `_matching_blocks` podía retornar decenas
   de bloques por entidad sin límite, incorporando texto irrelevante de secciones
   comunes (menús, pies de página, teasers).

## Solución

### A — Puntuación y cap de imágenes en extracción inicial

`_sanitize_entity_images` en `main.py` ordena las imágenes candidatas por
relevancia del slug de URL respecto al nombre de la entidad antes de aplicar el
cap (`_MAX_ENTITY_IMAGES = 10`). Imágenes cuyo slug contiene más palabras del
nombre de la entidad quedan primeras.

`enrich_entities_images` en `images.py` reduce el límite por defecto de 50 a 8
imágenes. El umbral de contexto para imágenes guest (slugs opacos de Liferay) se
eleva de `context_score >= 1` a `context_score >= 2`.

### B — Filtro de boilerplate en campos de texto

`is_boilerplate_text()` en `text_utils.py` detecta patrones CMS comunes:

| Patrón | Ejemplo |
|--------|---------|
| `\d{1,5}\s+visitas?` | "1487 visitas" |
| `saber\s+m[aá]s` | "Saber más" |
| `ir\s+a\s+\w` | "Ir a Catedral" |
| `ver\s+m[aá]s` | "Ver más" |
| `leer\s+m[aá]s` | "Leer más" |

Tanto `_append_context` (`main.py`) como `_merge_text` (`knowledge_base.py`)
descartan silenciosamente cualquier bloque `incoming` que active este detector.
Los valores existentes ya almacenados no se modifican.

### C — Límite de bloques por entidad y penalización de bloques grandes

`_matching_blocks` en `entity_merger.py` limita la respuesta a los
`_MAX_BLOCKS_PER_ENTITY = 5` bloques de mayor puntuación. Adicionalmente:

- Bloques con más de 600 palabras reciben una penalización de -60 puntos
  (ampliada respecto al -40 anterior para >450 palabras).
- Bloques con más de 450 palabras reciben -40 puntos.

La KB también aplica un cap (`_MAX_KB_IMAGES = 10`) durante la fusión en
`_enrich`: una vez que la entidad base ya tiene 10 imágenes, las imágenes
entrantes se ignoran.

## Archivos modificados

| Fichero | Cambio |
|---------|--------|
| `src/text_utils.py` | `_BOILERPLATE_RE`, `is_boilerplate_text()` |
| `src/main.py` | `_rank_and_cap_images`, `_MAX_ENTITY_IMAGES`, boilerplate check en `_append_context` |
| `src/images.py` | `max_images` default 8, umbral guest `context_score >= 2` |
| `src/knowledge_base.py` | boilerplate check en `_merge_text`, `_MAX_KB_IMAGES` en `_enrich` |
| `src/entity_merger.py` | `_MAX_BLOCKS_PER_ENTITY`, penalización reforzada en `_matching_blocks` |
| `tests/test_quality_012.py` | 15 tests cubriendo los cinco cambios |

## Tests

```
tests/test_quality_012.py  — 15 tests
  BoilerplateDetectionTests   (5 tests)
  MergeTextBoilerplateTests   (5 tests)
  KBImageCapTests             (2 tests)
  MatchingBlocksCapTests      (3 tests)
```
