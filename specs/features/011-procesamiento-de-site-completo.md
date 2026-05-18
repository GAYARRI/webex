# Feature 011: Procesamiento de site completo

## Estado

Implementado

## Contexto

El sistema puede procesar una pagina individual, una lista explicita de URLs o un
site completo. Para el modo site completo, el operador proporciona una URL raiz y
el sistema descubre paginas internas del mismo dominio, las procesa y consolida
las entidades en una KB acumulativa.

## Principio

El crawler parte de una URL raiz y construye una cola de paginas internas. Si
existe sitemap, lo usa como semilla principal de URLs; si no existe o se desactiva
con `--no-sitemap`, cae a descubrimiento BFS desde la home mediante enlaces HTML.

Cada pagina procesada pasa por el mismo flujo conceptual:

1. Extraccion de contenido y bloques.
2. Extraccion de entidades candidatas.
3. Asignacion de imagenes por heuristica y, si procede, vision por LLM.
4. Asociacion de evidencias de bloque.
5. Merge interno de entidades dentro de la pagina.
6. Enriquecimiento con coordenadas, Wikidata, Wikipedia y OpenStreetMap cuando
   `--geocode` esta activo.
7. Consolidacion de evidencias externas en la entidad.
8. Clasificacion ontologica final con toda la evidencia disponible.
9. Saneado de imagenes, URLs e iconos.
10. Resolucion contra la KB acumulativa.

La clasificacion inicial de una entidad se considera provisional. La clasificacion
definitiva se recalcula tras acumular evidencias textuales, visuales y externas.

## Interfaz de linea de comandos

```bash
# Crawl con limite de paginas
python -m src.main https://visitaburgos.es \
    --crawl \
    --max-pages 30 \
    --kb data/kb/burgos.json \
    --output data/output/burgos.json \
    --output-md data/output/burgos.md

# Crawl sin sitemap, solo BFS HTML
python -m src.main https://visitaburgos.es \
    --crawl \
    --no-sitemap \
    --max-pages 30 \
    --kb data/kb/burgos.json

# Informe de tipos sobre una KB existente
python -m src.report data/kb/burgos.json
```

## Descubrimiento de URLs

Al iniciar un crawl, salvo que se use `--no-sitemap`, el sistema intenta obtener
un sitemap del site:

1. Prueba `/sitemap.xml`, `/sitemap_index.xml` y `/sitemap/sitemap.xml`.
2. Si el sitemap es un indice (`<sitemapindex>`), descarga y procesa sub-sitemaps
   hasta 3 niveles de recursion.
3. Las URLs del sitemap pasan por los mismos filtros que las URLs descubiertas en
   HTML: dominio, extension, segmentos de sistema e idioma.
4. Si se encuentra sitemap, sus URLs son la cola inicial del crawl.
5. Si no se encuentra sitemap, o `--no-sitemap` esta activo, la cola empieza en la
   URL raiz y se alimenta con enlaces HTML internos.

Comportamiento actual: cuando hay sitemap, el crawler usa el sitemap como lista de
trabajo principal y no amplia la cola con BFS HTML. Esto favorece control y
predecibilidad, aunque puede dejar fuera paginas internas que no esten en sitemap.

## Reglas del crawler

- El dominio de la URL raiz define el perimetro: solo se siguen URLs del mismo host.
- Las URLs se normalizan antes de encolar: sin fragmento, sin query string y con
  slash final consistente.
- Se descartan recursos estaticos y documentos: `.pdf`, `.jpg`, `.png`, `.css`,
  `.js`, `.xml`, etc.
- Se descartan rutas con segmentos de sistema: `login`, `admin`, `api`, `logout`,
  `register`, `search`, `feed`, `rss`, `sitemap`, `tag`, `category`, etc.
- `--lang` permite descartar paginas cuyo primer segmento de URL sea un idioma
  distinto al solicitado.
- `--max-pages` limita el numero de paginas procesadas.
- Si `--max-pages` no se especifica, no hay limite por defecto.
- Una pagina con error de red no detiene el crawl; se registra en el informe.
- Tras cada pagina procesada correctamente, la KB se guarda en disco si se ha
  indicado `--kb`.
- Al finalizar el crawl, se recalcula la clasificacion de toda la KB y se guarda
  de nuevo si hay `--kb`.

## Evidencias y clasificacion

Durante el crawl, cada entidad puede acumular evidencias desde:

- bloques de pagina (`page_block`);
- analisis visual (`vision_fallback` u otras estrategias de imagen);
- Wikidata;
- Wikipedia, a partir de sitelinks de Wikidata;
- OpenStreetMap/Nominatim;
- paginas adicionales que resuelvan contra la misma entidad en la KB.

La salida final debe usar la clasificacion mas ajustada a las clases disponibles
en la ontologia tras evaluar toda la evidencia acumulada. Los tipos devueltos por
IA, structured data o heuristicas tempranas se tratan como candidatos, no como
decision definitiva.

## Salida JSON

El modo `full` devuelve un informe de crawl y una lista de entidades en formato KB.
Cada entidad incluye, entre otros campos:

- `name`;
- `types`;
- `sourceUrl`;
- `relatedUrls`;
- `address`, `phone`, `email`;
- `coordinates`;
- `shortDescription`, `longDescription`, `sourceText`, `description`;
- `images`;
- `wikidataId`;
- `evidence`;
- `sources` con trazabilidad de `page_url`, `source_type`, texto, imagenes y metadata.

## Salida Markdown

Si se indica `--output-md`, se genera un informe Markdown con:

1. Cabecera: dominio, fecha de extraccion, paginas procesadas y total de entidades.
2. Tabla de tipos: conteo por clase ontologica.
3. Ficha por entidad: nombre, tipos, descripcion corta, coordenadas, direccion,
   numero de imagenes, numero de fuentes, paginas de origen y `wikidataId`.

## Informe de tipos

`src/report.py` permite inspeccionar una KB existente:

```bash
python -m src.report data/kb/burgos.json
```

El informe cuenta entidades por tipo y total de entidades. Una entidad con varios
tipos cuenta en cada tipo.

## Criterios de aceptacion

- Dado un site con sitemap valido, cuando se ejecuta `--crawl`, entonces se cargan
  URLs del sitemap en la cola inicial.
- Dado `--no-sitemap`, cuando se ejecuta `--crawl`, entonces se parte de la URL
  raiz y se descubren enlaces internos por BFS HTML.
- Dado `--max-pages 2`, cuando hay mas de dos paginas en cola, entonces se procesan
  exactamente dos paginas.
- Dado un error de red en una pagina, cuando se crawlea el site, entonces el crawl
  continua con el resto de URLs y registra el error.
- Dado `--kb`, cuando una pagina se procesa correctamente, entonces la KB se guarda
  incrementalmente.
- Dado que una entidad acumula evidencias externas o de paginas posteriores, cuando
  finaliza el crawl, entonces su clasificacion se recalcula usando toda la evidencia
  disponible.
- Dado `--output-md`, cuando el crawl finaliza, entonces el fichero Markdown contiene
  una seccion de tipos y una ficha por entidad.

## Fuera de alcance

- Respeto de `robots.txt`.
- Autenticacion, cookies de sesion o contenido protegido.
- Renderizado JavaScript con navegador real.
- Deteccion semantica avanzada de duplicados de pagina completa.
