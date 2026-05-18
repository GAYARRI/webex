# Task Plan 001: Extraer contenido web

## Spec relacionada

`specs/features/001-extraer-contenido-web.md`

## Tareas

- [ ] Crear paquete `src`.
- [ ] Crear punto de entrada CLI.
- [ ] Implementar descarga HTTP.
- [ ] Implementar extraccion de titulo y descripcion.
- [ ] Implementar limpieza basica de texto.
- [ ] Implementar salida JSON por consola.
- [ ] Implementar escritura opcional con `--output`.
- [ ] Agregar pruebas unitarias para parser y errores.

## Validacion manual

```powershell
python -m src.main "https://example.com"
python -m src.main "https://example.com" --output data/output/example.json
```
