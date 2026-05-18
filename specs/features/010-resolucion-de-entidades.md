# Feature 010: Resolución de entidades por similitud contextual e identidad externa

## Estado

Borrador

## Contexto

El merge entre entidades de distintas páginas usa hoy `entity_key()`, que solo
fusiona cuando el `wikidataId` es idéntico o el nombre normalizado (sin artículos)
coincide exactamente. Esto deja sin resolver casos frecuentes:

- "Catedral de Burgos" (página A) vs "La Catedral" (página B) → dos entidades distintas.
- "Camino de Santiago" (página A) vs "El Camino de Santiago por Burgos" (página B) → idem.

Además, si dos entidades de páginas distintas describen el mismo recurso real, al
enriquecerlas con Wikidata recibirán el mismo `wikidataId` — lo que las identifica
inequívocamente como la misma entidad. Pero hoy el enriquecimiento externo ocurre
*dentro* de `_process_page`, y `merge_into_kb` se ejecuta después, de modo que el
`wikidataId` sí está disponible en el momento del merge. El problema es el camino
inverso: si una entidad ya en la KB tiene `wikidataId` pero la entrante aún no lo
tiene, el merge falla por nombre aunque sean la misma.

## Principio

Dos entidades representan el mismo recurso real si su contexto asociado está
fuertemente relacionado. La identidad externa (Wikidata, OSM) es la señal más fuerte;
la similitud de nombre, coordenadas y dirección son señales de apoyo. La fusión se
activa cuando la suma de señales supera un umbral de confianza.

## Señales de resolución y pesos

| Señal | Condición | Peso |
|---|---|---|
| `wikidataId` compartido | Ambas entidades tienen el mismo ID no vacío | 1.0 (definitivo) |
| Coordenadas próximas | Distancia ≤ 150 m (ambas con lat/lng) | 0.55 |
| Dirección coincidente | `address` normalizado no vacío e igual | 0.35 |
| Nombre contenido | Un nombre contiene al otro (núcleo ≥ 4 tokens) | 0.30 |
| Similitud de nombre | Jaccard de tokens significativos ≥ 0.50 | 0.20 |
| Tipo principal compartido | Primer elemento de `types` coincide | 0.10 |

**Umbral de fusión:** suma de señales ≥ **0.70**

La señal `wikidataId` es siempre definitiva (score = 1.0 directo, sin acumular).

## Reglas de resolución

- La resolución reemplaza a `merge_into_kb` como paso de integración cross-página.
  Internamente sigue usando `_enrich()` para combinar campos una vez identificada la
  coincidencia.
- Para cada entidad entrante se busca la candidata más afín en la KB. Si la
  puntuación más alta supera el umbral, se fusiona; si no, se añade como entidad nueva.
- Si una entidad en la KB tiene `wikidataId` y la entrante no lo tiene pero coincide
  por otras señales (≥ 0.70), el `wikidataId` de la KB se propaga a la entrante antes
  de fusionar.
- Si la entrante tiene `wikidataId` y la candidata en KB no, se propaga en sentido
  contrario.
- El umbral es configurable vía argumento `--merge-threshold` (float 0–1, default 0.70).
- El informe de resolución registra para cada par fusionado: señales activadas,
  puntuación total y nombres originales de ambas entidades.
- La resolución no sustituye al merge interno de página (`merge_entities`), que sigue
  ejecutándose antes.

## Reglas de fusión de contenido

Al fusionar dos entidades, la información de contexto se acumula con las siguientes
reglas para cada campo de texto (`shortDescription`, `longDescription`, `description`,
`sourceText`):

- Si el texto entrante está **contenido** en el existente → se descarta (es clon).
- Si el existente está **contenido** en el entrante → el entrante lo sustituye
  (el entrante lo supera y ya no hay pérdida de información).
- Si son **distintos** → se concatenan separados por espacio; ninguno se pierde.

Para `sources` (evidencias):

- Cada evidencia se identifica por la tripleta `(url, block_id, source_type)`.
- Si la tripleta ya existe en la entidad base → se descarta (duplicado exacto).
- Si es distinta → se acumula. La trazabilidad de página (`metadata.page_url`) se
  preserva siempre, sin excepción.

Para `images`:

- Se acumulan sin duplicar URLs. No hay eliminación por similitud visual.

Esta lógica reemplaza el comportamiento actual de `_enrich()` en `knowledge_base.py`,
que descartaba el texto más corto perdiendo información.

## Orden en el pipeline

```
extrae_página
  → enriquece_imágenes
  → analiza_imágenes_vision (opcional)
  → attach_block_evidence
  → merge_entities  (dentro de la página, sin cambios)
  → enrich_coordinates + Wikidata + OSM  (si --geocode)
  → consolidate_evidence + sanitize
  → [NUEVO] resolve_into_kb   ← sustituye merge_into_kb
  → save_kb (incremental)
```

El enriquecimiento externo ocurre antes de la resolución cross-página, de modo que
el `wikidataId` asignado por Wikidata ya está disponible como señal de identidad.

## Criterios de aceptación

- Dadas dos entidades con nombres "Catedral de Burgos" y "La Catedral", coordenadas
  a < 150 m de distancia y mismo tipo, cuando se resuelven, entonces se fusionan en
  una sola entidad con evidencias de ambas fuentes.
- Dadas dos entidades con el mismo `wikidataId`, cuando se resuelven, entonces
  siempre se fusionan independientemente del nombre.
- Dadas dos entidades con nombres similares pero coordenadas a > 5 km, cuando se
  resuelven, entonces NO se fusionan (coordenadas contradictorias actúan como barrera).
- Dado un par con puntuación 0.65 (por debajo del umbral), cuando se resuelven,
  entonces se crean como entidades separadas.
- El informe de resolución lista los pares fusionados con sus señales y puntuación.
- Dadas dos entidades con descripciones distintas que se fusionan, cuando se exporta
  la entidad resultante, entonces `longDescription` contiene el contenido de ambas.
- Dadas dos entidades donde la descripción de la entrante está contenida en la de la
  base, cuando se fusionan, entonces `longDescription` no se duplica ni crece.
- Dadas dos entidades fusionadas procedentes de páginas distintas, cuando se exportan
  sus `sources`, entonces cada evidencia conserva su `page_url` original.

## Barrera anti-fusión

Si ambas entidades tienen coordenadas y la distancia supera 5 km, la puntuación
total se fuerza a 0 — no se fusionan aunque otras señales sean fuertes. Esto evita
falsos positivos por nombre cuando los recursos son físicamente distintos.

## Fuera de alcance

- Resolución basada en embeddings semánticos o vectores de texto.
- Resolución interactiva (preguntar al usuario).
- Razonamiento transitivo (A=B y B=C → A=C) más allá de la pasada actual.
- Separación de entidades ya fusionadas incorrectamente (split).
