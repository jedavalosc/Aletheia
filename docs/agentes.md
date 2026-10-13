# Proceso agéntico autónomo — diseño

Versión 1 · 12 de octubre de 2026 · enmienda las secciones 3 y 11 del encargo

## Por qué

Aletheia News no tiene, por ahora, equipo local: un solo editor y ningún comentador, anotador ni equipo de país. La visión es un proceso general que corra solo y que pueda repetirse en otros países. Este documento fija cómo se incorpora ese proceso sin romper los principios del encargo, en particular "la neutralidad se audita, no se genera".

## Regla central

**Los agentes proponen, el código decide, el editor aprueba las excepciones.**

- Cada etapa del pipeline la ejecuta un agente con una tarea estrecha y herramientas acotadas. Todo lo que produce queda en la base con procedencia: modelo, versión del prompt, entradas, salida, tokens, costo y duración (`agent_run`, `agent_step`).
- Entre etapas están las compuertas deterministas que ya existen (regla de selección, verificador oración por oración, conteo de cobertura, verificador visual, reglas de la capa académica). Un agente no puede saltarlas ni modificarlas.
- Lo que una compuerta no puede resolver va a la cola de excepciones (`review_item`): agrupaciones de baja confianza, desacuerdos entre agentes, rechazos del verificador que el redactor no logró reparar. El editor revisa la cola, no cada oración.

## Sustitución de roles

| Rol en los documentos EII | Sustituto | Control frente a su debilidad conocida |
|---|---|---|
| Ingesta | Agente de recolección (RSS, sitemaps) | `robots.txt`, límite de ritmo, solo titular y resumen; alerta si cae la ingesta de un polo |
| Agrupación en eventos | Similitud léxica local + agente que decide los casos dudosos | Casos dudosos a la cola; fusión y división manual en el panel |
| Extracción de afirmaciones | Agente extractor | Un segundo agente, en otro proveedor, re-extrae o verifica; los desacuerdos van a la cola |
| Redacción | Agente redactor restringido a las afirmaciones seleccionadas | Verificador en código; hasta dos intentos de reparación |
| Codificación de posición de medios (dos anotadores) | Dos agentes anotadores independientes + acuerdo (alfa de Krippendorff) | El acuerdo entre modelos mide consistencia, no validez. Muestra mensual codificada por el editor; la metodología lo declara |
| Revisión por pares de la crónica | Agente revisor adversarial en otro proveedor | Prueba de simetría entre polos cada semana |
| Equipo de país (ejes, exclusiones, tipografía) | Agente que redacta propuestas con fuentes | Firma del editor; ocurre una o dos veces al año |
| Comentador académico | **No se sustituye.** Agente que busca literatura publicada y revisada por pares y presenta sus hallazgos atribuidos a sus autores, con cita | Nunca redacta enunciados explicativos ni normativos propios. Si no hay literatura pertinente, la capa no aparece |
| Editor | El editor, con cola de excepciones | — |

## Niveles de autonomía

El nivel vigente se guarda por país (`country.autonomy_level`) y se publica en la metodología con sus métricas.

| Nivel | Qué hace el sistema | Qué hace el editor |
|---|---|---|
| 0 | Produce borradores | Aprueba todo, oración por oración (fase 1) |
| 1 | Produce la edición completa | Aprueba la edición desde la cola de excepciones (**nivel de partida**) |
| 2 | Publica solo lo que pasa todas las compuertas con confianza alta | Revisa después, en menos de 24 horas; las correcciones son versiones visibles |
| 3 | Publica todo | Auditorías periódicas |

**Para subir de nivel** hacen falta al menos cuatro ediciones reales consecutivas en el nivel actual con: tasa de rechazo del verificador estable o en baja, desacuerdo entre extractor y verificador por debajo del umbral fijado, correcciones posteriores a la publicación, disputas de lectores aceptadas y calificación de simetría en lectura ciega. Bajar de nivel es inmediato ante un error grave.

**Período electoral.** No pasar del nivel 1 durante la segunda vuelta ni sin opinión jurídica: publicar texto de IA sin revisión sobre elecciones tiene riesgo reputacional y legal, y las reglas brasileñas sobre contenido generado por IA en contexto electoral siguen cambiando.

## Proceso general, no brasileño

Todo agente recibe la configuración del país como entrada (medios, ejes, términos cargados, idiomas, zona horaria). Brasil es la primera instancia. Un agente de arranque de país redacta, con fuentes, la lista de medios, los ejes candidatos y la lista de términos cargados de un país nuevo, para firma del editor.

## Transparencia en el sitio

- Cada pieza dice cómo se produjo: automática, o revisada por el editor.
- Página "Como esta edição foi feita": agentes, modelos, versiones de prompt, compuertas superadas, costo e intervenciones humanas de cada edición.
- La metodología muestra el nivel de autonomía vigente y sus métricas.

## Costos

El alojamiento puede seguir gratuito. El costo nuevo es el modelo, sobre todo la extracción de afirmaciones. Cada corrida tiene un tope de gasto (`AGENT_BUDGET_CENTS_PER_RUN`); al alcanzarlo, la corrida se detiene limpia y deja constancia. Medir una semana real antes de fijar el presupuesto.

## Estado de implementación

| Pieza | Estado |
|---|---|
| Registro de corridas y pasos, cola de excepciones, nivel de autonomía | Hecho (panel: Fila de exceções, Corridas, Eventos da semana) |
| Recolección (paso 1) | Hecho: 20 medios, cada dos horas (D28, D29) |
| Agrupación en eventos (paso 2) | Hecho: TF-IDF + enlace promedio + revisión por agente (D30, D31) |
| Extracción y verificación cruzada de afirmaciones (paso 3) | Hecho: `kimi-k3` extrae, compuertas en código, `kimi-k2.6` verifica (D35–D43). Semana del 5/10: 67 aceptadas, 11 en revisión, desacuerdo 15 %, 8 min |
| Redacción restringida (paso 4) | Pendiente |
| Posición de medios por anotadores modelo (paso 5) | Pendiente |
| Nivel de autonomía en la metodología pública | Hecho |
| Revisor adversarial, literatura académica, página de transparencia | Pendiente |
