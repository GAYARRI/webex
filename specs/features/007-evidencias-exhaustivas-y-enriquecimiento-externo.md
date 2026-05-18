# Feature 007: Evidencias exhaustivas y enriquecimiento externo

## Estado

Borrador

## Contexto

Cada entidad debe funcionar como un nucleo semantico que acumula informacion no redundante. La salida no debe limitarse a una imagen principal o a una descripcion resumida si existen mas textos, imagenes o fuentes externas relevantes.

## Principio

Para cada entidad se deben acumular:

- textos fuente de pagina que aporten informacion nueva;
- imagenes relevantes no redundantes;
- evidencias externas de Wikidata;
- evidencias externas de OpenStreetMap/Nominatim;
- coordenadas y metadatos asociados a esas fuentes.

## Reglas

- Una imagen debe aparecer en `images` solo una vez.
- Una URL de imagen no debe aparecer en `relatedUrls`.
- `sourceText` conserva el mejor texto fuente directo de la entidad.
- `sources` conserva el conjunto de evidencias auditables, internas y externas.
- Las evidencias de pagina usan `source_type: page_block`.
- Las evidencias de Wikidata usan `source_type: wikidata`.
- Las evidencias de OpenStreetMap/Nominatim usan `source_type: openstreetmap`.
- La fusion de entidades debe acumular evidencias sin duplicar la misma fuente.
- La descripcion enriquecida puede coexistir con textos fuente; no debe reemplazarlos.

## Criterios de aceptacion

- Dada una entidad con varias imagenes relevantes, cuando se exporta, entonces `images` contiene todas las URLs no redundantes aceptadas.
- Dada una URL de imagen en `relatedUrls`, cuando se normaliza la entidad, entonces se mueve a `images`.
- Dada una entidad con `wikidataId`, cuando se consulta Wikidata, entonces se agrega una evidencia `wikidata` con URL, texto, imagenes y coordenadas si existen.
- Dada una entidad geocodificada con OpenStreetMap/Nominatim, cuando se agrega coordenada, entonces se agrega evidencia `openstreetmap`.
- Dado un bloque textual relevante, cuando se asocia a una entidad, entonces queda registrado en `sources` sin recorte agresivo.

## Fuera de alcance

- Garantizar que las fuentes externas siempre tengan imagenes.
- Descargar fisicamente imagenes.
- Resolver derechos de uso de imagenes.
