# Decisiones de implementación — Aletheia News Brasil, fase 1

Registro de las decisiones que el prompt dejó abiertas o que la implementación obligó a tomar. Las marcadas **[A confirmar]** son las que conviene revisar con el equipo antes de la fase 2; las demás son reversibles y menores.

## Arquitectura y stack

**D1. Generador estático en Python (Jinja2), no Astro.** El prompt sugiere Astro. Elegí generar el sitio desde el mismo proceso Python porque las reglas que deciden qué se publica (verificador, términos cargados, selección, textos de las infografías) ya viven en Python, y el generador las reutiliza sin duplicar la lógica ni el i18n en otro lenguaje. El resultado es el mismo: HTML estático en `/pt`, `/es`, `/en`, regenerado al aprobar una edición; solo el chat y el panel son dinámicos. Revertirlo implica reescribir las plantillas, no el modelo de datos.

**D2. Recuperación léxica (BM25) en la fase 1; pgvector en la fase 2.** El corpus del chat es una sola edición (unos 100 documentos), y la recuperación léxica con plegado de acentos funciona en los tres idiomas porque cada documento se indexa con sus tres versiones. La columna de embeddings y la extensión `pgvector` entran en la migración de la fase 2, junto con la agrupación de eventos, que es donde hacen falta. Fly Managed Postgres incluye pgvector.

**D3. Un proceso web sirve sitio, API, chat y panel.** El sitio se reconstruye al arrancar (el disco de Fly es efímero), al aprobar una edición y cada dos minutos si otra Machine publicó (`_site_sync` en `app/main.py`), porque `fly deploy` crea dos Machines por defecto.

**D4. Pipeline programado a diario e idempotente.** `fly machine run --schedule` admite `hourly/daily/weekly/monthly`, sin hora exacta. El pipeline se programa a diario y solo actúa entre el sábado 00:00 y el lunes 06:00 BRT, cuando ya pasó el corte del viernes 23:59 y la edición de la semana aún no existe. El fin de semana queda para la revisión humana.

**D5. Conexión agrupada de Fly.** `fly mpg attach` define `DATABASE_URL` con la URL agrupada (pooler). Desactivé los prepared statements automáticos de psycopg (`prepare_threshold=None`), que fallan con pooling en modo transacción, y normalizo `postgres://` a `postgresql+psycopg://`. La Machine programada recibe la URL por `--file-secret` (`DATABASE_URL_FILE`), que es el mecanismo documentado para secretos en Machines creadas con `fly machine run`.

## Reglas editoriales

**D6. Pertenencia a un polo.** [A confirmar] Un medio pertenece a un polo cuando todo su intervalo de confianza queda de un lado del cero; si el intervalo cruza el cero, no entra en ningún denominador. Es conservador: un medio de posición incierta no infla ni reduce la cobertura de ningún polo. Solo funciona para ejes binarios; los ejes con tres o más polos necesitan otra regla (fase 2).

**D7. Denominador de cobertura.** Medios del polo que publicaron al menos un texto en la semana (hasta el corte), no todos los medios de la lista. Así un medio inactivo esa semana no aparece como "no cubrió".

**D8. Banderas de punto ciego.** [A confirmar] Diferencia de cobertura ≥ 40 puntos entre polos, en un evento de impacto ≥ 60, calculada solo en el eje principal y solo para el evento y para afirmaciones establecidas (`llano`). Una afirmación atribuida a un solo polo la cubre un solo polo por definición, así que marcarla sería ruido. Los umbrales son provisionales y deben calibrarse con datos reales; en otros ejes la cobertura se muestra pero no genera bandera.

**D9. "O que este enfoque não menciona".** Afirmaciones establecidas (o grupos de cifras en disputa reportadas por los dos polos) que cubre el 25% o menos de los medios del polo.

**D10. Cifras en disputa.** Toda afirmación con la misma medida y valores distintos se fuerza a `atribuido`, aunque tenga respaldo de dos polos. Con tres o más fuentes se dibuja la pieza de puntos por fuente; con dos, una tabla, porque dibujar dos cifras sobre un eje común sugiere una comparabilidad que no está establecida.

