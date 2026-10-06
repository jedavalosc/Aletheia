# Guia de estilo de redação — Aletheia News Brasil

Versão 1 · outubro de 2026 · documento de entrada do modelo de redação e do verificador

Este guia vale para a crônica, para as traduções e para as respostas da conversa com a IA. A referência é o registro neutro das agências com maior reputação de imparcialidade (Reuters, Associated Press, AFP) e de seus manuais, aplicado ao português do Brasil. Ele não substitui esses manuais: fixa as escolhas que importam para a neutralidade auditável da plataforma.

O verificador (`app/rules/verifier.py`) aplica em código as regras marcadas com **[V]**. As demais dependem do editor humano, que aprova cada crônica.

## 1. Princípio

A crônica diz o que aconteceu e quem afirma o quê. Não diz quem tem razão, não explica por que aconteceu e não antecipa o que vai acontecer. Explicação e interpretação pertencem à camada acadêmica, assinada.

Cada oração publicada se apoia em pelo menos uma afirmação atômica (`claim_id`) **[V]**. Se uma ideia não tem afirmação que a sustente, ela não entra no texto.

## 2. Estrutura

- **Pirâmide invertida.** O mais importante primeiro. O leitor que parar no primeiro parágrafo deve saber o essencial.
- **Título informativo.** Sujeito e verbo no presente do indicativo, sem ponto final, sem pergunta, sem dois-pontos de efeito. Ex.: *Assembleia de Itaquara aprova limite à publicidade de apostas esportivas*.
- **Primeiro parágrafo (lide):** o quê, quem, quando e onde. O porquê só entra se for um fato atribuído.
- **Contexto depois.** Antecedentes verificáveis, com data e fonte.
- **Sem suspense.** Nada de "o que ninguém esperava", "reviravolta", ganchos ou perguntas retóricas.
- **Parágrafos curtos:** uma a três orações. Orações com até 35 palavras, de preferência.

## 3. Atribuição

- Tudo o que não for fato estabelecido é atribuído **[V]**. Pela regra de seleção (`app/rules/selection.py`), uma afirmação é fato estabelecido se for respaldada por veículos de pelo menos dois polos do eixo ativo ou por fonte primária verificável; caso contrário, entra atribuída.
- Verbo atributivo padrão: **disse** ou **afirmou**. Também neutros: *informou*, *declarou*, *relatou*, *registrou*, *estimou*, *segundo*, *de acordo com*.
- **Denunciou, acusou, admitiu** carregam significado. Use-os só quando descrevem o ato com exatidão: *denunciou* para uma denúncia formal (ao Ministério Público, a um órgão), *acusou* para uma acusação explícita a alguém identificado, *admitiu* quando a pessoa reconhece algo que antes negava.
- Evite *alegou* (sugere falsidade), *confessou* (fora do âmbito penal), *reconheceu* quando não há reconhecimento, *revelou* (sugere segredo), *disparou*, *rebateu*, *atacou*, *detonou*.
- A fonte vem identificada: nome completo e cargo na primeira menção; depois, sobrenome ou cargo. Fontes anônimas só com justificativa do editor registrada.
- **Cifras em disputa** são apresentadas por fonte, nunca somadas, promediadas ou resumidas em intervalo "consensual" **[V]**: *A Defesa Civil estadual registrou 1.240 pessoas desalojadas; a associação de moradores informou 3.100.*

## 4. Léxico

- Sem adjetivos valorativos (*polêmico*, *histórico*, *duro*, *radical*, *escandaloso*, *brilhante*) nem advérbios de juízo (*infelizmente*, *curiosamente*).
- Sem verbos que imputam intenção (*tentou esconder*, *manobrou*, *driblou*, *armou*).
- Sem metáforas bélicas (*guerra*, *batalha*, *ofensiva*, *trincheira*, *fogo amigo*) nem esportivas (*bola dividida*, *virada*, *gol contra*, *jogo jogado*).
- **Cifras com unidade, fonte e data:** *R$ 2,3 bilhões em 2025, segundo o Tesouro Nacional*. Separador de milhar com ponto, decimal com vírgula. Percentual com o símbolo colado (*12%*). Não arredondar cifras em disputa.
- Datas: *5 de outubro de 2026*; na mesma semana, o dia da semana (*na terça-feira, 6*). Hora no horário de Brasília, com "BRT" quando houver ambiguidade.
- Nomes e cargos completos na primeira menção. Siglas desdobradas na primeira menção, exceto STF, TSE, IBGE e similares de uso corrente.
- Linguagem de gênero conforme o uso das agências: cargo no gênero da pessoa (*a ministra*, *a juíza*).

## 5. Termos carregados do contexto brasileiro

A lista vive no banco de dados (tabela `loaded_term`), é editável no painel editorial e é revisada a cada ciclo eleitoral. A semente está em `app/seed/loaded_terms_br.json`. O detector marca qualquer ocorrência **[V]**; o termo só é aceito se a oração for atribuída ou se ele estiver dentro de citação textual entre aspas. Alguns (pejorativos) só são aceitos em citação.

