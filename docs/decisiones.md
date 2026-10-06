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
