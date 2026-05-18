# Feature 006: Entidades por bloques semanticos y fusion de evidencias

## Estado

Borrador

## Contexto

El sistema no debe crear entidades porque exista una URL. La URL es solo una fuente. La entidad debe nacer de un bloque de contenido coherente donde texto, imagenes y contexto apunten a uno o varios conceptos ontologicos.

Este cambio pasa el flujo de `URL -> entidades` a `bloques -> conceptos -> entidades -> evidencias`.

## Contrato de identidad

- La URL nunca determina la identidad de una entidad.
- La URL solo puede actuar como fuente, evidencia o enlace relacionado.
- El nombre de la entidad debe ser el nombre natural del concepto turistico detectado: recurso, evento, lugar, servicio, ruta, establecimiento o institucion.
- No se aceptan como nombre de entidad dominios, slugs, rutas, breadcrumbs, categorias de menu ni etiquetas de navegacion.
- Cuando un bloque trate de un recurso claro, el sistema debe priorizar el nombre conceptual aunque la URL sea la senal mas visible.

## Principio

Una entidad se crea cuando un bloque contiene suficiente evidencia textual y/o visual compatible con un concepto ontologico. Si otro bloque aporta informacion compatible con una entidad ya creada, se anade como evidencia a esa entidad en lugar de crear una entidad nueva.

## Procedimiento

1. Dividir la pagina en bloques semanticos.
2. Limpiar cada bloque de navegacion, logos, iconos, botones, cookies y ruido.
3. Evaluar texto e imagenes del bloque como una unidad.
4. Inferir la idea general del bloque.
5. Correlacionar esa idea con categorias ontologicas candidatas.
6. Crear una o varias entidades solo si el bloque tiene evidencia suficiente.
7. Asociar a cada entidad el texto, imagenes y URL fuente del bloque.
8. Fusionar entidades equivalentes detectadas en bloques posteriores.
9. Contrastar y enriquecer, cuando sea posible, con Wikidata y OpenStreetMap/Nominatim para coordenadas, imagenes de referencia, identificadores externos y validacion contextual.

## Bloque semantico

Un bloque puede ser:

- `article`
- `section`
- `main`
- tarjeta o contenedor con titulo, texto e imagen;
- modulo de noticia;
- ficha de recurso;
- bloque de evento;
- bloque de servicio turistico.

## Evidencia por entidad

Cada entidad debe poder conservar evidencias:

```json
{
  "sources": [
    {
      "url": "https://example.com",
      "block_id": "block-12",
      "text": "Texto relevante del bloque",
      "images": ["https://example.com/image.jpg"]
    }
  ]
}
```

## Resolucion semantica de bloques

Cada bloque turistico candidato debe terminar con uno de estos estados:

- `attached_to_entity`: el bloque queda como evidencia directa de una entidad.
- `covered_by_related_entities`: el bloque actua como paraguas, resumen o contexto y queda cubierto por varias entidades relacionadas.
- `discarded_navigation`: el bloque contiene enlaces, menus o agrupaciones de navegacion.
- `discarded_noise`: el bloque contiene ruido tecnico, errores de plantilla o contenido sin valor ontologico.
- `unresolved_relevant`: el bloque parece turisticamente relevante pero no se ha convertido, asociado ni descartado con razon.

El objetivo operativo es reducir `unresolved_relevant` a cero sin forzar que todo bloque sea una entidad independiente.

## Reglas de fusion

- Dos entidades con nombre normalizado equivalente se fusionan.
- Dos entidades con el mismo `wikidataId` se fusionan.
- Si los nombres son parecidos pero las clasificaciones son incompatibles, se mantienen separadas.
- Al fusionar, se combinan imagenes sin duplicados.
- Al fusionar, se combinan fuentes/evidencias sin duplicados.
- La descripcion larga puede ampliarse con nuevo contenido, pero no debe reemplazarse por texto de menor calidad.
- La clasificacion ontologica debe conservarse o inferirse antes de guardar la entidad; las entidades sin clasificacion y sin evidencia suficiente deben descartarse.
- Las coordenadas de mayor confianza prevalecen sobre coordenadas debiles o genericas.

## Criterios de aceptacion

- Dada una pagina con varios bloques, cuando se procesa, entonces cada entidad conserva al menos una evidencia de bloque.
- Dado un segundo bloque sobre la misma entidad, cuando se procesa, entonces se fusiona con la entidad existente.
- Dadas imagenes de un bloque, cuando se crea una entidad desde ese bloque, entonces solo se asocian las imagenes compatibles con ese contexto.
- Dado contenido de navegacion, cuando se extraen bloques, entonces no debe crear entidades por si solo.
- Dada una URL fuente, cuando se crea una entidad, entonces la URL aparece como evidencia, no como identidad de la entidad.
- Dado un nombre candidato con forma de URL, dominio o ruta, cuando se limpian entidades, entonces se descarta como identidad.
- Dada una entidad turistica sin tipo devuelto por IA, cuando el texto aporta senales suficientes, entonces se intenta inferir una categoria ontologica permitida.
- Dado un bloque con senales turisticas, cuando no queda asociado a ninguna entidad, cubierto por entidades relacionadas ni descartado con razon, entonces debe aparecer como `unresolved_relevant`.
- Dado un bloque paraguas como una home de ciudad, cuando varios contenidos posteriores cubren sus conceptos, entonces puede resolverse como `covered_by_related_entities`.
- Dado un `ground_truth.json`, cuando se mida cobertura de contenido, entonces no debe usarse como fuente exhaustiva; solo sirve como regresion sobre ejemplos canonicos.

## Fuera de alcance

- Crawling completo de un sitio.
- Resolucion perfecta de duplicados semanticos complejos.
- Entrenamiento de modelos propios.