**D11. Términos cargados.** "Ocupação" está en la lista igual que "invasão": cada polo usa uno para el mismo acto. Los falsos positivos ("taxa de ocupação hospitalar", "é um mito que") bloquean la oración y el editor la reescribe; es un costo aceptado. Las equivalencias en español e inglés están en la misma tabla.

**D12. Ediciones de 6 a 12 eventos.** La aprobación se rechaza fuera de ese rango, salvo en la edición de demostración, que tiene los tres eventos que pide el prompt.

**D13. Traducciones.** Se exigen las tres lenguas con los mismos `claim_ids` por oración; el verificador corre sobre cada traducción con los términos cargados de su idioma. El método se muestra al lector. En la demostración, las traducciones las redactó el modelo y nadie las revisó, por lo que están marcadas "automática sin revisión" y la página lo avisa.

## Capa académica

**D14. Solo comentario de fondo.** El esquema rechaza `tipo <> 'fondo'` (la cadencia semanal elimina el comentario rápido). Una restricción de base de datos impide guardar enunciados explicativos o normativos con `autoria` distinta de `humano`.

**D15. Demostración sin enunciados explicativos ni normativos.** El prompt prohíbe que el modelo redacte esos planos. La demostración muestra solo enunciados descriptivos y conceptuales (marcados "texto de demostración") y un recuadro que explica que los otros planos están reservados al comentador humano. Las referencias son ficticias y lo dicen.

## Chat

**D16. Verificar y después transmitir.** [A confirmar] El prompt pide streaming y también que ninguna respuesta factual sin cita llegue al lector. Ambas cosas no caben juntas a nivel de token: el texto ya mostrado no se puede retirar. El servidor genera la respuesta completa, la verifica y transmite por SSE los segmentos ya aprobados, precedidos de un evento de estado ("verificando las fuentes"). Cuesta unos segundos de latencia y garantiza el criterio de aceptación.

**D17. Respuesta estructurada en segmentos tipados.** El modelo devuelve JSON con segmentos `fato`, `cobertura`, `interpretacao`, `metodologia`, `sem_informacao` y `esclarecimento`. El verificador exige `claim_ids` existentes en cada hecho, comprueba que cada número de un hecho aparezca en las afirmaciones citadas, aplica las reglas de la crónica (términos cargados, atribución, cifras por fuente), rechaza interpretaciones en Modo Factual Puro y prohíbe números en el texto de conexión. El nombre del comentador y el estatus epistémico los añade el servidor desde la base de datos, no el modelo. Si falla, el modelo recibe los motivos y tiene un reintento; si vuelve a fallar, se envían las afirmaciones más cercanas, que siempre son verificables.

**D17b. Proveedor configurable.** El prompt pide la API de Anthropic. A pedido del equipo, el chat también acepta cualquier API compatible con OpenAI (`CHAT_PROVIDER=openai_compatible`, `CHAT_BASE_URL`, `CHAT_API_KEY`), probado con Kimi (`kimi-k3`, `https://api.moonshot.ai/v1`). El verificador es el mismo para cualquier proveedor: el modelo propone, el código decide qué se publica. Con modelos de razonamiento hay que subir `CHAT_MAX_TOKENS` (4000), porque gastan tokens antes de responder.

**D18. Modo sin conexión.** Sin `ANTHROPIC_API_KEY`, o con el presupuesto diario agotado, el chat responde de forma extractiva: devuelve afirmaciones y datos de cobertura de la edición, verificados con el mismo código. Sirve de respaldo y de línea de base para la evaluación.

**D19. Preguntas enmarcadas desde un polo.** La evaluación de simetría mostró que dos preguntas sobre el mismo evento, enmarcadas desde polos opuestos, recuperaban hechos disjuntos (solapamiento 0): cada encuadre recibía los hechos que lo confirmaban. Ahora la recuperación añade las afirmaciones que el otro encuadre deja fuera, y el prompt pide incluirlas. El solapamiento subió a 0,38–0,57 en el par más desigual.

