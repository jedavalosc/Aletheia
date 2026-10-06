"""Interface strings in PT (main), ES and EN, and translation lookup helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

UI = {
    "site_name": {"pt": "Aletheia News Brasil", "es": "Aletheia News Brasil", "en": "Aletheia News Brasil"},
    "tagline": {"pt": "Edição semanal. Cada oração ligada às fontes que a sustentam.",
                "es": "Edición semanal. Cada oración enlazada a las fuentes que la respaldan.",
                "en": "Weekly edition. Every sentence linked to the sources behind it."},
    "demo_banner": {"pt": "Edição de demonstração — conteúdo fictício",
                    "es": "Edição de demonstração — conteúdo fictício (edición de demostración: contenido ficticio)",
                    "en": "Edição de demonstração — conteúdo fictício (demo edition: fictional content)"},
    "demo_banner_long": {"pt": "Estados, cidades, veículos, pessoas, cifras e referências desta edição são inventados para demonstrar o funcionamento da plataforma.",
                         "es": "Estados, ciudades, medios, personas, cifras y referencias de esta edición son inventados para demostrar el funcionamiento de la plataforma.",
                         "en": "The states, cities, outlets, people, figures and references in this edition are invented to show how the platform works."},
    "edition": {"pt": "Edição", "es": "Edición", "en": "Edition"},
    "edition_n": {"pt": "Edição n.º {n}", "es": "Edición n.º {n}", "en": "Edition no. {n}"},
    "cutoff": {"pt": "Data de corte", "es": "Fecha de corte", "en": "Data cutoff"},
    "cutoff_note": {"pt": "O que aconteceu depois de {d} não está nesta edição.",
                    "es": "Lo ocurrido después del {d} no está en esta edición.",
                    "en": "Anything that happened after {d} is not in this edition."},
    "week": {"pt": "Semana", "es": "Semana", "en": "Week"},
    "published": {"pt": "Publicada em", "es": "Publicada el", "en": "Published"},
    "approved_by": {"pt": "Aprovada por", "es": "Aprobada por", "en": "Approved by"},
    "version": {"pt": "Versão", "es": "Versión", "en": "Version"},
    "version_history": {"pt": "Histórico de versões", "es": "Historial de versiones", "en": "Version history"},
    "version_line": {"pt": "versão {v}, edição de {d}", "es": "versión {v}, edición del {d}", "en": "version {v}, edition of {d}"},
    "methodology": {"pt": "Metodologia", "es": "Metodología", "en": "Methodology"},
    "dispute": {"pt": "Contestar", "es": "Disputar", "en": "Dispute"},
    "dispute_long": {"pt": "Canal de contestação", "es": "Canal de disputa", "en": "Dispute channel"},
    "media_index": {"pt": "Índice de veículos", "es": "Índice de medios", "en": "Outlet index"},
    "events_by_impact": {"pt": "Eventos da semana, por impacto", "es": "Eventos de la semana, por impacto",
                         "en": "This week's events, by impact"},
    "impact_note": {"pt": "Ordem por impacto estimado, não por audiência.", "es": "Orden por impacto estimado, no por audiencia.",
                    "en": "Ordered by estimated impact, not by audience."},
    "chronicle": {"pt": "Crônica", "es": "Crónica", "en": "Chronicle"},
    "read_chronicle": {"pt": "Ler a crônica", "es": "Leer la crónica", "en": "Read the chronicle"},
    "sources_paragraph": {"pt": "Fontes deste parágrafo", "es": "Fuentes de este párrafo", "en": "Sources for this paragraph"},
    "show_sources": {"pt": "Mostrar fontes desta oração", "es": "Mostrar fuentes de esta oración", "en": "Show sources for this sentence"},
    "claim": {"pt": "Afirmação", "es": "Afirmación", "en": "Claim"},
    "mode_llano": {"pt": "Fato estabelecido", "es": "Hecho establecido", "en": "Established fact"},
    "mode_atribuido": {"pt": "Atribuído", "es": "Atribuido", "en": "Attributed"},
    "mode_excluido": {"pt": "Excluído", "es": "Excluido", "en": "Excluded"},
    "mode_llano_why": {"pt": "Respaldo em veículos de pelo menos dois polos ou em fonte primária.",
                       "es": "Respaldo en medios de al menos dos polos o en fuente primaria.",
                       "en": "Supported by outlets of at least two poles or by a primary source."},
    "mode_atribuido_why": {"pt": "Respaldo em um só polo ou cifra em disputa: aparece atribuído.",
                           "es": "Respaldo en un solo polo o cifra en disputa: aparece atribuido.",
                           "en": "Supported by one pole only, or a disputed figure: shown attributed."},
    "primary_source": {"pt": "Fonte primária", "es": "Fuente primaria", "en": "Primary source"},
    "supported_by": {"pt": "Respaldada por", "es": "Respaldada por", "en": "Supported by"},
    "stance_afirma": {"pt": "afirma", "es": "afirma", "en": "affirms"},
    "stance_contradice": {"pt": "contradiz", "es": "contradice", "en": "contradicts"},
    "stance_matiza": {"pt": "matiza", "es": "matiza", "en": "qualifies"},
    "original_pt": {"pt": "", "es": "texto original en portugués", "en": "original text in Portuguese"},
    "open_original": {"pt": "abrir original", "es": "abrir original", "en": "open original"},
    "no_pole": {"pt": "sem polo atribuído", "es": "sin polo asignado", "en": "no pole assigned"},
    "official_source": {"pt": "fonte oficial", "es": "fuente oficial", "en": "official source"},
    "how_covered": {"pt": "Como cada polo cobriu", "es": "Cómo lo cubrió cada polo", "en": "How each pole covered it"},
    "not_mention": {"pt": "O que este enfoque não menciona", "es": "Lo que este enfoque no menciona",
                    "en": "What this framing leaves out"},
    "not_mention_none": {"pt": "Nada com respaldo amplo ficou de fora.", "es": "Nada con respaldo amplio quedó fuera.",
                         "en": "Nothing with broad support was left out."},
    "not_mention_measure": {"pt": "Cifra: {m}", "es": "Cifra: {m}", "en": "Figure: {m}"},
    "loaded_legend": {"pt": "Termos carregados aparecem destacados.", "es": "Los términos cargados aparecen resaltados.",
                      "en": "Loaded terms are highlighted."},
    "axis": {"pt": "Eixo", "es": "Eje", "en": "Axis"},
    "axis_switch": {"pt": "Ver por eixo", "es": "Ver por eje", "en": "View by axis"},
    "pole_order_note": {"pt": "A ordem dos polos alterna entre eventos; o registro é público na metodologia.",
                        "es": "El orden de los polos alterna entre eventos; el registro es público en la metodología.",
                        "en": "Pole order alternates between events; the log is public on the methodology page."},
    "coverage": {"pt": "Cobertura", "es": "Cobertura", "en": "Coverage"},
    "coverage_q": {"pt": "Quantos veículos de cada polo cobriram o evento?", "es": "¿Cuántos medios de cada polo cubrieron el evento?",
                   "en": "How many outlets of each pole covered the event?"},
    "of_outlets": {"pt": "{a} de {b} veículos", "es": "{a} de {b} medios", "en": "{a} of {b} outlets"},
    "by_outlets": {"pt": "% de veículos", "es": "% de medios", "en": "% of outlets"},
    "by_audience": {"pt": "% ponderado por audiência", "es": "% ponderado por audiencia", "en": "% weighted by audience"},
    "audience_weighted": {"pt": "ponderado por audiência", "es": "ponderado por audiencia", "en": "audience-weighted"},
    "blindspot": {"pt": "Cobertura baixa no polo {p}", "es": "Cobertura baja en el polo {p}", "en": "Low coverage in the {p} pole"},
    "blindspot_note": {"pt": "Observação de cobertura, não juízo de intenção. Bandeira provisória.",
                       "es": "Observación de cobertura, no juicio de intención. Bandera provisional.",
                       "en": "A coverage observation, not a judgement of intent. Provisional flag."},
    "blindspot_subject": {"pt": "Fato derivado", "es": "Hecho derivado", "en": "Derived fact"},
    "data_gap": {"pt": "Vazio declarado", "es": "Vacío declarado", "en": "Declared gap"},
    "source": {"pt": "Fonte", "es": "Fuente", "en": "Source"},
    "denominator": {"pt": "Denominador", "es": "Denominador", "en": "Denominator"},
    "figures_by_source": {"pt": "Cifras por fonte", "es": "Cifras por fuente", "en": "Figures by source"},
    "figures_note": {"pt": "Cada fonte com sua cifra. Nunca somadas nem promediadas.",
                     "es": "Cada fuente con su cifra. Nunca sumadas ni promediadas.",
                     "en": "Each source with its own figure. Never added or averaged."},
    "series": {"pt": "Série recorrente", "es": "Serie recurrente", "en": "Recurring series"},
    "factual_mode": {"pt": "Modo Factual Puro", "es": "Modo Factual Puro", "en": "Pure Factual Mode"},
    "factual_on": {"pt": "Ativado: só a crônica e suas fontes.", "es": "Activado: solo la crónica y sus fuentes.",
                   "en": "On: only the chronicle and its sources."},
    "see_coverage": {"pt": "ver como foi coberto", "es": "ver cómo lo cubrieron", "en": "see how it was covered"},
    "see_academic": {"pt": "ver análise acadêmica", "es": "ver análisis académico", "en": "see academic analysis"},
    "academic_label": {"pt": "Análise acadêmica. Interpretação assinada; não faz parte da crônica",
                       "es": "Análisis académico. Interpretación firmada; no forma parte de la crónica",
                       "en": "Academic analysis. Signed interpretation; not part of the chronicle"},
    "tradition": {"pt": "Tradição declarada", "es": "Tradición declarada", "en": "Declared tradition"},
    "what_we_dont_know": {"pt": "O que não sabemos", "es": "Lo que no sabemos", "en": "What we don't know"},
    "why_unknown": {"pt": "Por que não há resposta", "es": "Por qué no hay respuesta", "en": "Why there is no answer"},
    "commentator": {"pt": "Comentador(a)", "es": "Comentador(a)", "en": "Commentator"},
    "peer_reviewer": {"pt": "Revisão por pares", "es": "Revisión por pares", "en": "Peer review"},
    "disclosure": {"pt": "Declaração de interesses", "es": "Declaración de intereses", "en": "Disclosure of interests"},
    "disciplines": {"pt": "Mapa disciplinar", "es": "Mapa disciplinar", "en": "Discipline map"},
    "no_commentator_from": {"pt": "Sem comentário disponível desde: {d}", "es": "Sin comentario disponible desde: {d}",
                            "en": "No commentary available from: {d}"},
    "reserved_plane": {"pt": "Planos explicativo e normativo: reservados ao comentador humano. Na demonstração, não foram preenchidos, porque um modelo de linguagem não redige esses enunciados.",
                       "es": "Planos explicativo y normativo: reservados al comentador humano. En la demostración no se llenaron, porque un modelo de lenguaje no redacta esos enunciados.",
                       "en": "Explanatory and normative planes: reserved for the human commentator. They are left empty in the demo, because a language model does not draft those statements."},
    "demo_text_note": {"pt": "Texto de demonstração.", "es": "Texto de demostración.", "en": "Demo text."},
    "role_fundante": {"pt": "obra fundante", "es": "obra fundante", "en": "foundational work"},
    "role_estado_del_arte": {"pt": "estado da arte", "es": "estado del arte", "en": "state of the art"},
    "role_disidente": {"pt": "crítica dissidente", "es": "crítica disidente", "en": "dissenting critique"},
    "role_primaria": {"pt": "fonte primária", "es": "fuente primaria", "en": "primary source"},
    "current": {"pt": "atual", "es": "actual", "en": "current"},
    "references": {"pt": "Referências", "es": "Referencias", "en": "References"},
    "fictional_ref": {"pt": "referência fictícia", "es": "referencia ficticia", "en": "fictional reference"},
    "plane_descriptivo": {"pt": "Descritivo", "es": "Descriptivo", "en": "Descriptive"},
    "plane_explicativo": {"pt": "Explicativo", "es": "Explicativo", "en": "Explanatory"},
    "plane_conceptual": {"pt": "Conceitual", "es": "Conceptual", "en": "Conceptual"},
    "plane_normativo": {"pt": "Normativo", "es": "Normativo", "en": "Normative"},
    "status_consenso": {"pt": "Consenso", "es": "Consenso", "en": "Consensus"},
    "status_mayoritaria": {"pt": "Posição majoritária", "es": "Posición mayoritaria", "en": "Majority position"},
    "status_disputa": {"pt": "Disputa aberta", "es": "Disputa abierta", "en": "Open dispute"},
    "status_hipotesis": {"pt": "Hipótese", "es": "Hipótesis", "en": "Hypothesis"},
    "status_sin_evidencia": {"pt": "Sem evidência", "es": "Sin evidencia", "en": "No evidence"},
    "scale_acontecimiento": {"pt": "Acontecimento", "es": "Acontecimiento", "en": "Event"},
    "scale_coyuntura": {"pt": "Conjuntura", "es": "Coyuntura", "en": "Conjuncture"},
    "scale_larga_duracion": {"pt": "Longa duração", "es": "Larga duración", "en": "Long term"},
    "scale_transversal": {"pt": "Transversal", "es": "Transversal", "en": "Cross-cutting"},
    "reason_sin_estudios": {"pt": "Não há estudos", "es": "No hay estudios", "en": "No studies"},
    "reason_otro_contexto": {"pt": "Estudos de outros contextos", "es": "Estudios de otros contextos", "en": "Studies from other contexts"},
    "reason_datos_inexistentes": {"pt": "Dados inexistentes ou reservados", "es": "Datos inexistentes o reservados", "en": "Data missing or restricted"},
    "reason_irresoluble_hoy": {"pt": "Irresolúvel com a evidência atual", "es": "Irresoluble con la evidencia actual", "en": "Unresolvable with current evidence"},
    "machine_tr": {"pt": "Tradução automática sem revisão humana.", "es": "Traducción automática sin revisión humana.",
                   "en": "Machine translation, not reviewed by a person."},
    "machine_tr_reviewed": {"pt": "Tradução automática revisada por {r}.", "es": "Traducción automática revisada por {r}.",
                            "en": "Machine translation reviewed by {r}."},
    "human_tr": {"pt": "Tradução humana.", "es": "Traducción humana.", "en": "Human translation."},
    "language": {"pt": "Idioma", "es": "Idioma", "en": "Language"},
    "skip": {"pt": "Pular para o conteúdo", "es": "Saltar al contenido", "en": "Skip to content"},
    "section_politica": {"pt": "Política", "es": "Política", "en": "Politics"},
    "section_justica": {"pt": "Justiça", "es": "Justicia", "en": "Justice"},
    "section_economia": {"pt": "Economia", "es": "Economía", "en": "Economy"},
    "section_meio-ambiente": {"pt": "Meio ambiente", "es": "Medio ambiente", "en": "Environment"},
    "section_sociedade": {"pt": "Sociedade", "es": "Sociedad", "en": "Society"},
    "section_saude": {"pt": "Saúde", "es": "Salud", "en": "Health"},
    "section_ciencia": {"pt": "Ciência", "es": "Ciencia", "en": "Science"},
    "section_educacao": {"pt": "Educação", "es": "Educación", "en": "Education"},
    "section_internacional": {"pt": "Internacional", "es": "Internacional", "en": "International"},
    "exceptional": {"pt": "Inclusão excepcional", "es": "Inclusión excepcional", "en": "Exceptional inclusion"},
    "disputed_table": {"pt": "Cifras em disputa", "es": "Cifras en disputa", "en": "Disputed figures"},
    "figure": {"pt": "Cifra", "es": "Cifra", "en": "Figure"},
    "chat_open": {"pt": "Conversar sobre a edição", "es": "Conversar sobre la edición", "en": "Discuss this edition"},
    "chat_title": {"pt": "Conversa sobre a edição", "es": "Conversación sobre la edición", "en": "Conversation about the edition"},
    "chat_intro": {"pt": "Responde só com o que está publicado nesta edição, com as fontes de cada afirmação. Não navega na internet nem dá opinião.",
                   "es": "Responde solo con lo publicado en esta edición, con las fuentes de cada afirmación. No navega por internet ni opina.",
                   "en": "Answers only from what this edition published, citing sources for every claim. It does not browse the web or give opinions."},
    "chat_privacy": {"pt": "Sem conta e sem identificador persistente. As conversas são guardadas por {d} dias só para auditoria de qualidade e depois apagadas (LGPD).",
                     "es": "Sin cuenta ni identificador persistente. Las conversaciones se guardan {d} días solo para auditoría de calidad y luego se borran (LGPD).",
                     "en": "No account and no persistent identifier. Conversations are kept for {d} days for quality audits only, then deleted (LGPD)."},
    "chat_placeholder": {"pt": "Pergunte sobre a edição…", "es": "Pregunte sobre la edición…", "en": "Ask about the edition…"},
    "chat_send": {"pt": "Enviar", "es": "Enviar", "en": "Send"},
    "chat_close": {"pt": "Fechar", "es": "Cerrar", "en": "Close"},
    "chat_verifying": {"pt": "Verificando as fontes da resposta…", "es": "Verificando las fuentes de la respuesta…",
                       "en": "Checking the sources of the answer…"},
    "chat_unavailable": {"pt": "A conversa não está disponível agora.", "es": "La conversación no está disponible ahora.",
                         "en": "The conversation is not available right now."},
    "seg_fato": {"pt": "Fato da crônica", "es": "Hecho de la crónica", "en": "Chronicle fact"},
    "seg_interpretacao": {"pt": "Interpretação acadêmica", "es": "Interpretación académica", "en": "Academic interpretation"},
    "seg_metodologia": {"pt": "Metodologia", "es": "Metodología", "en": "Methodology"},
    "seg_cobertura": {"pt": "Cobertura", "es": "Cobertura", "en": "Coverage"},
    "chat_no_info": {"pt": "A edição não traz informação sobre isso.", "es": "La edición no trae información sobre eso.",
                     "en": "The edition has no information on that."},
    "chat_cutoff_suffix": {"pt": "Data de corte: {d}.", "es": "Fecha de corte: {d}.", "en": "Data cutoff: {d}."},
    "chat_no_opinion": {"pt": "Não dou opinião sobre quem tem razão. Segue o que a edição estabelece e o que está em disputa.",
                        "es": "No doy opinión sobre quién tiene razón. Sigue lo que la edición establece y lo que está en disputa.",
                        "en": "I don't give opinions on who is right. Here is what the edition establishes and what is disputed."},
    "chat_no_prediction": {"pt": "Não faço previsões. Segue o que a edição registra até a data de corte.",
                           "es": "No hago predicciones. Sigue lo que la edición registra hasta la fecha de corte.",
                           "en": "I don't make predictions. Here is what the edition records up to the cutoff."},
    "chat_injection": {"pt": "Só converso sobre o conteúdo desta edição, com as regras da plataforma.",
                       "es": "Solo converso sobre el contenido de esta edición, con las reglas de la plataforma.",
                       "en": "I only discuss the content of this edition, under the platform's rules."},
    "chat_new_data": {"pt": "Esse dado não está na edição; não posso confirmá-lo nem desmenti-lo. Ele foi registrado como sugestão para a equipe.",
                      "es": "Ese dato no está en la edición; no puedo confirmarlo ni desmentirlo. Quedó registrado como sugerencia para el equipo.",
                      "en": "That information is not in the edition; I can neither confirm nor deny it. It has been logged as a suggestion for the team."},
    "chat_fallback": {"pt": "Não consegui formular uma resposta verificável. Estas são as afirmações da edição mais próximas da pergunta.",
                      "es": "No logré formular una respuesta verificable. Estas son las afirmaciones de la edición más cercanas a la pregunta.",
                      "en": "I could not produce a verifiable answer. These are the edition's claims closest to the question."},
    "chat_rate": {"pt": "Muitas perguntas em pouco tempo. Tente de novo em alguns minutos.",
                  "es": "Demasiadas preguntas en poco tiempo. Intente de nuevo en unos minutos.",
                  "en": "Too many questions in a short time. Please try again in a few minutes."},
    "no_edition": {"pt": "Nenhuma edição publicada ainda.", "es": "Todavía no hay ediciones publicadas.",
                   "en": "No edition has been published yet."},
    "archive": {"pt": "Edições anteriores", "es": "Ediciones anteriores", "en": "Past editions"},
    "position": {"pt": "Posição estimada", "es": "Posición estimada", "en": "Estimated position"},
    "interval": {"pt": "intervalo", "es": "intervalo", "en": "interval"},
    "method": {"pt": "Método", "es": "Método", "en": "Method"},
    "provisional": {"pt": "provisória", "es": "provisional", "en": "provisional"},
    "hypothesis_axis": {"pt": "Eixo em hipótese, a validar", "es": "Eje en hipótesis, a validar", "en": "Axis is a hypothesis, to be validated"},
    "inactive_axis": {"pt": "inativo", "es": "inactivo", "en": "inactive"},
    "back": {"pt": "Voltar à edição", "es": "Volver a la edición", "en": "Back to the edition"},
    "fictional": {"pt": "fictício", "es": "ficticio", "en": "fictional"},
}


def t(key: str, lang: str, **kw) -> str:
    entry = UI.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry["pt"]
    return text.format(**kw) if kw else text


class Tr:
    """Cached lookup of translated database content."""

    def __init__(self, s: Session):
        self.cache: dict[tuple, m.Translation] = {}
        for row in s.scalars(select(m.Translation)):
            self.cache[(row.source_tipo, row.source_id, row.campo, row.idioma)] = row

    def get(self, tipo: str, sid: int, campo: str, lang: str, default: str) -> str:
        if lang == "pt":
            row = self.cache.get((tipo, sid, campo, "pt"))
            return row.texto if row else default
        row = self.cache.get((tipo, sid, campo, lang))
        return row.texto if row else default

    def row(self, tipo: str, sid: int, campo: str, lang: str) -> m.Translation | None:
        return self.cache.get((tipo, sid, campo, lang))


def fmt_date(d, lang: str) -> str:
    months = {
        "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
        "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    }
    mo = months[lang][d.month - 1]
    if lang == "en":
        return f"{mo} {d.day}, {d.year}"
    return f"{d.day} de {mo} de {d.year}"


def fmt_datetime_brt(dt, lang: str) -> str:
    from zoneinfo import ZoneInfo
    local = dt.astimezone(ZoneInfo("America/Sao_Paulo"))
    hhmm = local.strftime("%H:%M")
    if lang == "en":
        return f"{fmt_date(local, lang)}, {hhmm} BRT"
    return f"{fmt_date(local, lang)}, {hhmm} (horário de Brasília)" if lang == "pt" else f"{fmt_date(local, lang)}, {hhmm} (hora de Brasilia)"


def fmt_pct(x: float | None, lang: str) -> str:
    if x is None:
        return "—"
    return f"{round(x * 100)}%"


def fmt_num(v: float, lang: str) -> str:
    if v == int(v):
        s = f"{int(v):,}"
    else:
        s = f"{v:,.1f}"
    if lang in ("pt", "es"):
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s
