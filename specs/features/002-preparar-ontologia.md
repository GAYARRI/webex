# Feature 002: Preparar carga de ontologia local

## Estado

Borrador

## Contexto

El proyecto trabajara con conceptos de una ontologia turistica. Antes de clasificar contenido, necesitamos validar que la aplicacion puede cargar un archivo de ontologia local y exponer sus conceptos principales de forma controlada.

## Historia de usuario

Como desarrollador,
quiero cargar una ontologia local,
para preparar la clasificacion semantica del texto extraido en iteraciones posteriores.

## Entradas

- `--ontology`: ruta opcional a un archivo RDF, OWL o TTL.

## Salidas

Metadatos minimos de la ontologia:

```json
{
  "ontology": {
    "path": "data/ontology/ontology.rdf",
    "loaded": true,
    "classes_count": 120,
    "concepts_sample": []
  }
}
```

## Criterios de aceptacion

- Dada una ruta valida, cuando cargo la ontologia, entonces el sistema indica que fue cargada correctamente.
- Dada una ruta inexistente, cuando cargo la ontologia, entonces el sistema devuelve un error claro.
- Dado un formato no soportado, cuando cargo la ontologia, entonces el sistema no interrumpe la extraccion web basica.

## Fuera de alcance

- Inferencia semantica avanzada.
- Mapeo automatico entre texto y conceptos.
- Edicion de la ontologia.
