# Contribuir a Aletheia News

Empieza por el panel didáctico: `/admin/painel` en el servidor, o en local

```bash
python -m app.cli build-panel --sem-dados      # build/panel/index.html, sin base de datos
```

Explica las etapas, los agentes, las compuertas, la cola de excepciones, el modelo de datos, la infraestructura, la operación semanal y la deuda conocida, con enlaces al código.

## Definición de terminado

Un cambio que añade o modifica una etapa, un agente o una compuerta no está terminado hasta que:

1. **El registro lo describe.** `app/agents/registry.yaml` lista cada etapa (con su `run_tipo` y sus `pasos_registrados`), cada agente (con su prompt y su versión) y cada compuerta (con su código y sus pruebas).
2. **Las anotaciones lo explican.** `docs/panel/anotaciones.yaml` tiene el propósito de la etapa, la tarea del agente o la regla de la compuerta, en español y, si puedes, en inglés; y cada tipo nuevo de la cola dice qué significa y cómo se resuelve.
3. **La verificación pasa.**

   ```bash
   python -m app.cli build-panel --check --sem-dados
   ```

   Falla si el código abre un `agent_run`, registra un paso (`run.step`), envía un tipo a la cola (`run.review`) o define una versión de prompt (`*_VERSION`) que no está en el registro, o si una referencia `ruta.py::Simbolo` ya no existe. El workflow `.github/workflows/panel.yml` la corre en cada push.
4. **Las pruebas pasan** (`TEST_DATABASE_URL=… python -m pytest`), incluida `tests/test_panel.py`.

## Reglas que no cambian

- Los agentes proponen, el código decide, el editor aprueba las excepciones. Ningún agente escribe en la base sin pasar por una compuerta de `app/rules/`.
- Toda llamada a un modelo pasa por `Run.llm` (registra modelo, versión de prompt, tokens y costo, y respeta el tope de gasto).
- Al cambiar un prompt, sube su versión.
- Las decisiones que se apartan del encargo se registran en `docs/decisiones.md` con un número nuevo.
