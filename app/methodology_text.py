"""Methodology texts shared by the methodology page and the chat corpus."""

METHOD = {
 'pt': {
  'intro': 'Esta página documenta como a Aletheia News Brasil seleciona, escreve e mede. Todas as regras abaixo estão no código e podem ser contestadas.',
  'sel_h': 'Regra de seleção de afirmações',
  'sel': 'Uma afirmação entra na crônica como fato estabelecido se for respaldada por veículos de pelo menos dois polos do eixo principal ou por fonte primária verificável. Caso contrário, entra atribuída (“segundo X”). Cifras em disputa aparecem por fonte, nunca promediadas.',
  'ver_h': 'Verificador', 'ver': 'Nenhuma oração é publicada sem pelo menos um claim_id existente. O verificador rejeita termos carregados sem atribuição, afirmações de um só polo sem atribuição e cifras em disputa resumidas. Roda sobre o original e sobre cada tradução.',
  'pol_h': 'Pertença a um polo', 'pol': 'Cada veículo tem uma posição estimada por eixo, de −1 a 1, com intervalo, método e vigência. Um veículo pertence a um polo quando o intervalo inteiro está de um lado do zero; se o intervalo cruza o zero, não entra em nenhum denominador. Posições nunca são atribuídas à mão e nunca são sobrescritas: cada estimativa nova é uma linha nova.',
  'cov_h': 'Cobertura e pontos cegos', 'cov': 'Denominador: veículos do polo que publicaram ao menos um texto na semana. Uma bandeira provisória aparece quando a diferença de cobertura entre polos de um fato estabelecido é de 40 pontos ou mais num evento de impacto 60 ou mais. A bandeira descreve cobertura; não infere intenção. Nesta versão, as bandeiras só são calculadas no eixo principal.',
  'axes_h': 'Eixos', 'idx_h': 'Índice de veículos', 'idx_note': 'Veículos da lista de ingestão sem posição estimada ainda não entram em nenhum denominador. Fontes oficiais (Agência Brasil/EBC) não pertencem a polo.',
  'not_est': 'posição ainda não estimada', 'terms_h': 'Termos carregados', 'only_quote': 'só em citação', 'gaps_h': 'Vazios declarados',
  'order_h': 'Registro da ordem dos polos', 'order_l': 'primeiro polo à esquerda', 'order_r': 'ordem invertida',
  'tr_h': 'Traduções', 'tr': 'O português é a língua principal. Espanhol e inglês indicam o método: humana, automática revisada (com nome do revisor) ou automática sem revisão. Os claim_ids acompanham cada oração traduzida.',
  'id_h': 'Identidade visual (provisória)', 'id': 'Cores de polo com a mesma luminosidade e saturação, sem vermelho, verde ou amarelo, à espera de teste cego. Lista de exclusão inicial, a confirmar pela equipe do país após a eleição:',
  'ctx_h': 'Contexto do país', 'chat_h': 'Conversa com a IA', 'chat': 'A IA conversa só com esta edição: afirmações, crônicas, cobertura, análise acadêmica e esta metodologia. Não navega na internet. Toda oração factual cita claim_ids e é verificada antes de ser mostrada; se a verificação falha, a resposta não é enviada. Não cria perfil do leitor nem infere seu polo.',
  'conf': 'confirmado', 'pend': 'a confirmar', 'hyp': 'hipótese'},
 'es': {
  'intro': 'Esta página documenta cómo Aletheia News Brasil selecciona, redacta y mide. Todas las reglas están en el código y pueden disputarse.',
  'sel_h': 'Regla de selección de afirmaciones',
  'sel': 'Una afirmación entra en la crónica como hecho establecido si la respaldan medios de al menos dos polos del eje principal o una fuente primaria verificable. Si no, entra atribuida (“según X”). Las cifras en disputa se presentan por fuente, nunca promediadas.',
  'ver_h': 'Verificador', 'ver': 'Ninguna oración se publica sin al menos un claim_id existente. El verificador rechaza términos cargados sin atribución, afirmaciones de un solo polo sin atribución y cifras en disputa resumidas. Corre sobre el original y sobre cada traducción.',
  'pol_h': 'Pertenencia a un polo', 'pol': 'Cada medio tiene una posición estimada por eje, de −1 a 1, con intervalo, método y vigencia. Un medio pertenece a un polo cuando todo el intervalo está de un lado del cero; si el intervalo cruza el cero, no entra en ningún denominador. Las posiciones nunca se asignan a mano ni se sobrescriben.',
  'cov_h': 'Cobertura y puntos ciegos', 'cov': 'Denominador: medios del polo que publicaron al menos un texto en la semana. Aparece una bandera provisional cuando la diferencia de cobertura entre polos de un hecho establecido es de 40 puntos o más en un evento de impacto 60 o más. La bandera describe cobertura; no infiere intención. En esta versión, las banderas solo se calculan en el eje principal.',
  'axes_h': 'Ejes', 'idx_h': 'Índice de medios', 'idx_note': 'Los medios de la lista de ingesta sin posición estimada todavía no entran en ningún denominador. Las fuentes oficiales (Agência Brasil/EBC) no pertenecen a un polo.',
  'not_est': 'posición aún no estimada', 'terms_h': 'Términos cargados', 'only_quote': 'solo en cita', 'gaps_h': 'Vacíos declarados',
  'order_h': 'Registro del orden de los polos', 'order_l': 'primer polo a la izquierda', 'order_r': 'orden invertido',
  'tr_h': 'Traducciones', 'tr': 'El portugués es la lengua principal. Español e inglés indican el método: humana, automática revisada (con nombre del revisor) o automática sin revisión. Los claim_ids acompañan cada oración traducida.',
  'id_h': 'Identidad visual (provisional)', 'id': 'Colores de polo con igual luminosidad y saturación, sin rojo, verde ni amarillo, a la espera de prueba ciega. Lista de exclusión inicial, a confirmar por el equipo del país tras la elección:',
  'ctx_h': 'Contexto del país', 'chat_h': 'Conversación con la IA', 'chat': 'La IA conversa solo con esta edición: afirmaciones, crónicas, cobertura, análisis académico y esta metodología. No navega por internet. Toda oración factual cita claim_ids y se verifica antes de mostrarse; si la verificación falla, la respuesta no se envía. No crea perfiles del lector ni infiere su polo.',
  'conf': 'confirmado', 'pend': 'por confirmar', 'hyp': 'hipótesis'},
 'en': {
  'intro': 'This page documents how Aletheia News Brasil selects, writes and measures. Every rule below is in the code and can be disputed.',
  'sel_h': 'Claim selection rule',
  'sel': 'A claim enters the chronicle as an established fact if outlets from at least two poles of the main axis support it, or if it comes from a verifiable primary source. Otherwise it is attributed (“according to X”). Disputed figures are shown by source, never averaged.',
  'ver_h': 'Verifier', 'ver': 'No sentence is published without at least one existing claim_id. The verifier rejects loaded terms without attribution, single-pole claims without attribution and collapsed disputed figures. It runs on the original and on every translation.',
  'pol_h': 'Pole membership', 'pol': 'Each outlet has an estimated position per axis, from −1 to 1, with an interval, method and validity period. An outlet belongs to a pole when its whole interval lies on one side of zero; if the interval crosses zero, it counts in no denominator. Positions are never assigned by hand and never overwritten.',
  'cov_h': 'Coverage and blind spots', 'cov': 'Denominator: outlets of the pole that published at least one text that week. A provisional flag appears when the coverage gap between poles on an established fact is 40 points or more, in an event of impact 60 or more. The flag describes coverage; it does not infer intent. In this version, flags are computed on the main axis only.',
  'axes_h': 'Axes', 'idx_h': 'Outlet index', 'idx_note': 'Outlets on the ingestion list without an estimated position are not yet counted in any denominator. Official sources (Agência Brasil/EBC) belong to no pole.',
  'not_est': 'position not yet estimated', 'terms_h': 'Loaded terms', 'only_quote': 'quote only', 'gaps_h': 'Declared gaps',
  'order_h': 'Pole order log', 'order_l': 'first pole on the left', 'order_r': 'order reversed',
  'tr_h': 'Translations', 'tr': 'Portuguese is the main language. Spanish and English show the method: human, reviewed machine translation (with the reviewer\'s name) or unreviewed machine translation. claim_ids travel with every translated sentence.',
  'id_h': 'Visual identity (provisional)', 'id': 'Pole colors with equal lightness and saturation, no red, green or yellow, pending a blind test. Initial exclusion list, to be confirmed by the country team after the election:',
  'ctx_h': 'Country context', 'chat_h': 'Conversation with the AI', 'chat': 'The AI only discusses this edition: claims, chronicles, coverage, academic analysis and this methodology. It does not browse the web. Every factual sentence cites claim_ids and is verified before it is shown; if verification fails, the answer is not sent. It builds no reader profile and does not infer the reader\'s pole.',
  'conf': 'confirmed', 'pend': 'to be confirmed', 'hyp': 'hypothesis'}}

