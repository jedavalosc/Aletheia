# Revisor local multidisciplinar — diseño

Versión 1 · 14 de octubre de 2026 · propuesta, sin implementar · amplía `docs/agentes.md` (fila "Revisión por pares de la crónica")

## 1. El problema

El verificador de fidelidad actual (paso 4, D44–D49) es un solo modelo que lee cada oración contra sus afirmaciones. En la primera semana real falló de dos maneras opuestas:

- **Objeta lo que es correcto, desde memoria vieja.** Dos veces eliminó la oración "Flávio Bolsonaro é candidato do PL à Presidência" porque "recuerda" a Flávio como senador. El error no es aleatorio: borra contexto de un solo lado de la elección. Un revisor que se equivoca siempre en la misma dirección es una fuente de sesgo, no de ruido.
- **No ve lo que un especialista local vería.** Dejó pasar "a campanha de Flávio Bolsonaro alegou", un verbo que en el periodismo brasileño sugiere falsedad y que se aplicó a un solo polo. No notó que la crónica del IPCA omitía la cifra central (0,82%) porque no sabe qué hace central a un dato de inflación.

Los dos fallos tienen la misma raíz: le pedimos pericia local a un modelo cuya única fuente es su entrenamiento, que es genérico y está desactualizado.

## 2. Principio

**La pericia local no puede vivir en la memoria del modelo.** El diseño la saca de tres lugares que sí se pueden auditar:

1. **Una base de conocimiento local (BCL)** fechada y con fuente primaria: quién ocupa cada cargo, qué candidaturas están registradas, qué etapa procesal tiene cada caso, cómo se publica cada indicador. Es lo que el modelo "sabe" del país, y es verificable.
2. **Rúbricas disciplinarias** escritas y firmadas por especialistas brasileños: qué mira un jurista electoral, un economista, un lingüista, al leer una crónica. Es el criterio.
3. **Calibración contra especialistas humanos**: una muestra mensual codificada a ciegas mide si cada lente acierta. Sin esa medida, "pericia local" es una afirmación, no una propiedad del sistema.

Regla operativa: **sin evidencia, no hay objeción.** Toda objeción debe citar un código de afirmación o una entrada de la BCL vigente en la fecha del evento. Una objeción sin cita se descarta en código y queda registrada. Con esta regla, la objeción "Flávio es senador" solo podría sostenerse citando una entrada de la BCL, y la entrada vigente diría lo contrario.

## 3. Arquitectura

```
crónica (PT) + afirmaciones aceptadas
        │
        ▼
[1] enlace de entidades (código) ──► fragmento de la BCL pertinente al evento
        │
        ▼
[2] lentes disciplinarias en paralelo (modelos, ≥2 proveedores)
        │  objeciones estructuradas, cada una con evidencia
        ▼
[3] adjudicación (código) ──► descarta sin evidencia · conflicto afirmación–BCL a la cola
        │                      · grave con evidencia → reparación · leve → registro
        ▼
[4] prueba de simetría (código + muestra por modelo)
        │
        ▼
redactor repara (máx. 2 rondas) ─► verificador en código ─► cola del editor
```

Las lentes no reescriben: objetan con categoría, evidencia y una sugerencia acotada a las afirmaciones. La reparación sigue siendo del redactor y la decisión, del código y del editor.

## 4. Base de conocimiento local (BCL)

| Tipo de entrada | Ejemplo | Fuente primaria |
|---|---|---|
| Cargo | presidencia del TSE: nombre, desde, hasta | tse.jus.br |
| Candidatura | candidato, partido, cargo, número, estado del registro | DivulgaCandContas (TSE) |
| Calendario electoral | fecha de la segunda vuelta, fin de la propaganda | resoluciones del TSE |
| Etapa procesal | caso, instancia, condición (investigado, denunciado, réu, condenado), fecha | portales del STF, STJ, TSE y TRE |
| Indicador | IPCA: qué mide, quién lo publica, calendario de divulgación, meta vigente | IBGE, Banco Central, CMN |
| Institución | competencias del corregidor general electoral; decisión monocrática y colegiada | Constitución, Código Electoral, reglamentos internos |
| Léxico | término cargado o connotación de verbo, con su uso por polo | lista `loaded_term` + rúbrica lingüística |
| Región | órganos estatales (Alerj, TRE-RJ), medios regionales | sitios oficiales |

Cada entrada tiene `valido_desde`, `valido_hasta`, `fuente_url`, `verificado_en` y `estado` (propuesta, vigente, retirada). Un **agente curador** la mantiene: cada semana consulta las fuentes oficiales de las entidades que aparecen en las afirmaciones y propone altas, cambios y bajas. Ningún cambio entra sin aprobación: del editor ahora y del panel cuando exista. Una entrada sin fuente primaria no se crea. Una entrada que el curador no pudo reverificar en 30 días se marca vencida y las lentes no pueden citarla.

