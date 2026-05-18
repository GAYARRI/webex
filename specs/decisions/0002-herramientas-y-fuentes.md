# Decision 0002: Herramientas y fuentes de apoyo

## Estado

Borrador

## Contexto

El proyecto no depende solo de extraccion HTML. Para transformar contenido web en entidades utiles y semanticamente validables, necesitaremos apoyarnos en librerias, ontologias y fuentes externas.

Esta decision documenta las herramientas candidatas, su papel previsto y sus limites iniciales.

## Herramientas y fuentes disponibles

### Extraccion web

- `requests`: descargar HTML de paginas publicas.
- `beautifulsoup4`: parsear HTML y extraer titulo, metadatos, enlaces, imagenes y texto.
- `lxml`: parser HTML/XML rapido para Beautiful Soup y procesamiento estructurado.

### Datos estructurados y salida

- `json`: formato principal de intercambio para resultados.
- `pandas`: analisis tabular, revision de resultados y comparacion de salidas.

### Ontologia y semantica

- Ontologia local en `data/ontology/ontology.rdf`: referencia principal de dominio.
- `rdflib`: leer RDF, OWL o TTL y consultar triples.
- `owlready2`: explorar clases, jerarquias y relaciones ontologicas cuando sea necesario.

### Enriquecimiento externo

- Wikidata: fuente de identificadores, nombres alternativos, coordenadas y tipos externos.
- OpenStreetMap: fuente potencial para lugares, direcciones y coordenadas.

### Inteligencia artificial

- OpenAI API: posible apoyo para extraccion de entidades, resumen, clasificacion candidata y normalizacion de texto.
- Modelo por defecto del MVP: `gpt-5.4-mini`, configurable mediante `OPENAI_MODEL`.

## Reglas iniciales de uso

- La IA puede utilizarse alli donde aporte valor claro: deteccion de entidades, resumen, clasificacion candidata, normalizacion y resolucion de ambiguedades.
- La extraccion basica de HTML debe poder ejecutarse sin IA para facilitar diagnostico y pruebas.
- Las fuentes externas deben usarse como apoyo, no como sustituto del contenido extraido de la pagina.
- Cualquier dato enriquecido externamente debe poder distinguirse del dato extraido directamente.
- La ontologia local debe ser la referencia prioritaria para clasificacion semantica.
- El archivo `ground_truth.json` debe usarse como fixture de ejemplo para validar el mecanismo de comparacion, no como benchmark universal.
- Las salidas generadas o asistidas por IA deben conservar evidencia o referencia al texto fuente siempre que sea posible.

## Riesgos

- Wikidata y OpenStreetMap pueden contener datos incompletos, ambiguos o desactualizados.
- Las clases de la ontologia pueden no coincidir exactamente con los tipos detectados en texto libre.
- El uso de IA puede producir clasificaciones plausibles pero no justificadas por la pagina fuente.
- Algunas paginas requieren JavaScript y no seran cubiertas por `requests` y `beautifulsoup4` en la primera version.

## Consecuencias

- El sistema debe conservar trazabilidad de origen por campo cuando sea posible.
- La arquitectura debe separar extraccion, normalizacion, clasificacion y enriquecimiento.
- Las specs futuras deben indicar si una funcionalidad usa solo HTML, ontologia local, IA o fuentes externas.
