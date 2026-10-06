# Aletheia News Brasil — fase 1 (esqueleto)

Edición semanal brasileña de Aletheia News: cada oración de la crónica enlazada a las afirmaciones y fuentes que la respaldan, cobertura medida por polo, piezas visuales justificadas, capa académica separada y una conversación con IA que solo habla de la edición publicada.

Esta entrega es la **fase 1** del prompt: modelo de datos completo, panel editorial mínimo, sitio estático en portugués, español e inglés con una **edición de demostración ficticia** de tres eventos, y chat funcionando sobre esa edición. Las fases 2 a 4 (ingesta real, capas de profundidad, identidad definitiva) se apoyan en esta base. Las decisiones tomadas están en [`docs/decisiones.md`](docs/decisiones.md); la guía de redacción, en [`docs/estilo-redacao.md`](docs/estilo-redacao.md).

## Qué hay

| Parte | Dónde | Estado |
|---|---|---|
| Modelo de datos (geopolítica, medios, contenido, edición, analítica, académica, visual, estilo, traducción, conversación, disputa) | `app/models.py`, `migrations/` | Completo, 55 tablas |
| Reglas en código: selección de afirmaciones, verificador oración por oración, términos cargados, reglas de la capa académica y de las piezas visuales | `app/rules/` | Completo |
| Cobertura con denominador, puntos ciegos, "o que este enfoque não menciona" | `app/analytics/core.py` | Calculado, nunca cargado a mano |
| Piezas visuales estándar (cobertura, punto ciego, cifras por fuente, serie) con fuente, corte y denominador dentro de la imagen | `app/analytics/visuals.py`, `app/site/svg.py` | Verificadas automáticamente |
| Sitio estático trilingüe | `app/site/` | `/pt`, `/es`, `/en`, `hreflang` |
| Chat sobre la edición | `app/chat/` | Con modelo (Anthropic) o sin conexión |
| Panel editorial | `app/admin.py` | `/admin` con contraseña |
| Pipeline semanal | `app/pipeline/weekly.py` | Ventana y etapas sobre eventos cargados; ingesta en fase 2 |
| Edición de demostración ficticia | `app/seed/demo_content.py` | 3 eventos en el estado inventado de Itaquara |
| Configuración de Brasil | `app/seed/brasil.py` | Ejes como hipótesis versionadas, medios solo para ingesta (sin posición) |
| Pruebas, evaluación del chat (70 preguntas), auditoría de accesibilidad | `tests/`, `evals/`, `scripts/qa/` | Ver resultados abajo |

## Ejecutar en local

### Con Docker

```bash
cp .env.example .env          # defina ADMIN_PASSWORD; ANTHROPIC_API_KEY es opcional
docker compose up --build -d  # Postgres con pgvector + web en http://localhost:8080
docker compose exec web python -m app.cli seed-brasil
docker compose exec web python -m app.cli seed-demo
```

La edición queda **en revisión**. Para publicarla, entre en `http://localhost:8080/admin` (usuario `editor`, la contraseña de `.env`), apruebe las tres crónicas con su nombre, confirme la razón de inclusión excepcional del evento de apuestas y apruebe la edición. El sitio se regenera al aprobar.

Para una prueba rápida sin pasar por el panel: `docker compose exec web python -m app.cli seed-demo --aprovar-como "Su nombre"` (registra su nombre como editor que aprueba). Si ya cargó la demostración, antes ejecute `reset-demo`.

### Sin Docker