**Conflicto entre afirmación y BCL.** Si un medio dice X y la BCL dice no-X, el revisor no corrige: puede estar equivocado el medio o desactualizada la base. La oración va a la cola con las dos fuentes, nunca a reparación automática.

## 5. Las lentes

Seis lentes, cada una con su rúbrica en `docs/rubricas/<lente>.md`, con versión y firma. Se activan por sección y por entidades del evento, no todas siempre.

| Lente | Qué revisa | Evidencia que puede citar | Esta semana habría |
|---|---|---|---|
| Jurídico-procesal (derecho electoral y procesal) | Condición procesal exacta; decisión monocrática o colegiada; liminar o firme; instancia y competencia; presunción de inocencia | BCL: etapas, instituciones; afirmaciones | Confirmado que la decisión del corregidor es preliminar y debe ir al pleno, y verificado que la crónica no la presente como definitiva |
| Ciencia política e instituciones | Cargos, partidos, candidaturas, coaliciones, reglas electorales; trato simétrico de candidatos | BCL: cargos, candidaturas, calendario | Anulado con evidencia la objeción "Flávio es senador" (candidatura registrada) |
| Economía y estadística | Indicador central presente; unidad, base y período; % frente a p.p.; meta y bandas; cifras en disputa | BCL: indicadores; afirmaciones con medida | Señalado que la crónica del IPCA no tiene la variación mensual que da título al evento |
| Lingüística del portugués de Brasil | Connotación de verbos y adjetivos, términos cargados fuera de la lista, apodos y silbatos de perro, registro; propone altas a la lista | BCL: léxico; `loaded_term` | Objetado "alegou" aplicado solo a la campaña de un polo |
| Medios y encuadre | Equilibrio de atribuciones; orden y espacio por polo; respuesta del otro lado cuando existe; qué medio se nombra | Afirmaciones y sus apoyos; métricas de simetría | Comparado el trato de los dos actos en la Paulista (42 y 50) |
| Federación y región | Centralismo del Sudeste; nombres de órganos estatales; contexto regional en eventos locales | BCL: región | Revisado "Alerj", "TRE-RJ" y la cobertura regional del caso Garotinho |

Una séptima lente, **traducción**, revisa ES y EN con la misma regla de evidencia: registro, equivalencias de la guía de estilo y términos cargados en la lengua de destino.

**Contrato de salida** (JSON, validado en código):

```json
{"lente": "juridico", "rubrica": "juridico-1",
 "objeciones": [{"n": 3, "categoria": "condicion_procesal",
                 "gravedad": "grave|leve",
                 "evidencia": ["c41-4", "bcl:TSE-corregedoria-competencia"],
                 "problema": "una oración", "sugerencia": "una oración, dentro de las afirmaciones"}],
 "sin_objeciones": [0, 1, 2]}
```

Las categorías son una lista cerrada por lente. Una objeción con una categoría que no es de su lente se descarta: el lingüista no opina sobre etapas procesales.

## 6. Adjudicación en código

1. Descartar las objeciones sin evidencia, con evidencia inexistente o con una entrada de la BCL no vigente en la fecha del evento. Quedan registradas como "objeción sin respaldo"; su tasa por lente es una métrica.
2. Conflicto entre afirmación y BCL: a la cola, con las dos fuentes.
3. Objeción grave con evidencia válida: a reparación, con el texto de la objeción.
4. Dos lentes en contradicción sobre la misma oración: a la cola.
5. Objeción leve: registro y resumen para el editor; no bloquea.
6. Se mantiene la regla literal (D47): una oración hecha solo con palabras de sus afirmaciones no se elimina por una objeción de fidelidad, pero sí puede objetarse por léxico o encuadre.

## 7. Simetría

**Métricas en código**, por evento y por semana:

- verbos atributivos usados por polo;
- proporción de oraciones y posición del primer sujeto de cada polo;
- presencia de la respuesta del otro lado cuando hay afirmación que la contenga;
- medios nombrados por polo.

**Prueba contrafactual** sobre una muestra de eventos: se intercambian los actores (Lula↔Flávio, PT↔PL) y las mismas lentes juzgan la versión intercambiada. Una diferencia de veredicto entre original y espejo es una señal de sesgo del redactor o de la lente.

**Sesgo del propio revisor:** tasa de objeciones según el polo del sujeto de la oración. Si una lente objeta más a las oraciones sobre un polo sin que la adjudicación las confirme en la misma proporción, la lente vuelve a modo sombra. El caso de Flávio de esta semana es exactamente lo que esta métrica debe detectar.

## 8. Diversidad de modelos

Las lentes se reparten al menos entre dos proveedores (hoy Kimi; se suma Claude u otro con una clave). En los eventos de mayor impacto y en los sensibles, las lentes jurídica y de encuadre corren en los dos proveedores y la adjudicación exige acuerdo. Diversificar reduce los errores correlacionados, no los elimina: la calibración humana sigue siendo la medida.

## 9. Panel humano local

Sin personas, las lentes imitan una disciplina; con personas, se puede medir si la ejercen. El panel sigue las reglas del comentador académico (formación, declaración de intereses, pluralidad, rotación):

