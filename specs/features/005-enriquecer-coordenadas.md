# Feature 005: Enriquecer coordenadas de entidades

## Estado

Borrador

## Contexto

La primera version puede detectar entidades, pero las coordenadas salen pobres si no aparecen claramente en el texto o si la IA no las reconoce. Para mejorar la calidad, el sistema debe buscar coordenadas con una estrategia propia y trazable.

## Objetivo

Mejorar el campo `coordinates` de cada entidad usando fuentes verificables y dejando constancia del origen del dato.

## Estrategia inicial

1. Buscar coordenadas explicitas en la pagina:
   - JSON-LD.
   - Metadatos `geo.position`, `ICBM`, `place:location:latitude`, `place:location:longitude`.
   - Enlaces o scripts con patrones `lat`, `lng`, `latitude`, `longitude`.
2. Si la entidad ya tiene coordenadas, conservarlas.
3. Si no tiene coordenadas y existe direccion o nombre suficiente, consultar OpenStreetMap/Nominatim cuando el usuario lo permita.
4. Si no hay suficiente confianza, dejar coordenadas vacias.

## Salida esperada

```json
"coordinates": {
  "lat": 42.34399,
  "lng": -3.69691,
  "source": "openstreetmap",
  "confidence": 0.78
}
```

## Criterios de aceptacion

- Dada una entidad con coordenadas existentes, cuando se enriquece, entonces se conservan.
- Dada una pagina con JSON-LD que contiene `geo.latitude` y `geo.longitude`, cuando se procesa, entonces se usan como candidatas.
- Dada una entidad sin coordenadas pero con direccion, cuando se habilita geocodificacion, entonces se consulta OpenStreetMap/Nominatim.
- Dada una entidad sin coordenadas y sin datos suficientes, cuando se procesa, entonces `coordinates.lat` y `coordinates.lng` siguen siendo `null`.
- Dado un dato enriquecido, cuando se devuelve la entidad, entonces `coordinates.source` indica su origen.

## Fuera de alcance

- Geocodificacion masiva sin limites de peticiones.
- Resolver todas las ambiguedades geograficas automaticamente.
- Garantizar precision cartografica perfecta.