Requiere Python 3.12+ y Postgres 16.

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://usuario@localhost:5432/aletheia ADMIN_PASSWORD=...
python -m app.cli migrate
python -m app.cli seed-brasil
python -m app.cli seed-demo
./scripts/start.sh            # http://localhost:8080
```

### Comandos

`python -m app.cli <comando>`: `migrate`, `seed-brasil`, `seed-demo [--aprovar-como NOMBRE]`, `reset-demo`, `build-site`, `purge-chats`, `status`, `eval-chat [--out DIR]`.

## Desplegar en Render (gratis) con Neon

Render no tiene región en Sudamérica; la más cercana es Virginia (EE. UU.). La app y la base van juntas allí, porque cada página hace varias consultas pequeñas a la base.

1. **Repositorio.** Suba este proyecto a un repositorio de GitHub (puede ser privado). Render despliega desde el repositorio y vuelve a desplegar en cada commit.
2. **Base de datos en Neon** (plan gratuito, sin tarjeta). En neon.com cree un proyecto en la región **AWS US East 1 (N. Virginia)**, Postgres 16. En "Connect", active "Connection pooling" y copie la cadena (`postgresql://…-pooler…/neondb?sslmode=require…`).
3. **Servicio en Render.** En el panel de Render: New → Blueprint → conecte GitHub y elija el repositorio. Render lee `render.yaml` y pide tres valores:
   - `DATABASE_URL`: la cadena de Neon.
   - `CHAT_API_KEY`: la clave de Kimi.
   - `ADMIN_PASSWORD`: una contraseña larga para `/admin` (usuario `editor`). Guárdela.
4. **Primer arranque.** Con `AUTO_SEED=demo`, la app migra la base y carga la configuración de Brasil y la edición de demostración. La dirección queda en `https://aletheia-news-brasil.onrender.com` (o la que asigne Render). Apruebe la demostración en `/admin`.
5. **Pipeline semanal.** En GitHub: Settings → Secrets and variables → Actions → nuevo secreto `DATABASE_URL` con la misma cadena de Neon. El flujo `.github/workflows/weekly-pipeline.yml` corre el sábado 06:00 UTC (03:00 BRT); también se puede lanzar a mano desde la pestaña Actions.

**Límites del plan gratuito.** El servicio se duerme tras 15 minutos sin visitas y el siguiente visitante espera alrededor de un minuto. El disco es efímero: el sitio se regenera en cada arranque desde la base, así que no se pierde nada. Para lanzamiento, cambie `plan: free` por `plan: starter` en `render.yaml` (7 USD/mes, no se duerme).

`fly.toml` se retiró. El `Dockerfile` sirve para cualquier proveedor que ejecute contenedores, y `docker-compose.yml` para un servidor propio.

## Verificación

Ejecutado en este entorno sobre Postgres 16 (sin Docker: no había daemon disponible, así que la imagen no se construyó aquí; los requisitos se instalaron en un entorno limpio y `scripts/start.sh` migró y sirvió desde cero).

| Criterio de aceptación | Resultado |
|---|---|
| Ninguna oración publicada sin `claim_id` válido | Las tres crónicas pasan el verificador en PT, ES y EN; el chat dio 100% de oraciones factuales con cita válida en las 70 preguntas |
| Ningún término cargado sin atribución | Verificador en crónica, traducciones, títulos de piezas visuales y respuestas del chat; 0 adopciones del término del lector en la evaluación |
| Edición, fecha de corte y versión en toda página; fuente, fecha y denominador en cada pieza | Comprobado por `tests/test_demo_e2e.py` |
| Tres lenguas con método de traducción | Avisos visibles; la demostración está marcada como traducción automática sin revisión |
| Deportes y farándula solo con razón registrada | Restricción en base de datos y bloqueo de aprobación hasta que un editor la confirme |
| Página de crónica < 300 KB | Máximo 205 KB, contando las cinco fuentes |
| WCAG 2.1 AA con herramienta automática | axe-core: 0 violaciones en 72 comprobaciones (6 páginas × 3 idiomas × claro/oscuro × escritorio/móvil, con chat y fuentes abiertos). Una herramienta automática no cubre todos los criterios: falta revisión manual con lector de pantalla |
| Chat con 100% de citas válidas en el set de evaluación | Cumplido con el modo sin conexión. **La evaluación con el modelo no se ejecutó aquí por falta de clave de API**; córrala antes del lanzamiento (abajo) |
| Despliegue reproducible desde el README | Desplegado y verificado en Fly el 6/10/2026 (luego retirado por costo); configuración de Render validada contra su documentación y el arranque con `AUTO_SEED` probado en local |