- **Composición:** dos especialistas por lente (doce), con al menos uno de cada polo del eje principal en las lentes jurídica, política y de encuadre; cuota de fuera del eje Río–São Paulo (Nordeste, Norte y Sur). La composición se publica en la metodología y se audita contra los ejes del país.
- **Tareas:**
  - escribir y firmar las rúbricas y aprobar la semilla de la BCL;
  - codificar cada mes, a ciegas, una muestra de oraciones con errores sembrados y sin ellos;
  - resolver las escalas de eventos sensibles.
- **Dedicación estimada:** cuatro a seis horas al mes por persona, más la redacción inicial de rúbricas, a ajustar tras el piloto.

Mientras el panel no exista, el agente redacta borradores de rúbrica con fuentes, el editor los firma como provisionales y la metodología lo dice: "lentes con rúbrica provisional, sin calibración humana".

## 10. Medición

- **Conjunto de oro con errores sembrados**, por categoría:
  - condición procesal cambiada;
  - atribución eliminada;
  - verbo connotado;
  - fecha o cifra inventada;
  - cargo desactualizado;
  - indicador central omitido;
  - respuesta del otro polo omitida.

  Mitad oraciones correctas. Se renueva cada trimestre para que no se memorice.
- **Por lente:** sensibilidad por categoría, tasa de objeciones falsas en oraciones correctas, asimetría por polo, alfa de Krippendorff frente al panel.
- **Umbrales propuestos** para que una lente pase de modo sombra a compuerta: sensibilidad de al menos 0,8 en sus categorías, objeciones falsas por debajo de 5% y asimetría por polo no distinguible de cero en dos meses de muestra. Son propuestos: se calibran con el piloto, no se publican como validados.

## 11. Costo y latencia

Con la activación por sección, unas cuatro lentes por evento: 40 llamadas para 10 eventos, de unos 30 s cada una sin razonamiento y en paralelo, lo que suma 5 a 8 minutos al pipeline. El costo es del mismo orden que la redacción (unos 40–60 ¢ a los precios provisionales, menos con la tarifa real) más la doble corrida en eventos sensibles. El curador de la BCL agrega pocas llamadas por semana y consultas a sitios oficiales desde GitHub Actions. El costo mayor y real es el panel humano.

## 12. Generalización

Las lentes y el contrato de salida son generales. Lo local vive en tres piezas por país: la BCL, el anexo de cada rúbrica (instituciones, léxico, indicadores) y el panel. Para un país nuevo, el agente de arranque redacta la semilla de la BCL y los anexos con fuentes, y el editor del país los firma.

## 13. Plan por fases

| Fase | Qué | Criterio para pasar |
|---|---|---|
| A | BCL de Brasil (cargos, candidaturas 2026, calendario, etapas de casos en curso, indicadores, léxico) y rúbricas provisionales redactadas por agente y firmadas por el editor | 100% de las entidades de la semana con entrada vigente o marcada ausente |
| B | Lentes en modo sombra durante dos ediciones, junto al verificador actual; conjunto de oro inicial | Comparación publicada en el panel: qué detecta cada uno |
| C | Las lentes reemplazan al verificador de fidelidad como compuerta; simetría semanal | Umbrales de §10 en el conjunto de oro |
| D | Panel humano: firma de rúbricas y primera calibración | Alfa por lente medido; lentes por debajo vuelven a sombra |
| E | Misma arquitectura para el verificador de afirmaciones (paso 3) y la traducción | — |

Datos nuevos: `bcl_entry`, `lens_review` (crónica, lente, modelo, rúbrica, salida) y `objection` (oración, lente, categoría, gravedad, evidencia, resultado de la adjudicación). Código: `app/agents/review_local.py`, `app/agents/bcl_curator.py`, `app/rules/adjudicate.py`.

## 14. Lo que este diseño no resuelve

- Un modelo con rúbrica no es un especialista. El diseño identifica errores de categorías conocidas y mide cuántos detecta; no garantiza juicio experto ante lo imprevisto.
- La BCL cubre lo que tiene fuente oficial. Lo que no circula en fuentes oficiales queda fuera, igual que en la capa académica, y lo mismo vale para el saber de las comunidades sobre su territorio.
- Las lentes revisan la crónica contra afirmaciones que vienen de titulares y resúmenes (D35). No pueden detectar lo que ningún medio publicó.
- En período electoral, el nivel de autonomía no pasa de 1 (docs/agentes.md); el revisor ayuda al editor, no lo reemplaza.

## 15. Decisiones que necesita el editor

1. Si se financia el panel humano (fase D) y con qué presupuesto. Sin él, el sistema puede ser riguroso pero no puede decir que su pericia local está validada.
2. Una segunda clave de proveedor (Claude u otro) para la diversidad del §8.
3. Por qué lente empezar si se implementa por partes. Propuesta: ciencia política (por el fallo de esta semana), luego lingüística y jurídica.
