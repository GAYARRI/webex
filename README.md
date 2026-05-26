# Extraccion Web Semantica

Proyecto iniciado con metodologia Spec Driven Development.

El objetivo es construir, paso a paso, una herramienta para extraer informacion de paginas web y convertirla en datos estructurados que puedan relacionarse con una ontologia de dominio.

## Como trabajaremos

Este proyecto no empieza por el codigo. Empieza por especificaciones pequenas, claras y verificables.

Flujo base:

1. Definir el problema en `specs/product-brief.md`.
2. Escribir una spec de funcionalidad en `specs/features/`.
3. Acordar criterios de aceptacion.
4. Documentar decisiones tecnicas relevantes en `specs/decisions/`.
5. Convertir la spec en tareas en `specs/tasks/`.
6. Implementar solo lo necesario para cumplir la spec.
7. Validar con pruebas y comandos reproducibles.

## Estructura inicial

```text
docs/
  spec-driven-workflow.md
specs/
  README.md
  product-brief.md
  decisions/
  features/
  tasks/
data/
  ontology/
```

## Primera funcionalidad propuesta

La primera spec esta en:

```text
specs/features/001-extraer-contenido-web.md
```

Su objetivo es recibir una URL, extraer contenido textual basico y devolver una salida JSON.

## Preparacion tecnica futura

Para ejecutar el MVP en Python:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Uso MVP

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco"
python -m src.main "https://visitasevilla.es/el-flamenco" --ground-truth ground_truth.json
python -m src.main "https://visitasevilla.es/el-flamenco" --no-ai
```

Para permitir enriquecimiento de coordenadas con OpenStreetMap/Nominatim:

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco" --geocode
```

Para validar relacion imagen-entidad con analisis visual por IA:

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco" --analyze-images
```

Para dar maxima relevancia al analisis visual y filtrar imagenes no aceptadas por IA:

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco" --analyze-images --image-strategy vision-first
```

Para guardar sin imprimir todo el JSON en consola:

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco" --geocode --output data/output/el-flamenco.json --quiet
```

Para trabajar con una base de conocimiento acumulativa:

```powershell
python -m src.main "https://visitaburgosciudad.es/es/que-ver/catedral" --geocode --analyze-images --image-strategy vision-first --kb data/kb/burgos.json --output data/output/catedral-clean.json --format clean --quiet
```

`--kb` carga, fusiona y guarda entidades acumuladas. `--format clean` devuelve una salida compacta con los campos principales de cada entidad.

Para generar una salida con la misma estructura de entidades que `ground_truth.json`:

```powershell
python -m src.main "https://visitaburgosciudad.es/" --geocode --analyze-images --image-strategy vision-first --format golden --output data/output/burgos-home-golden.json --quiet
```

`--format golden` devuelve una lista JSON de entidades, sin metadatos de pagina ni reportes.

`ground_truth.json` contiene ejemplos canonicos para pruebas de regresion. No es una lista exhaustiva de contenido turistico y no debe usarse para decidir si nos dejamos informacion sin procesar. Usalo solo con paginas relacionadas con los ejemplos que contiene. Por defecto, la comparacion solo usa entidades del mismo dominio que la URL procesada.

Para revisar cobertura, mira `content_coverage_report` en la salida. Ese informe senala bloques con pinta turistica que no han quedado asociados a ninguna entidad.

Para forzar comparacion contra todo el archivo:

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco" --ground-truth ground_truth.json --ground-truth-scope all
```

El modelo de IA por defecto se lee de `.env` mediante `OPENAI_MODEL`. Para este proyecto se usa `gpt-4o-mini`.

## Pruebas

```powershell
python -m unittest discover -s tests
```

## Contributors

- Jose R. Martinez: direccion del producto, criterios de extraccion y validacion funcional.
- Codex (OpenAI): asistencia tecnica en especificacion, implementacion, pruebas y refactorizacion.

## Principio del proyecto

Si una funcionalidad no tiene spec, todavia no se implementa.
