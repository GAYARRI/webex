# Feature 003: Extraer entidades relevantes de cada barrido

## Estado

Borrador

## Contexto

Tras extraer el contenido de una pagina, el sistema debe intentar identificar entidades relevantes para el dominio tratado. En el contexto inicial del proyecto, una entidad puede representar un recurso turistico, establecimiento, evento, servicio, lugar, ruta, experiencia u otro elemento significativo que pueda clasificarse semanticamente.

Esta spec define que informacion queremos obtener por cada entidad detectada durante un barrido.

## Historia de usuario

Como analista de dominio,
quiero obtener entidades estructuradas a partir del contenido web,
para revisar que informacion es relevante y preparar su clasificacion ontologica.

## Entradas

- Contenido extraido de una URL.
- Metadatos de la pagina origen.
- Ontologia local opcional para orientar la clasificacion.

## Procedimiento fundamental por bloque

Antes de extraer entidades de un bloque de pagina, el sistema debe:

1. Evaluar el contenido completo del bloque: texto, enlaces, imagenes candidatas, contexto cercano de las imagenes y metadatos disponibles.
2. Eliminar del contexto operativo el ruido que no aporta contenido ontologico:
   - menus de navegacion;
   - cabeceras y pies repetidos;
   - selectores de idioma;
   - banners de cookies;
   - botones genericos;
   - iconos de redes sociales;
   - logos;
   - imagenes decorativas o de interfaz;
   - textos legales o errores de plantilla.
3. Construir una idea general del bloque: tema principal, intencion comunicativa y tipo de recurso descrito.
4. Correlacionar esa idea general con categorias ontologicas candidatas usando todas las herramientas disponibles:
   - ontologia local;
   - tipos ya conocidos;
   - Wikidata;
   - OpenStreetMap;
   - IA;
   - reglas y heuristicas locales.
5. Extraer solo entidades con valor semantico real para el dominio turistico, cultural, territorial, patrimonial, de eventos o servicios.
6. Asociar imagenes a entidades solo cuando el texto de la URL de la imagen tenga una coincidencia explicita o indubitable con el nombre de la entidad. La proximidad, el contexto textual, el `alt` o el contenido visible de la imagen pueden servir como apoyo de revision, pero no bastan por si solos para incluir la URL en `images`.

El objetivo no es extraer todos los nombres mencionados, sino las entidades que representan conocimiento util y clasificable.

## Salidas

La salida de extraccion debe poder incluir una lista de entidades con esta forma inicial:

```json
{
  "entities": [
    {
      "nombre_entidad": "Museo de Ejemplo",
      "clasificacion_entidad": "Museo",
      "imagenes_relevantes": [
        {
          "url": "https://example.com/image.jpg",
          "alt": "Fachada del museo",
          "source": "page"
        }
      ],
      "informacion_resumida": "Museo dedicado a la historia local.",
      "informacion_larga": "Descripcion ampliada de la entidad con detalles relevantes extraidos de la pagina.",
      "informacion_contexto": {
        "direccion": "Calle Ejemplo 1",
        "telefono": "+34 000 000 000",
        "email": "info@example.com",
        "web": "https://example.com",
        "horario": "Martes a domingo de 10:00 a 18:00",
        "precio": "Entrada general 5 EUR"
      },
      "coordenadas": {
        "lat": 40.4168,
        "long": -3.7038
      },
      "source_url": "https://example.com",
      "confidence": 0.82
    }
  ]
}
```

## Correspondencia con `ground_truth.json`

El archivo `ground_truth.json`, ubicado en la raiz del proyecto, actua como referencia de ejemplo para probar la comparacion de resultados. No es un benchmark universal. Sus campos actuales se corresponden con esta spec de la siguiente manera:

- `name` equivale a `nombre_entidad`.
- `types` equivale a `clasificacion_entidad`, permitiendo una o varias clases.
- `images` equivale a `imagenes_relevantes`.
- `shortDescription` equivale a `informacion_resumida`.
- `longDescription` equivale a `informacion_larga`.
- `description` conserva texto de contexto extraido de la pagina.
- `address`, `phone`, `email`, `url`, `relatedUrls` forman parte de `informacion_contexto`.
- `coordinates.lat` y `coordinates.lng` equivalen a `coordenadas.lat` y `coordenadas.long`.
- `score` equivale a una valoracion manual o confianza esperada.
- `wikidataId` permite enlazar la entidad con una fuente externa de referencia cuando exista.

## Campos por entidad

- `nombre_entidad`: nombre principal de la entidad detectada.
- `clasificacion_entidad`: tipo o categoria asignada a la entidad. Puede proceder de reglas, heuristicas, IA o una ontologia.
- `imagenes_relevantes`: lista de imagenes asociadas a la entidad, con URL y metadatos disponibles.
- `informacion_resumida`: descripcion breve orientada a revision rapida.
- `informacion_larga`: descripcion extendida con el mayor contexto util posible.
- `informacion_contexto`: datos complementarios como direccion, telefono, email, web, horarios, precios u otros atributos detectados.
- `coordenadas`: latitud y longitud cuando procedan y puedan obtenerse con confianza.
- `source_url`: URL desde la que se extrajo la entidad.
- `confidence`: nivel de confianza estimado para la entidad o su clasificacion.

## Criterios de aceptacion

- Dado contenido con una entidad clara, cuando se procesa la pagina, entonces la salida incluye al menos `nombre_entidad`, `clasificacion_entidad`, `informacion_resumida`, `source_url` y `confidence`.
- Dada una entidad detectada con apoyo de IA, cuando se devuelve la salida, entonces debe conservarse la URL de origen y, cuando sea posible, evidencia textual que justifique la deteccion.
- Dado contenido con imagenes asociadas, cuando se procesa la pagina, entonces se incluyen las imagenes relevantes disponibles.
- Dadas imagenes candidatas de la pagina, cuando se asocian a entidades, entonces solo se incluyen si la URL de la imagen contiene tokens distintivos del nombre de la entidad o una forma compuesta equivalente.
- Dada una entidad con varias imagenes relevantes, cuando se devuelve la salida, entonces puede incluir varias imagenes sin duplicados.
- Dadas imagenes candidatas ambiguas, cuando se habilita analisis visual, entonces el sistema puede analizar el contenido de la imagen y su contexto para informar la decision, pero la salida final solo conserva imagenes cuya URL tambien cumpla la regla de coincidencia explicita o indubitable con el nombre de la entidad.
- Dadas imagenes repetidas para una entidad, cuando se devuelve la salida, entonces deben aparecer una sola vez.
- Dado contenido con direccion, telefono u horarios, cuando se procesa la pagina, entonces esos datos se agrupan en `informacion_contexto`.
- Dado contenido con coordenadas explicitas, cuando se procesa la pagina, entonces se informan `lat` y `long`.
- Dado contenido sin coordenadas, cuando se procesa la pagina, entonces `coordenadas` puede ser `null` sin considerar el resultado erroneo.
- Dada una entidad con clasificacion incierta, cuando se procesa la pagina, entonces el sistema conserva la entidad y refleja una confianza menor.

## Casos limite

- Varias entidades en una misma pagina.
- Una entidad mencionada con varios nombres.
- Imagenes genericas de decoracion no asociadas a la entidad.
- Direcciones parciales o telefonos con formatos distintos.
- Coordenadas ausentes, ambiguas o heredadas de mapas embebidos.
- Clasificaciones posibles multiples.

## Fuera de alcance

- Garantizar clasificacion ontologica perfecta en la primera version.
- Geocodificar direcciones usando servicios externos.
- Descargar o almacenar fisicamente las imagenes.
- Resolver duplicados entre multiples paginas.
