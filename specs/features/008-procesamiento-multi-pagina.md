# Feature 008: Procesamiento multi-página y acumulación de conocimiento

## Estado

Borrador

## Contexto

El sistema procesa actualmente una URL por ejecución. Con `--kb` se puede acumular
conocimiento entre ejecuciones sucesivas, pero el flujo es manual: el operador lanza
el comando una vez por URL y gestiona él mismo el orden y la trazabilidad.

La fase 2 requiere procesar un conjunto de páginas relacionadas en una sola ejecución,
construyendo una base de conocimiento donde cada entidad acumula evidencias de todas
las páginas que la mencionan, con trazabilidad completa de qué página aportó qué.

## Principio

El mecanismo de merge existente (`merge_into_kb` + `entity_key`) se conserva sin
cambios. La extensión añade:

- Un modo de entrada multi-URL (lista de URLs en argumento o fichero).
- Registro de la página de origen en cada fuente de evidencia.
- Informe de progreso y resultado consolidado por ejecución batch.

## Reglas

- Cada URL de la lista se procesa de forma independiente y secuencial con el mismo
  pipeline que una ejecución simple (extracción, imágenes, merge interno, geocodificación
  si se activa, enriquecimiento externo si se activa).
- Al terminar cada página, sus entidades se fusionan en la KB acumulada usando el
  mecanismo existente (`merge_into_kb`).
- Cada evidencia (`source`) debe registrar en su metadata la URL de la página que la
  generó (`page_url`) si no está ya presente.
- Si una entidad extraída coincide en clave (`entity_key`) con una entidad ya en la KB,
  sus evidencias se aportan a la existente (enriquecimiento).
- Si no hay coincidencia, se crea como entidad nueva.
- El criterio de coincidencia es el existente: `wikidataId` si disponible, si no
  nombre normalizado sin artículos.
- La KB se guarda después de procesar cada página (escritura incremental), de modo que
  una interrupción no pierde el trabajo ya hecho.
- El informe final incluye: páginas procesadas, páginas con error, entidades nuevas
  añadidas, entidades enriquecidas, total acumulado en KB.

## Interfaz de línea de comandos

Dos formas de especificar varias páginas:

```
# Varias URLs directamente
python -m src.main --urls url1 url2 url3 --kb data/kb/turismo.json

# Fichero con una URL por línea
python -m src.main --urls-file lista.txt --kb data/kb/turismo.json
```

La opción `url` (posicional singular) permanece sin cambios para compatibilidad.
Las opciones `--analyze-images`, `--image-strategy`, `--geocode`, `--model`,
`--format` se aplican a todas las páginas del batch.

## Criterios de aceptación

- Dado un fichero con 3 URLs, cuando se ejecuta con `--urls-file`, entonces se
  procesan las 3 y la KB final contiene las entidades de todas ellas.
- Dada una entidad que aparece en dos páginas distintas con el mismo nombre
  normalizado, cuando se procesa el batch, entonces existe una sola entidad en la KB
  con evidencias (`sources`) de ambas páginas.
- Dado un error de red en la segunda página de un batch de tres, cuando se procesa,
  entonces la primera y tercera páginas se procesan correctamente y el informe indica
  el error de la segunda.
- Dado un batch que se interrumpe tras la primera página, cuando se relee la KB,
  entonces contiene las entidades de esa primera página.
- Cada `source` en la KB contiene `page_url` identificando la página que la originó.

## Fuera de alcance

- Crawling automático (seguir enlaces desde las páginas).
- Procesamiento en paralelo de páginas.
- Deduplicación semántica avanzada (embeddings, similitud vectorial).
- Interfaz web o modo daemon.
