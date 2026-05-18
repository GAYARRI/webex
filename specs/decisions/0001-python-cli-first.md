# Decision 0001: Empezar con una CLI en Python

## Estado

Aceptada

## Contexto

El proyecto necesita validar primero el flujo de extraccion y salida estructurada. Una interfaz grafica agregaria complejidad antes de tener claro el contrato funcional.

## Decision

La primera version sera una herramienta de linea de comandos en Python.

## Consecuencias

- Las specs se validaran con comandos reproducibles.
- La salida JSON facilitara pruebas automatizadas.
- Una futura API o interfaz web podra reutilizar la logica central.
