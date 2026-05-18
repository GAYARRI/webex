# Feature 004: Validar regresion contra ejemplos canonicos

## Estado

Borrador

## Contexto

El proyecto cuenta con un archivo `ground_truth.json` en la raiz. Este archivo contiene ejemplos canonicos y sirve como fixture de ejecucion para probar el mecanismo de comparacion.

Este archivo no representa la verdad global del sistema, no es un inventario exhaustivo de contenido turistico y no debe usarse para medir si el extractor se esta dejando informacion sin procesar. Solo debe compararse con paginas cuyo dominio o escenario este representado en el propio archivo.

## Objetivo

Usar `ground_truth.json` para comprobar regresiones sobre casos canonicos conocidos: si el sistema antes reconocia una entidad de ejemplo, debe seguir pudiendo reconocerla.

La cobertura de contenido debe evaluarse con `content_coverage_report`, no con `ground_truth_report`.

## Entrada

- `ground_truth.json`: lista de entidades canonicas para escenarios de ejemplo.
- Resultado generado por el extractor para una o varias URLs.

## Campos actuales del golden set

Cada entidad del golden set puede incluir:

- `name`: nombre esperado de la entidad.
- `types`: lista de clasificaciones esperadas.
- `score`: puntuacion o confianza esperada.
- `sourceUrl`: URL fuente original cuando se conozca.
- `url`: URL principal asociada a la entidad o pagina de origen.
- `relatedUrls`: URLs relacionadas.
- `address`: direccion.
- `phone`: telefono.
- `email`: correo electronico.
- `coordinates`: objeto con `lat` y `lng`.
- `shortDescription`: descripcion breve esperada.
- `longDescription`: descripcion larga esperada.
- `description`: texto de contexto extraido o asociado.
- `images`: imagen o lista de imagenes asociadas.
- `wikidataId`: identificador Wikidata cuando exista.

## Criterios de aceptacion

- Dado un resultado de extraccion de un dominio cubierto por `ground_truth.json`, cuando se compara contra la referencia, entonces el sistema informa ejemplos canonicos encontrados, ausentes y adicionales.
- Dado un resultado de extraccion de un dominio no cubierto por `ground_truth.json`, cuando se compara contra la referencia, entonces el sistema debe avisar que no hay entidades de referencia para ese dominio.
- Dado cualquier resultado, cuando se emite `ground_truth_report`, entonces debe indicar explicitamente que no mide cobertura exhaustiva.
- Dado contenido turistico potencialmente no procesado, cuando se quiera medir cobertura, entonces debe usarse `content_coverage_report`.
- Dada una entidad esperada, cuando aparece en la salida generada con nombre equivalente, entonces se evalua coincidencia de clasificacion.
- Dadas imagenes esperadas, cuando la salida contiene imagenes, entonces se informa si coinciden exactamente o si son candidatas diferentes.
- Dadas coordenadas esperadas, cuando la salida contiene coordenadas, entonces se evalua la distancia o coincidencia aproximada.
- Dados campos vacios en el golden set, cuando la salida contiene informacion adicional, entonces no se considera error automaticamente; debe marcarse como dato adicional revisable.
- Dado un campo presente en el golden set, cuando la salida no lo contiene, entonces se marca como ausencia a revisar.

## Reglas de comparacion iniciales

- Los nombres se comparan normalizando mayusculas, minusculas, espacios y acentos.
- Las clasificaciones se comparan como conjuntos, no como texto unico.
- Las imagenes se comparan por URL.
- `images` y `relatedUrls` deben tratarse como listas aunque en el golden set aparezcan a veces como string.
- Las coordenadas pueden considerarse equivalentes si estan dentro de una tolerancia configurable.

## Observaciones detectadas en el archivo actual

- El archivo es JSON valido.
- Contiene 50 entidades.
- Cubre ejemplos de Sevilla y Valladolid, no todos los destinos posibles.
- `images` aparece a veces como string y a veces como lista.
- `relatedUrls` aparece a veces como string y a veces como lista.
- Hay una entidad con `longDescriptionb`, probablemente deberia ser `longDescription`.
- Algunas clases parecen tener erratas o variantes, por ejemplo `EductionalCenter`, `FoodEstablisment`, `AccomodationEstablishment` y `ExibitionHall`.
- Algunas clasificaciones usan nombres locales y una usa una URI completa de ontologia.

## Fuera de alcance

- Corregir automaticamente el golden set.
- Usar este archivo como benchmark universal del extractor.
- Usar este archivo para medir cobertura exhaustiva de una pagina o sitio.
- Decidir que entidad es correcta cuando el golden set y la salida discrepan semanticamente.
- Medir calidad de resumen con evaluacion subjetiva avanzada.
