# Task Plan 002: MVP extraccion y entidades

## Specs relacionadas

- `specs/features/001-extraer-contenido-web.md`
- `specs/features/003-extraer-entidades.md`
- `specs/features/004-golden-set-validacion.md`
- `specs/decisions/0002-herramientas-y-fuentes.md`

## Objetivo

Construir el primer MVP ejecutable: una CLI que reciba una URL, extraiga contenido web, detecte entidades candidatas con ayuda de IA cuando sea necesario y produzca JSON compatible con el golden set.

## Decisiones de implementacion para el MVP

- Usar el formato de `ground_truth.json` como contrato inicial de salida para entidades.
- Tratar `ground_truth.json` como fixture de ejemplo, no como referencia global para cualquier destino.
- Permitir ejecucion sin IA para extraccion basica y diagnostico.
- Usar IA para tareas semanticamente ambiguas: entidades, resumen, clasificacion candidata y normalizacion.
- Mantener trazabilidad: cada entidad debe conservar al menos `url` y texto fuente o descripcion asociada.

## Tareas

- [x] Crear paquete `src`.
- [x] Crear CLI `python -m src.main URL`.
- [x] Implementar descarga HTML con `requests`.
- [x] Implementar parseo basico con `beautifulsoup4`.
- [x] Extraer titulo, descripcion, texto e imagenes candidatas.
- [x] Crear modelo interno de entidad compatible con `ground_truth.json`.
- [x] Implementar detector inicial de entidades asistido por IA cuando haya API key disponible.
- [x] Implementar modo sin IA que devuelva contenido extraido y entidades vacias o heuristicas simples.
- [x] Implementar carga opcional de `ground_truth.json`.
- [x] Implementar normalizacion de `images` y `relatedUrls` como listas.
- [x] Implementar reporte inicial de comparacion contra `ground_truth.json`.
- [x] Agregar pruebas unitarias para normalizacion y comparacion.
- [x] Implementar enriquecimiento inicial de coordenadas desde pagina y OpenStreetMap opcional.

## Validacion manual

```powershell
python -m src.main "https://visitasevilla.es/el-flamenco"
python -m src.main "https://visitasevilla.es/el-flamenco" --ground-truth ground_truth.json
```

## Resultado esperado

El MVP debe generar un JSON con datos de pagina y una lista `entities` en formato compatible con `ground_truth.json`, aun si algunas entidades tienen baja confianza o requieren revision humana.