**D19b. Corrección del evaluador (tras la corrida con Kimi).** Dos comprobaciones daban falsos fallos: (1) las preguntas sin respuesta exigían cero hechos, pero una buena respuesta dice "la edición no trae esto" y añade hechos verificados relacionados; ahora basta el segmento `sem_informacao`. (2) El detector de opinión encontraba "quem tem razão" dentro de la propia negativa; ahora solo revisa segmentos de contenido (`fato`, `cobertura`, `interpretacao`). Las respuestas no cambiaron; se recalificaron las guardadas. La misma corrida mostró un problema real, ya corregido: el modelo dijo "sin asimetría" citando la cobertura del evento y omitiendo las banderas de hechos derivados. La recuperación ahora trae las banderas junto con la cobertura, y el prompt exige mencionarlas.

**D20. Privacidad.** Sin cuentas ni identificador persistente: el id de sesión vive en la pestaña. La IP se usa solo en memoria para el límite de uso y nunca se guarda. Las conversaciones se borran a los 30 días (configurable). Las sugerencias de datos nuevos se guardan sin vínculo con la conversación. El límite por IP es por Machine; con varias Machines, el límite efectivo se multiplica. Si eso importa, se pasa a un contador en Postgres.

**D21. Presupuesto diario.** Se estima con los precios por millón de tokens configurados en `CHAT_PRICE_IN_CENTS_PER_MTOK` y `CHAT_PRICE_OUT_CENTS_PER_MTOK`. Los valores por defecto son de ejemplo: hay que ajustarlos al plan contratado.

## Identidad visual

**D22. Tipografía de titulares pendiente.** [A confirmar] No encontré una familia de raíz brasileña con licencia abierta cuya procedencia pudiera verificar. La propuesta provisional usa Source Serif 4 (lectura y titulares) e Inter (interfaz), autoalojadas (OFL). La familia de titulares sale del inventario del equipo del país.

**D23. Colores de polo.** #4C6A8B y #7F5E7C: igual luminosidad (L* 44) e igual croma (22) en CIELAB, sin rojo, verde ni amarillo, contraste ≥ 5:1 sobre el fondo. Color de marca provisional: pardo de algodón crudo #5E5546, a ΔE > 20 de todos los colores excluidos. Pendiente la prueba ciega.

**D24. CSP con `'unsafe-inline'` en scripts.** Por la configuración inline del chat y del formulario de disputa. Se puede endurecer con nonces sin cambiar comportamiento.

## Datos de demostración

**D25. Mundo ficticio explícito.** Estado de Itaquara, ciudad de Porto Anil, medios nombrados con letras griegas, URLs en el dominio reservado `.invalid`, comentadores "A" y "B". Ninguna entidad puede confundirse con una real. Cada página lleva "Edição de demonstração — conteúdo fictício" y `noindex`.

**D26. Contexto electoral.** Las fechas de la primera y segunda vuelta vienen del prompt y figuran en la configuración del país con la marca "a confirmar por el equipo con el calendario del TSE". No hay resultados ni candidatos en el código.

## Fase 2: proceso agéntico (12 de octubre de 2026)

**D27. Proceso agéntico con compuertas.** [A confirmar] Sin equipo local, cada etapa la ejecuta un agente; las reglas en código siguen decidiendo y el editor resuelve una cola de excepciones. Nivel de autonomía de partida: 1. Diseño completo en `docs/agentes.md`; enmienda reflejada en el encargo del proyecto (sección 14).

**D28. Recolección solo de titular, resumen y enlace.** Los agentes nunca descargan ni guardan el cuerpo de los artículos: solo lo que el medio publica en su RSS o en su sitemap de Google News. Se respeta `robots.txt` con el agente de usuario `AletheiaNewsBot` y un máximo de una petición por segundo por dominio. Fuentes verificadas en `app/seed/feeds_br.json`: 20 de 22 medios; GZH y Band sin fuente utilizable, declarado como vacío.

**D29. Recolección cada dos horas.** Varios RSS guardan solo las últimas 10 entradas (Poder360, Jovem Pan, Revista Oeste, Agência Brasil). Recolectar una vez por semana perdería casi todo su contenido y crearía falsos puntos ciegos. Corre en GitHub Actions; en un repositorio privado consume del cupo gratuito de minutos, por eso no es horaria.