# Agentic process (docs/agentes.md). {n} is the current autonomy level.
METHOD["pt"].update({
    "auto_h": "Processo automatizado",
    "auto": "Cada etapa (recolha, agrupamento em eventos e, em seguida, extração de afirmações e redação) é executada por "
            "agentes de software com modelos de linguagem. As regras que decidem o que se publica estão em código e não "
            "podem ser alteradas pelos agentes. Cada passo fica registrado com modelo, versão das instruções e custo. "
            "Nível de autonomia atual: {n} (0: tudo revisado por pessoa; 1: o editor aprova a edição a partir de uma fila "
            "de exceções; 2: publicação automática do que passa em todas as verificações, com revisão posterior; 3: "
            "auditorias periódicas). O nível só sobe com evidência de pelo menos quatro edições reais."})
METHOD["es"].update({
    "auto_h": "Proceso automatizado",
    "auto": "Cada etapa (recolección, agrupación en eventos y, luego, extracción de afirmaciones y redacción) la ejecutan "
            "agentes de software con modelos de lenguaje. Las reglas que deciden qué se publica están en código y los "
            "agentes no pueden cambiarlas. Cada paso queda registrado con modelo, versión de las instrucciones y costo. "
            "Nivel de autonomía actual: {n} (0: todo revisado por una persona; 1: el editor aprueba la edición desde una "
            "cola de excepciones; 2: publicación automática de lo que pasa todas las verificaciones, con revisión "
            "posterior; 3: auditorías periódicas). El nivel solo sube con evidencia de al menos cuatro ediciones reales."})
METHOD["en"].update({
    "auto_h": "Automated process",
    "auto": "Each stage (collection, grouping into events and, next, claim extraction and drafting) is run by software "
            "agents using language models. The rules that decide what gets published are in code and the agents cannot "
            "change them. Every step is logged with its model, instruction version and cost. Current autonomy level: {n} "
            "(0: everything reviewed by a person; 1: the editor approves the edition from an exception queue; 2: "
            "automatic publication of what passes every check, reviewed afterwards; 3: periodic audits). The level only "
            "rises on evidence from at least four real editions."})
