# Feature 014 — Asignación de imágenes mediante visión artificial

## Objetivo

Mejorar la cobertura de imágenes para entidades turísticas cuando el heurístico de emparejamiento no puede asignar imágenes (p.ej. slugs opacos, imágenes sin atributo `alt`). Se usa un LLM multimodal como fallback automático, sin necesidad de activarlo manualmente.

## Motivación

El heurístico de imágenes basa el emparejamiento en el nombre de la entidad, el texto `alt` y la URL de la imagen. Cuando estas señales están ausentes o son opacas, la entidad queda con `images: []`. Las imágenes son un campo clave en el output (`images: [...]`); las entidades sin imagen tienen menor calidad percibida.

## Estrategias disponibles (`--image-strategy`)

| Estrategia | Descripción |
|---|---|
| `heuristic-first` (defecto) | Visión valida y complementa las imágenes del heurístico. |
| `vision-first` | Visión reemplaza completamente las imágenes del heurístico. |
| `disambiguation` | Visión evalúa TODAS las imágenes de la página; cada imagen se asigna a una sola entidad. Máxima cobertura, mayor coste. |
| `fallback` | Visión sólo actúa para las entidades que quedaron con 0 imágenes tras el heurístico. Coste mínimo. |

## Comportamiento del fallback automático

- Sin `--analyze-images`: el fallback se activa automáticamente en cada página si `OPENAI_API_KEY` está configurada.
- Con `--analyze-images`: se usa la estrategia indicada en `--image-strategy`.
- El fallback **no actúa** si todas las entidades ya tienen imágenes (retorna `status: skipped`).
- El fallback **no actúa** si `OPENAI_API_KEY` no está configurada.
- Solo las entidades con `images == []` se pasan al modelo de visión; las que ya tienen imágenes no se tocan.

## Flujo técnico

```
_process_page()
  └─ enrich_entities_images()         # heurístico de emparejamiento
  └─ [--analyze-images]
       ├─ True  → analyze_images_with_vision(strategy=args.image_strategy)
       └─ False → analyze_images_with_vision(strategy="fallback")  # automático
```

### `_run_fallback(entities, page, report)`

1. Filtra `without_images = [e for e in entities if not e.images]`.
2. Si no hay ninguna → `status: skipped`.
3. Si hay → delega en `_run_disambiguation(without_images, page, report)`.
4. Las entidades con imágenes previas NO se modifican.

### `_run_disambiguation(entities, page, report)`

Para cada imagen de la página, el modelo responde: *¿qué entidad de la lista representa mejor esta imagen?*

- Input: lista de imágenes de la página (filtradas por `is_noise_image`) + índice de entidades (nombre + descripción).
- Output: `{"assignments":[{"image_url":"...","entity":"nombre","reason":"..."}]}`.
- Las asignaciones se resuelven con `_resolve_entity_name` (tolerante a variaciones menores de nombre).
- Cada imagen se asigna a **una sola** entidad.

## Coste y límites

- `VISION_BATCH_SIZE = 8` imágenes por llamada al LLM.
- `MAX_IMAGE_BYTES = 4 MB` por imagen (las más grandes se envían por URL, no en base64).
- Solo se procesan imágenes que pasan el filtro `is_noise_image` (excluye logos, iconos, etc.).

## Tests

`tests/test_image_ai.py :: FallbackStrategyTests`

- `test_fallback_skipped_when_all_entities_have_images` — no llama al modelo si todas ya tienen imagen.
- `test_fallback_skipped_when_no_api_key` — sin clave API retorna `skipped`.
- `test_fallback_only_processes_entities_without_images` — solo las entidades sin imagen reciben asignación; las que ya tenían imagen no cambian.
- `test_fallback_report_strategy_field` — el campo `strategy` del report refleja `"fallback"`.