**D30. Agrupación léxica local, no embeddings.** [A confirmar] El encargo sugiere embeddings con `pgvector`. Kimi no ofrece API de embeddings y un modelo local no cabe en el servicio gratuito. Se usa TF-IDF sobre titular y resumen (pliegue de acentos, nombres propios con más peso) y aglomeración por enlace promedio, que resiste el encadenamiento que produce un mismo nombre en muchas noticias distintas durante una elección. Con datos de la semana del 5/10 separó bien eventos que compartían nombres. Revisar si la calidad cae con volúmenes mayores.

**D31. El agente revisa cada grupo.** Una llamada al modelo por evento candidato: confirma que es un solo evento y retira los titulares que no corresponden, redacta un título provisional neutral (verificado contra la lista de términos cargados), asigna sección y decide el alcance temático con su razón. Sin clave, o al alcanzar el tope de gasto, se usan reglas deterministas. Prueba del 12/10: 15 llamadas, unos 18 s cada una con `kimi-k3`.

**D32. Las columnas de opinión no forman eventos.** URLs de columnas, blogs, opinión y "vozes" se excluyen de la agrupación: encuadran hechos, no los reportan. Siguen en la base para el análisis de encuadre.

**D33. Impacto = amplitud de la cobertura.** [A confirmar] El impacto provisional se calcula por la proporción de medios activos que cubren el evento y su dispersión regional. Mide atención, no importancia. Es una aproximación hasta que el editor (o un agente con criterios explícitos) lo ajuste; el panel lo dice.

**D34. Precios del modelo.** El costo registrado usa los precios configurados (`AGENT_PRICE_*`, por defecto los del chat). Ajustarlos a la tarifa real de Kimi para que el tope por corrida (`AGENT_BUDGET_CENTS_PER_RUN`, 100 ¢) sea fiel.

## Paso 3: afirmaciones (13 de octubre de 2026)

**D35. Afirmaciones desde titular y resumen.** El recolector nunca guarda el cuerpo de los artículos (D28), así que el agente extrae afirmaciones solo de titulares y resúmenes del feed. Resultado: menos afirmaciones y más simples, pero cada una se rastrea palabra por palabra hasta un texto publicado por el medio. Para extraer del texto completo habría que revisar los términos de uso de cada medio y activar `cuerpo_permitido` medio por medio; queda pendiente.

**D36. Verificador en otro modelo, no en otro proveedor.** [A confirmar] El diseño pide un verificador en un proveedor distinto para que los errores no estén correlacionados. Con una sola clave (Kimi), el verificador usa otro modelo del mismo proveedor (`kimi-k2.6` cuando el extractor es `kimi-k3`) con instrucciones propias. Reduce la correlación, no la elimina. Basta definir `VERIFIER_PROVIDER`, `VERIFIER_MODEL` y `VERIFIER_API_KEY` (por ejemplo, con Claude) para separarlos.

**D37. Compuertas antes del verificador.** Un apoyo solo sobrevive si su fragmento es copia literal del titular o resumen del medio; una afirmación solo sobrevive con al menos un apoyo que la afirme, sin números ausentes de sus fragmentos, con tipo válido y sin términos cargados sin atribución. El verificador juzga lo que sobrevivió.

**D38. Nada se acepta sin el verificador.** Confirmada y sin divergencias de postura → aceptada. Parcial o con divergencias → en revisión y a la cola del editor. Rechazada → rechazada, guardada para auditoría. Si el verificador no responde, todas quedan en revisión. La tasa de desacuerdo entre agentes se registra por corrida: es una de las métricas para subir de nivel de autonomía.

**D39. Todo es atribuido hasta estimar posiciones.** La regla de selección exige respaldo en dos polos para un hecho llano. Sin posiciones estimadas de medios (paso 5), ninguna afirmación tiene polo y todas entran atribuidas. Es lo correcto: el sistema no sabe aún qué cobertura cruza el eje.

**D40. Razonamiento del modelo apagado para los agentes.** Con razonamiento, `kimi-k3` gasta unos 10.000 tokens y cinco minutos por evento antes de responder; con `max_tokens` 6000 se queda sin respuesta. Con razonamiento apagado (`"thinking": {"type": "disabled"}`) tarda unos 45 s y unos 2.000 tokens, y sus afirmaciones pasan las compuertas igual (12 de 12 en el evento de prueba). Lo mismo con `kimi-k2.6` como verificador. Comparados el 13/10 sobre el mismo evento: `kimi-k2.6` con razonamiento y `kimi-k2.7-code-highspeed` no respondieron dentro del presupuesto. Las compuertas y el verificador hacen el trabajo que el razonamiento haría. `AGENT_THINKING` y `VERIFIER_THINKING` lo cambian; por defecto `disabled` para modelos `kimi-*`. El chat público no cambia.

