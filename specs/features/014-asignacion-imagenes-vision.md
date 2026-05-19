# Feature 014: Asignacion de imagenes mediante vision artificial

## Estado

Implementado, desactivado por defecto

## Objetivo

Mejorar la cobertura de imagenes para entidades turisticas cuando el heuristico
de emparejamiento no puede asignar imagenes con suficiente confianza. La vision
por LLM queda disponible como herramienta opcional, pero no se ejecuta
automaticamente.

## Motivacion

El analisis visual mejora casos con slugs opacos, imagenes sin `alt` o paginas con
asociaciones ambiguas. Sin embargo, en crawl completo puede multiplicar mucho el
tiempo de ejecucion y el coste porque requiere llamadas externas al modelo.

Por defecto, el pipeline usa solo:

- emparejamiento heuristico de imagenes;
- filtros de ruido/iconos/logos;
- evidencias de imagenes desde fuentes externas como Wikidata/Commons cuando
  `--geocode` esta activo.

La vision por LLM se activa solo si el operador lo pide explicitamente.

## Interfaz

```bash
# Sin vision LLM, comportamiento por defecto
python -m src.main https://visitaburgosciudad.es/ --crawl --max-pages 10

# Vision LLM explicita
python -m src.main https://visitaburgosciudad.es/ \
    --crawl \
    --max-pages 10 \
    --analyze-images \
    --image-strategy vision-first

# Compatibilidad: --no-vision se acepta, pero no es necesario
python -m src.main https://visitaburgosciudad.es/ --crawl --no-vision
```

## Estrategias disponibles

| Estrategia | Descripcion |
|---|---|
| `heuristic-first` | Vision valida y complementa las imagenes del heuristico. |
| `vision-first` | Vision reemplaza completamente las imagenes del heuristico. |
| `disambiguation` | Vision evalua todas las imagenes de la pagina y asigna cada imagen a una entidad. Mayor cobertura y mayor coste. |
| `fallback` | Vision actua solo para entidades que quedaron con `images == []` tras el heuristico. |

## Comportamiento actual

- Sin `--analyze-images`, no se llama al modelo de vision.
- Con `--analyze-images`, se usa la estrategia indicada en `--image-strategy`.
- `--no-vision` queda como flag de compatibilidad; no cambia el comportamiento por
  defecto porque la vision ya esta apagada.
- Si se usa estrategia `fallback`, solo las entidades sin imagen se pasan al modelo.
- Si no hay `OPENAI_API_KEY`, la llamada visual se omite y el reporte indica
  `status: skipped`.
- La vision no puede saltarse el contrato final de asignacion: una imagen solo
  queda en `images` si la URL de la imagen contiene una coincidencia explicita o
  indubitable con el nombre de la entidad. El contenido visual, el contexto o el
  `alt` pueden ayudar a diagnosticar, pero no bastan para persistir la imagen.

## Flujo tecnico

```text
_process_page()
  -> enrich_entities_images()                    # heuristico
  -> si --analyze-images:
       analyze_images_with_vision(strategy=args.image_strategy)
  -> si no:
       continuar sin vision LLM
```

El mismo criterio aplica en `run_crawl()`.

## Evidencias

Cuando la vision asigna imagenes, se crea una evidencia con:

- `source_type="vision_fallback"` para estrategia `fallback`;
- `page_url` con la pagina procesada;
- lista de imagenes asignadas;
- texto/metadata de razonamiento cuando el analizador lo proporcione.

Estas evidencias se usan internamente para trazabilidad y consolidacion, pero la
lista final `images` debe contener solo URLs relevantes y no redundantes.

## Coste y limites

- `VISION_BATCH_SIZE = 8` imagenes por llamada al LLM.
- `MAX_IMAGE_BYTES = 4 MB` por imagen; imagenes mayores se envian por URL.
- Se filtran logos, iconos y recursos de ruido antes de llamar al modelo.
- En crawl completo, se recomienda activar vision solo en pruebas acotadas con
  `--max-pages` o sobre URLs seleccionadas.

## Tests

`tests/test_image_ai.py :: FallbackStrategyTests` cubre el comportamiento de la
estrategia `fallback` cuando se invoca explicitamente.
