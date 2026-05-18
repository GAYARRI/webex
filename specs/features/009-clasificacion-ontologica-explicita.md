# Feature 009: Clasificación ontológica explícita desde la ontología SEGITTUR

## Estado

Borrador

## Contexto

El sistema asigna tipos a las entidades usando una lista de strings hardcodeada en
`ai_client.py` (`TOURIST_TYPES`) y un mapa de palabras clave en `entity_extractor.py`
(`TYPE_KEYWORDS`). Esos strings son aproximaciones al estilo Schema.org, sin anclaje
formal en ninguna ontología.

La ontología de referencia del proyecto (`data/ontology/ontology.rdf`) es la
**Ontología SEGITTUR v1.2** con 272 clases, jerarquía OWL y etiquetas en español e
inglés. No se lee en ningún módulo del sistema.

## Principio

La clasificación de cada entidad debe derivarse explícitamente de la ontología
SEGITTUR: las clases válidas, sus nombres y sus etiquetas deben leerse del fichero RDF,
no definirse de forma manual en el código.

## Reglas

- Al arrancar el clasificador, se carga `data/ontology/ontology.rdf` y se construye
  un índice en memoria con clases, etiquetas (español e inglés) y jerarquía padre-hijo.
- Las clases válidas para clasificación (`TOURIST_TYPES`) se derivan del índice:
  subárbol de `HistoricalOrCulturalResource`, `NaturalResource`, `Route`, `Event`,
  `TourismService`, más un conjunto seleccionado de `TourismOrRelatedFacility`
  (alojamiento, restauración, ocio y cultura).
- El prompt de la IA incluye el nombre local y la etiqueta española de cada clase
  válida, para que el modelo entienda el vocabulario sin ambigüedad.
- El mapa de palabras clave (`TYPE_KEYWORDS`) y el mapa Schema.org
  (`SCHEMA_TO_TOURIST_TYPE`) usan los nombres locales de la ontología
  (p.ej. `"Cathedral"` en lugar de `"Church"`, `"Castle"` en lugar de `"HistoricalSite"`).
- Los tipos asignados a cada entidad son nombres locales de clase SEGITTUR
  (p.ej. `["Cathedral"]`, `["Museum"]`, `["Event"]`).
- La ruta al fichero de ontología es configurable; si el fichero no existe, el sistema
  usa un conjunto de clases de reserva y registra una advertencia.

## Clases de reserva (fallback)

Si la ontología no está disponible, se usan estas clases mínimas:

```
Cathedral, Church, Basilica, Chapel, Monastery, Museum, ArtGallery, Castle,
Palace, Monument, HistoricalOrCulturalResource, CultureCentre, Theater,
Auditorium, Garden, Square, ArcheologicalSite, Hotel, Restaurant, Bar,
NaturalPark, Trail, Route, Event, Tour, TouristAttractionSite
```

## Criterios de aceptación

- Dado el fichero `ontology.rdf`, cuando se carga el índice, entonces contiene todas
  las clases SEGITTUR con su etiqueta española.
- Dada una entidad cuyo texto contiene "catedral", cuando se clasifica con el
  heurístico, entonces su tipo es `"Cathedral"` (no `"Church"`).
- Dada una entidad cuyo texto contiene "monasterio", cuando se clasifica, entonces su
  tipo es `"Monastery"` (no `"Church"`).
- Dado el prompt de la IA, cuando se construye, entonces incluye la etiqueta española
  de cada clase válida junto a su nombre local.
- Dado que el fichero `ontology.rdf` no existe, cuando se arranca el extractor,
  entonces se usa el conjunto de reserva sin lanzar excepción.

## Fuera de alcance

- Exportación de entidades en formato RDF/JSON-LD con URIs completas.
- Resolución de las referencias SKOS externas (p.ej. tipos de evento detallados).
- Razonamiento OWL (inferencia de tipos a partir de la jerarquía).
- Modificación de la ontología.