| Termo | Por que é carregado | Como escrever |
|---|---|---|
| invasão / ocupação (de terras, prédios) | Cada polo usa um dos dois para qualificar o mesmo ato | Descrever o ato: *o grupo entrou no imóvel em 2 de outubro e permanece no local* |
| golpe, golpista | Qualificação política; juridicamente, só quando há decisão | *condenado pelo STF por [tipo penal]*, atribuído |
| censura (decisão judicial) | Qualifica a decisão | *decisão de [tribunal] que determinou a remoção de [conteúdo]* |
| ditadura, ditador | Fora do período 1964–1985, é qualificação | Atribuir |
| fascista, comunista | Rótulos de combate | Atribuir; para partidos, o nome oficial |
| petralha, bolsominion, mito | Pejorativos e apelidos de campo | Só em citação textual |
| ladrão | Imputação penal | *condenado por [crime] pelo [tribunal]* |
| terrorista | Imputação penal | Só com tipificação legal atribuída |
| baderneiro, vândalo | Desqualifica quem protesta | Descrever o ato |
| regime de [nome] | Aplicado a governo eleito, sugere ilegitimidade | *governo de [nome]* |

Falsos positivos (*taxa de ocupação hospitalar*, *é um mito que*) bloqueiam a oração mesmo assim: o editor reescreve sem a palavra. É um custo aceito.

## 6. Qualificações jurídicas

- **Fato julgado:** decisão atribuída ao tribunal, com instância e data. *Condenado pelo STF em [data] por [crime]*. Se cabe recurso, dizê-lo.
- **Fato em processo:** estado processual exato. *Investigado* (inquérito aberto), *denunciado pelo Ministério Público* (denúncia oferecida), *réu* (denúncia recebida). Nunca *acusado* como sinônimo vago de qualquer dessas fases.
- Presunção de inocência: nada de *suposto criminoso*; o crime é descrito como objeto da investigação, não a pessoa.
- Decisões liminares são *liminares* ou *decisões provisórias*, não "vitórias" nem "derrotas".

## 7. O que a crônica não faz

- Não atribui intenções nem motivações não declaradas.
- Não prevê desfechos (*deve*, *tende a*, *pode levar a*), salvo previsão atribuída a uma fonte.
- Não usa citação de forma seletiva para insinuar: se uma citação de um polo entra, a resposta direta do outro polo, se houver, também entra.
- Não preenche lacunas: se a informação não existe, diz que não está disponível até a data de corte.

## 8. Equivalências em espanhol e inglês

As traduções mantêm o registro de agência. Não podem ficar mais coloquiais nem mais enfáticas que o original. Os `claim_ids` acompanham cada oração traduzida.

| Português | Español | English |
|---|---|---|
| disse / afirmou | dijo / afirmó | said |
| informou | informó | said / reported |
| segundo / de acordo com | según / de acuerdo con | according to |
| registrou (cifra oficial) | registró | recorded |
| estimou | estimó | estimated |
| denunciou (formalmente) | denunció | filed a complaint / reported to |
| investigado | investigado | under investigation |
| denunciado pelo Ministério Público | acusado formalmente por la Fiscalía (Ministério Público) | charged by prosecutors |
| réu | procesado (acusado con denuncia aceptada) | defendant |
| liminar | medida cautelar | injunction / preliminary ruling |
| Câmara dos Deputados | Cámara de Diputados | Chamber of Deputies |
| Assembleia Legislativa | Asamblea Legislativa (estatal) | state legislature |
| Defesa Civil | Defensa Civil | civil defense agency |
| R$ 2,3 bilhões | 2.300 millones de reales (R$) | 2.3 billion reais |

Regras próprias de cada língua:

- **Español.** Registro de agência (EFE, AFP en español): *dijo* como verbo padrão; evitar *señaló* em série, *arremetió*, *fustigó*. Cifras: *1.240*; *3,5%*. Nomes de instituições brasileiras em português na primeira menção, com tradução entre parênteses quando ajudar.
- **English.** AP Stylebook: *said* almost always; avoid *claimed* (implies doubt), *slammed*, *blasted*. Figures: *1,240*; *3.5%*. Spell out *percent* only in running prose if the house style requires; default to the symbol in data pieces.
- O verificador roda também sobre cada tradução, com a lista de termos carregados da língua de destino **[V]**.

## 9. Conversa com a IA

As respostas do chat seguem este guia. Além disso:

- Cada oração factual cita `claim_ids` **[V]**.
- Se o leitor usar um termo carregado, a IA não o adota; pode explicar que o termo é disputado e quem o usa.
- Quando a edição não tem a informação, a IA diz *a edição não traz informação sobre isso* e informa a data de corte.