**D41. "Afirma" contra "matiza" no va a la cola.** Si el extractor y el verificador discrepan solo entre "afirma" y "matiza", se guarda "matiza", la postura más débil, que no cuenta como respaldo pleno en la regla de selección. Solo "contradice" o "no relacionado" cuentan como divergencia y mandan la afirmación a revisión. Así la cola recibe desacuerdos reales, no matices de grado.

**D42. El verificador no usa conocimiento propio.** En la primera prueba rechazó "Lula e Flávio Bolsonaro disputam a eleição presidencial" porque "sabía" que Flávio es senador: conocimiento del modelo desactualizado. Sus instrucciones ahora le prohíben usar lo que sabe del mundo y le piden juzgar solo si la afirmación coincide con los textos. Cambios de tiempo verbal y paráfrasis no son materiales; un pasaje cortado con "..." respalda solo lo que muestra.

**D43. Resultado de la semana del 5/10.** Tres pasadas sobre los 10 eventos de la semana, ajustando instrucciones entre ellas. Última (`extract-3`/`verify-3`): 87 propuestas, 8 rechazadas por compuertas (casi todas por un número ausente de los fragmentos), 67 aceptadas, 11 en revisión, 1 rechazada por el verificador; desacuerdo entre agentes 15 % (25,6 % en la primera pasada); 8,4 minutos; 38 ¢ a los precios provisionales del chat (D34), menos con la tarifa real de Kimi. Lo que más va a revisión: el extractor completa resúmenes cortados por el medio ("influenciado principalmente pela…"). El verificador lo detecta.

## Paso 4: edición y crónicas (14 de octubre de 2026)

**D44. La edición se arma sola, por impacto.** Entran los eventos de la semana dentro del alcance con al menos tres afirmaciones aceptadas, ordenados por impacto (amplitud de cobertura, D33), hasta doce. Nunca se retira un evento ya incluido; con menos de seis, la cola avisa y la compuerta de publicación bloquea. El editor sigue pudiendo fusionar, retirar o marcar fuera de alcance en "Eventos da semana".

**D45. Dos verificadores sobre cada oración: código y otro modelo.** El verificador en código ganó tres reglas: ningún número que no esté en las afirmaciones citadas (admite 2,3 bilhões = 2.300 millones y 22h = 10 p.m.), ninguna afirmación no aceptada en el paso 3, ninguna fórmula de certeza ni verbo atributivo desaconsejado ("alegou", "revelou", "rebateu"). El código no ve si una oración dice algo que su afirmación no dice: eso lo juzga un segundo modelo (`kimi-k2.6`). Hasta dos rondas de reparación; la oración que sigue fallando se elimina (una idea sin afirmación no entra) y queda en la cola. Si falla el título o el lide, o quedan menos de dos oraciones, la crónica se rechaza entera.

**D46. Títulos atribuidos sin elegir medio.** Sin posiciones de medios, toda afirmación es atribuida (D39) y el título también necesita atribución. Nombrar un solo medio en el título lo privilegiaría; se usa al hablante ("Lula diz que...") o el grupo ("..., dizem veículos"). Cuando el paso 5 estime posiciones, los hechos respaldados por los dos polos entrarán llanos y los títulos perderán la atribución.

**D47. El verificador de fidelidad no puede borrar una oración literal.** En la primera semana eliminó dos veces "Flávio Bolsonaro é candidato do PL à Presidência" porque su entrenamiento lo recuerda como senador: un error sistemático contra un solo lado. Además de prohibirle usar conocimiento propio, una regla en código anula su objeción cuando todas las palabras de contenido de la oración vienen de sus afirmaciones (y, si cita una sola, en el mismo orden). La anulación queda en la cola para el editor. La regla no anula objeciones de negación, inversión de roles ni actores añadidos (probado). Es un parche: la solución de fondo está en `docs/revisor-local.md`.

