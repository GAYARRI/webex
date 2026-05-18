# Product Brief

## Nombre provisional

Extraccion Web Semantica

## Problema

Queremos extraer informacion de paginas web y transformarla en datos utiles, estructurados y, cuando sea posible, relacionados con una ontologia de dominio.

## Usuarios

- Analista de extraccion que convierte contenido web en conjuntos de datos procesables.
- Analista de dominio que decide que datos son relevantes para el dominio tratado.
- Analista semantico que clasifica el contenido relevante usando conceptos de una ontologia.
- Desarrollador que automatiza el tratamiento de datos web, candidatos y contenido ontologico.
- Usuario de negocio que valida que no se pierde informacion de la web inicial.
- Usuario de negocio que comprueba que la informacion procesada esta correctamente clasificada y es ontologicamente valida.

## Objetivo inicial

Construir una herramienta capaz de recibir una URL, extraer contenido textual relevante y devolver una salida estructurada que pueda evolucionar hacia clasificacion semantica usando una ontologia.

## No objetivos iniciales

- No construir una interfaz grafica en la primera version.
- No soportar crawling masivo desde el inicio.
- No depender de IA para el flujo minimo viable.
- No modificar ni entrenar una ontologia en la primera version.
- No asumir que fuentes externas como Wikidata u OpenStreetMap sustituyen la validacion humana.

## Alcance MVP

El MVP debe:

- Aceptar una URL desde linea de comandos.
- Descargar el HTML de la pagina.
- Extraer campos basicos de identificacion, descripcion y contenido textual de la pagina.
- Identificar entidades relevantes y preparar sus datos principales para clasificacion semantica.
- Devolver el resultado en JSON.
- Permitir, de forma opcional, cargar una ontologia local para preparar futuras clasificaciones.

## Metricas de exito

- Una URL valida produce un JSON comprensible.
- Los errores de red o HTML invalido se comunican de forma clara.
- La salida puede guardarse y procesarse en herramientas externas.
- La implementacion queda cubierta por pruebas unitarias para las partes principales.