### Evaluación del chat

```bash
python -m app.cli eval-chat --out build/eval
```

70 preguntas en tres idiomas: factuales con respuesta, sin respuesta en la edición, pares de preguntas enmarcadas desde cada polo, pedidos de opinión, intentos de inyección, metodología, cobertura y Modo Factual Puro. Escribe `summary.json`, `results.json` y `blind_pairs.csv` (pares sin etiqueta de polo, en orden aleatorio, para la lectura ciega humana; la clave va aparte).

Resultado con el modo sin conexión (línea de base):

| Métrica | Valor |
|---|---|
| Oraciones factuales con cita válida | 100% |
| Respuestas que pasan el verificador | 100% |
| Preguntas factuales con la afirmación esperada | 100% |
| Pedidos de opinión sin tomar partido | 100% |
| Inyecciones resistidas | 100% |
| Modo Factual Puro respetado | 100% |
| Negativas correctas | 67% (8 de 12) |
| Términos cargados adoptados | 0 |

Las cuatro negativas fallidas no afirman nada falso: ante "¿cuánto se gastó en compras de emergencia?" devuelven hechos relacionados (la alerta del Tribunal de Cuentas) en lugar de decir que la edición no trae la cifra. Un buscador léxico no distingue "relacionado" de "responde". Es el punto a vigilar cuando se evalúe con el modelo.

Resultado con Kimi (`kimi-k3`, `CHAT_PROVIDER=openai_compatible`), 70 preguntas:

| Métrica | Valor |
|---|---|
| Oraciones factuales con cita válida | 100% |
| Respuestas que pasan el verificador | 100% (4 servidas por el respaldo tras dos rechazos del verificador) |
| Preguntas factuales con la afirmación esperada | 100% |
| Negativas correctas | 100% |
| Pedidos de opinión sin tomar partido | 100% |
| Inyecciones resistidas | 100% |
| Modo Factual Puro respetado | 100% |
| Términos cargados adoptados | 0 |

Pendiente: en el par de preguntas enmarcadas desde polos opuestos sobre las compras de emergencia, el modelo aún cita hechos distintos para cada encuadre (solapamiento 0 en PT y EN). La lectura ciega humana con `blind_pairs.csv` debe decidir si eso se percibe como sesgo. Resultados completos en `build/eval-kimi-k3/`.

### Pruebas y accesibilidad

```bash
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql://usuario@localhost:5432/aletheia_test pytest   # base vacía; se reinicia
python scripts/qa/a11y.py --axe ruta/a/axe.min.js --base http://localhost:8080
```

## Estructura

```
app/
  models.py            modelo de datos
  rules/               reglas editoriales en código
  analytics/           cobertura, puntos ciegos, encuadre, piezas visuales
  editorial.py         verificación en tres idiomas y compuertas de aprobación
  chat/                corpus, recuperación, prompt, verificador, servicio, almacenamiento
  site/                generador estático, plantillas, CSS, JS, fuentes
  admin.py             panel editorial
  pipeline/weekly.py   pipeline semanal
  seed/                configuración de Brasil y demostración ficticia
docs/                  guía de redacción y decisiones
evals/                 set de evaluación del chat y ejecutor
tests/                 pruebas unitarias y de punta a punta
scripts/               arranque, pipeline, auditoría de accesibilidad
```

## Siguientes pasos (fase 2)

1. Ingesta de 20–30 medios (RSS, sitemaps), respetando `robots.txt`, muros de pago y términos de uso; texto completo solo donde se permita.
2. Embeddings con pgvector, agrupación en ventana de 7 días, extracción de afirmaciones atómicas y alineación entre artículos.
3. Redacción restringida con modelo, condicionada a las afirmaciones seleccionadas y pasada por el verificador existente.
4. Estimación de posiciones de medios con codificación humana de dos anotadores (provisional hasta entonces).
5. Calibrar los umbrales de punto ciego (D8) y confirmar con el equipo del país los ejes, los colores excluidos y la tipografía de titulares (D22).
