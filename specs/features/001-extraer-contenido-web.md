# Feature 001: Extraer contenido web desde una URL

## Estado

Borrador

## Contexto

El proyecto necesita una primera capacidad verificable: recibir una URL y extraer informacion textual basica. Esta funcionalidad sera la base para futuras capas de clasificacion semantica.

## Historia de usuario

Como usuario,
quiero ejecutar una herramienta con una URL,
para obtener informacion estructurada de la pagina sin tener que inspeccionar manualmente el HTML.

## Entradas

- `url`: URL publica HTTP o HTTPS.
- `--output`: ruta opcional para guardar el JSON.

## Salidas

Un objeto JSON con esta forma inicial:

```json
{
  "url": "https://example.com",
  "title": "Example Domain",
  "description": "Example description",
  "language": "es",
  "main_text": "Contenido textual principal...",
  "raw_text": "Texto extraido antes de limpieza avanzada...",
  "extracted_at": "2026-05-17T20:30:00Z",
  "status": "ok",
  "errors": []
}
```

## Criterios de aceptacion

- Dada una URL valida, cuando ejecuto la herramienta, entonces devuelve JSON con `url`, `title`, `description`, `language`, `main_text`, `raw_text`, `extracted_at`, `status` y `errors`.
- Dada una URL no disponible, cuando ejecuto la herramienta, entonces devuelve un error claro sin traza tecnica innecesaria.
- Dado HTML sin titulo, cuando ejecuto la herramienta, entonces `title` puede ser `null` y el proceso no falla.
- Dado el parametro `--output`, cuando ejecuto la herramienta, entonces el JSON se guarda en la ruta indicada.

## Casos limite

- URL sin esquema, por ejemplo `example.com`.
- Respuesta HTTP distinta de 2xx.
- HTML vacio.
- Contenido con codificacion no UTF-8.
- Paginas con mucho ruido de navegacion, scripts o estilos.

## Fuera de alcance

- Clasificacion semantica completa.
- Crawling de enlaces internos.
- Renderizado de JavaScript en navegador.
- Autenticacion en sitios privados.