**D48. Atribución estricta: verbos de habla, no de acción.** Se aceptan como marcas de atribución las formas en presente de los verbos de habla ("diz", "afirma", "informa") y "avalia"/"ouvido pelo". No se aceptan verbos de acción ("pediu", "negou", "anunciou"): con ellos, un hecho informado por un solo medio pasaría sin decir quién lo informa. El verbo desaconsejado "alegou" también se rechaza en las afirmaciones del paso 3, porque su texto se muestra en el sitio.

**D49. Traducción con claim_ids fijados por código.** Una llamada por lengua (ES, EN) traduce título, oraciones, afirmaciones y medidas. Los `claim_ids` de cada oración traducida los copia el código desde la oración en portugués; el modelo nunca los toca. El verificador corre de nuevo en cada lengua con su lista de términos cargados; las oraciones que fallan se traducen otra vez una vez. Método registrado: "máquina sin revisar", visible en el sitio. El editor puede editar una oración en portugués en el panel; sus traducciones se descartan y se rehacen.

**D50. Resultado de la semana del 5/10.** 10 eventos, 10 crónicas que pasan el verificador en las tres lenguas, 55 oraciones. En la corrida completa: 1 oración eliminada, 6 rondas de reparación, 3 objeciones del verificador anuladas por la regla literal (dos eran errores del verificador; la tercera, una fusión discutible de dos afirmaciones, quedó para el editor). 9,6 minutos y 50 ¢ a precios provisionales (D34). La crónica del IPCA salió con dos oraciones y sin la variación de 0,82%, porque esa afirmación no sobrevivió al paso 3; una regla nueva avisa en la cola cuando un número del título provisional no está en ninguna afirmación aceptada.

**D51. La semana se procesa de forma incremental.** El pipeline puede correr antes del sábado (corrida forzada para monitorear) y otra vez en la ventana normal. La segunda corrida no destruye el trabajo de la primera: la agrupación conserva los eventos con afirmaciones, crónica o lugar en la edición, y les suma los artículos nuevos cuya similitud promedio con el evento pasa el mismo umbral de enlace promedio (0,20); el resto forma eventos nuevos. La extracción se rehace solo en los eventos que ganaron artículos y nunca si el editor ya decidió sobre una afirmación o aprobó la crónica. Como los códigos de afirmación se reutilizan, una reextracción marca como "obsoleta" la crónica no aprobada del evento y la redacción escribe una versión nueva. Primera corrida forzada: 14 de octubre de 2026, semana del 12/10, a pedido del editor.

## Panel didáctico de traspaso (14 de octubre de 2026)

**D52. El panel se genera del código, no se escribe.** `app/panel` lee el repositorio (modelo de datos, corridas, pasos y tipos de cola de los agentes, versiones de prompt, workflows, variables de entorno, CLI, rutas, pruebas, decisiones) y dos archivos mantenidos a mano: `app/agents/registry.yaml` (qué código implementa cada etapa, agente y compuerta) y `docs/panel/anotaciones.yaml` (propósito, fallos conocidos, procedimientos, glosario). `build-panel --check` falla si el código y esos archivos divergen; el workflow `panel.yml` lo corre en cada push. Lo que el encargo pide y el código no tiene aparece como "falta", no se omite.

**D53. El registro vive en `app/agents/`, no en `agents/`.** La imagen Docker copia `app/` y `docs/`; poner el registro en la raíz habría obligado a otra línea en el Dockerfile y lo habría separado del código que describe. Por la misma razón el Dockerfile ahora copia `render.yaml`, `.github/`, `tests/`, `README.md`, `CONTRIBUTING.md` y `.env.example`: el panel los lee para describir despliegue, horarios y pruebas.

**D54. El panel se sirve en `/admin/painel`, generado al pedirlo.** Detrás de la misma contraseña del panel editorial, con caché de cinco minutos (`?fresh=1` lo regenera). Así incluye agregados de la base (corridas, costo, cola, nivel de autonomía) leídos en una transacción de solo lectura, sin datos de lectores. El repositorio es público, de modo que todo lo que el panel extrae del código ya es público; lo que no debe salir de `/admin` son los agregados en vivo. Nunca muestra valores de secretos: solo sus nombres y dónde se configuran.
