# Flujo Spec Driven

## 1. Brief

Antes de escribir codigo, se define el problema y el alcance en `specs/product-brief.md`.

## 2. Feature Spec

Cada funcionalidad nueva empieza como un archivo en `specs/features/`.

Una buena spec debe responder:

- Que problema resuelve.
- Para quien.
- Que entradas acepta.
- Que salida produce.
- Como sabremos que funciona.
- Que queda fuera de alcance.

## 3. Decision tecnica

Cuando una decision afecta la arquitectura, se documenta en `specs/decisions/`.

Ejemplos:

- Usar CLI antes que API.
- Usar `requests` en vez de navegador headless.
- Guardar resultados como JSON antes que en base de datos.
- Usar ontologia local, Wikidata u OpenStreetMap como fuentes de apoyo.

## 4. Plan de tareas

Cada spec aprobada se convierte en un plan pequeno en `specs/tasks/`.

## 5. Implementacion

El codigo se escribe solo para cumplir una spec concreta.

## 6. Validacion

La implementacion se valida contra los criterios de aceptacion, idealmente con pruebas automatizadas y una prueba manual reproducible.
