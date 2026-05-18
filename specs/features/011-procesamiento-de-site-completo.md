# Feature 011: Procesamiento de site completo

## Estado

Borrador

## Contexto

El sistema procesa páginas individuales o listas de URLs explícitas. Para analizar
un site completo el operador tendría que construir manualmente la lista de URLs.
Esta feature automatiza ese proceso: a partir de la home se descubren y procesan
todas las páginas internas del mismo dominio, construyendo la KB de forma autónoma.

## Principio

El crawler parte de una URL raíz, descubre enlaces internos en cada página procesada
y los encola para su procesamiento sucesivo (BFS). El número de páginas es
configurable. La resolución de entidades usa el mecanismo existente (Feature 010).
Los resultados se exportan en JSON (ya existente) y en Markdown legible por humanos.
Un informe de tipos cuenta entidades por clase ontológica.

## Interfaz de línea de comandos

```bash
# Crawl con límite de páginas
python -m src.main --crawl https://visitaburgos.es \
    --max-pages 30 \
    --kb data/kb/burgos.json \
    --output data/output/burgos.json \
    --output-md data/output/burgos.md

# Informe de tipos sobre una KB existente
python -m src.report data/kb/burgos.json
```

## Descubrimiento de URLs: sitemap + BFS

Al iniciar un crawl el sistema intenta obtener el sitemap del site antes de
empezar el BFS:

1. Prueba `/sitemap.xml`, `/sitemap_index.xml` y `/sitemap/sitemap.xml` en orden.
2. Si el sitemap es un índice (`<sitemapindex>`), descarga y procesa cada sub-sitemap
   (máximo 3 niveles de recursión).
3. Las URLs del sitemap pasan el mismo filtro que las del BFS (dominio, extensión,
   segmentos de sistema). Se añaden al inicio de la cola BFS.
4. Si no se encuentra sitemap o la respuesta no es XML válido, continúa solo con BFS.
5. El flag `--no-sitemap` desactiva el descubrimiento por sitemap.

Esto permite descubrir URLs que no están enlazadas en el HTML estático
(portales con navegación JavaScript, Liferay, SPAs, etc.).

## Reglas del crawler

- El dominio de la URL raíz define el perímetro: solo se siguen enlaces del mismo host.
- La cola de URLs es BFS (breadth-first): se priorizan páginas más cercanas a la home.
- Se descartan URLs con extensiones de recurso estático (`.pdf`, `.jpg`, `.css`, etc.).
- Se descartan rutas con segmentos de sistema: `login`, `admin`, `api`, `logout`,
  `register`, `search`, `feed`, `rss`, `sitemap`, `tag`, `category`.
- Las URLs se normalizan antes de encolar (sin fragmento `#`, sin query string,
  slash final consistente) para evitar duplicados.
- Si `--max-pages` no se especifica, se usa un límite por defecto de 50 páginas.
- Una página con error de red no detiene el crawl; se registra en el informe.
- Después de procesar cada página, la KB se guarda en disco (escritura incremental).

## Salida Markdown

El fichero Markdown generado contiene:

1. **Cabecera**: dominio, fecha de extracción, páginas procesadas, total entidades.
2. **Tabla de tipos**: conteo de entidades por clase ontológica, ordenado por frecuencia.
3. **Ficha por entidad**: nombre, tipos, descripción corta, coordenadas, dirección,
   número de imágenes, número de fuentes y páginas de origen, wikidataId si existe.

## Informe de tipos (`src/report.py`)

Módulo standalone ejecutable con `python -m src.report <kb_file>`. Imprime una
tabla con el conteo de entidades por tipo (una entidad con varios tipos cuenta en
cada uno) y el total. También puede devolver el resultado como dict para uso interno.

## Criterios de aceptación

- Dado un site con 3 páginas internas enlazadas desde la home, cuando se ejecuta
  con `--crawl` y `--max-pages 10`, entonces se procesan las 3 páginas.
- Dado `--max-pages 2`, cuando hay 10 páginas por descubrir, entonces se procesan
  exactamente 2.
- Dado un error de red en la segunda página, cuando se crawlea el site, entonces la
  primera y tercera páginas se procesan igualmente.
- Dado `--output-md`, cuando el crawl finaliza, entonces el fichero Markdown
  contiene una sección de tipos y una ficha por entidad.
- Dado `python -m src.report kb.json`, cuando se ejecuta, entonces imprime conteos
  por tipo y el total de entidades.

## Fuera de alcance

- Crawling recursivo profundo ilimitado (sin `--max-pages`).
- Respeto de `robots.txt`.
- Detección de contenido duplicado entre páginas.
- Autenticación o cookies de sesión.
