# Prueba de lectura en frío del panel

Criterio de aceptación del encargo del panel: un desarrollador que no conoce el proyecto puede, usando solo el panel, correr el sistema sobre la edición de demostración, encontrar el verificador de oraciones y explicar qué pasa cuando rechaza una oración.

**Método.** Un agente sin contexto previo recibió solo el HTML generado (`build-panel --sem-dados`), con la instrucción de no abrir ningún otro archivo, y respondió las tres preguntas citando el panel. Es un sustituto de la prueba con una persona, no la reemplaza: conviene repetirla con el primer desarrollador que tome el proyecto.

## Ronda 1 — 14/10/2026, commit 3f351e2 + panel

| Pregunta | Resultado |
|---|---|
| Correr la demostración de punta a punta | **Falla.** Armó una secuencia por inferencia, mezclando el pipeline semanal (que trabaja sobre la semana real) con la demostración. Faltaban cómo obtener la base local y cómo arrancar la web. |
| Encontrar el verificador | Pasa. Dio `app/rules/verifier.py::verify_sentence` y `app/editorial.py::verify_brief_all_languages`, pero no los llamadores. |
| Qué pasa al rechazar | Pasa en parte. Dio el estado `rechazada` y el bloqueo de la aprobación; no encontró cómo corregirlo. |

Problemas señalados y corregidos: los textos "si falla" estaban solo en español; el comando de pruebas incluía un archivo de evaluación inválido para `-k`; una referencia a `app/admin.py` sin función; `terminos_cargados` aparecía como "sin conectar" porque el contador no podía contar llamadas a `scan` (nombre demasiado común): ahora esos casos se marcan como desconocidos, no como cero. Se añadieron los procedimientos "Levantar el sistema en local con la edición de demostración" y "Una crónica rechazada por el verificador", y la lista de llamadores de cada función de compuerta.

## Ronda 2 — 14/10/2026, después de las correcciones

| Pregunta | Resultado |
|---|---|
| Correr la demostración de punta a punta | Pasa. Dio los pasos con y sin Docker y la aprobación en `/admin`. Pidió el formato de `DATABASE_URL`, cómo crear la base y si hace falta clave de modelo: añadidos después de esta ronda. |
| Encontrar el verificador | Pasa, con la cadena completa de llamadas. |
| Qué pasa al rechazar | Pasa: estado, bloqueo, dónde se ve y cómo se corrige; señaló que hoy no hay pantalla para reescribir oraciones (deuda registrada). |

Observaciones que quedan abiertas: "Escribe" y "Lee" solo detectan constructores, borrados y consultas directas, no cambios de atributos (por eso el verificador figura sin escrituras aunque cambia `neutral_brief.estado`); el panel lo advierte bajo el mapa del pipeline.

## Ronda 3 — 14/10/2026, sobre el commit 3aa398e (paso 4)

Mientras se construía el panel entró el paso 4 (armado de la edición, redacción, traducción). Al aplicar el panel sobre ese commit, `build-panel --check` falló con 25 discrepancias: dos tipos de corrida (`redaccion`, `traduccion`), seis pasos, siete tipos de cola y tres versiones de prompt que no estaban en el registro. Se actualizaron registro y anotaciones (y se retiraron dos hallazgos que el paso 4 resolvió). Es el comportamiento buscado: el panel no puede quedar desactualizado sin que la verificación lo diga.

| Pregunta | Resultado |
|---|---|
| Correr la demostración de punta a punta | Pasa, con Docker y sin Docker. |
| Encontrar el verificador | Pasa, con la cadena de llamadas, incluido el redactor (`draft.py::code_issues`). |
| Qué pasa al rechazar | Pasa: reparaciones, estado, cola (`cronica_rejeitada`) y las tres vías de corrección. |

Observaciones nuevas: los nombres mezclan idiomas (estado `rechazada`, tipo de cola `cronica_rejeitada`); el contador de llamadas desde pruebas muestra 0 para `verify_sentence` porque las pruebas llaman a su envoltorio `verify_brief`.
