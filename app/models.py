"""Data model for Aletheia News.

Follows the four EII context documents (architecture, academic commentator,
design and infographics, visual style by country), adapted to the weekly
cadence of the Brazil edition. Layers:

  geopolitical  country, cleavage, pole
  media         outlet, outlet_position, ownership_funding, outlet_reliability
  content       article, event, article_event, edition, edition_event
  analytic      claim, claim_support, framing_annotation, coverage_snapshot,
                coverage_daily, blindspot_flag, neutral_brief, brief_sentence,
                human_review, loaded_term, data_gap
  academic      scholar, scholar_disclosure, scholar_position, discipline_map,
                commentary, commentary_statement, reference, open_question,
                peer_review, disciplinary_gap
  visual        palette, dataset, visual, visual_justification, visual_encoding,
                visual_mark, visual_control, visual_review, visual_gap,
                control_usage
  style         theme_country, cultural_reference, reference_position,
                exclusion_list, theme_section, theme_blind_test
  translation   translation
  conversation  chat_session, chat_message, chat_suggestion, chat_usage_daily

Invariants that matter for neutrality are enforced in code (app/rules) and,
where cheap, also as database constraints here.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, JSONType


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------- geopolitical

class Country(Base):
    __tablename__ = "country"
    id: Mapped[str] = mapped_column(String(2), primary_key=True)  # ISO 3166-1 alpha-2
    nombre: Mapped[str] = mapped_column(String(80))
    idiomas: Mapped[list] = mapped_column(JSONType, default=list)
    zona_horaria: Mapped[str] = mapped_column(String(64))
    fecha_inicializacion: Mapped[date] = mapped_column(Date)
    # Election dates, incoming government, etc. live here as sourced data, never in code.
    contexto: Mapped[list] = mapped_column(JSONType, default=list)  # [{texto, fuente, fecha}]
    data_gaps: Mapped[list] = mapped_column(JSONType, default=list)  # declared ingestion gaps


class Cleavage(Base):
    __tablename__ = "cleavage"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    slug: Mapped[str] = mapped_column(String(60))
    nombre: Mapped[str] = mapped_column(String(160))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    tipo: Mapped[str] = mapped_column(String(20), default="principal")  # principal/territorial/secundario/candidato
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    es_hipotesis: Mapped[bool] = mapped_column(Boolean, default=True)
    peso_relevancia: Mapped[float] = mapped_column(Float, default=1.0)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    poles: Mapped[list["Pole"]] = relationship(back_populates="cleavage", order_by="Pole.orden")
    __table_args__ = (UniqueConstraint("country_id", "slug", "vigente_desde"),)


class Pole(Base):
    __tablename__ = "pole"
    id: Mapped[int] = mapped_column(primary_key=True)
    cleavage_id: Mapped[int] = mapped_column(ForeignKey("cleavage.id"))
    slug: Mapped[str] = mapped_column(String(60))
    etiqueta: Mapped[str] = mapped_column(String(160))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    orden: Mapped[int] = mapped_column(Integer, default=0)
    cleavage: Mapped[Cleavage] = relationship(back_populates="poles")


# ----------------------------------------------------------------------- media

class Outlet(Base):
    __tablename__ = "outlet"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    nombre: Mapped[str] = mapped_column(String(160))
    tipo: Mapped[str] = mapped_column(String(20))  # diario/tv/radio/digital/agencia
    alcance: Mapped[str] = mapped_column(String(20))  # nacional/regional
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audiencia_estimada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    idioma: Mapped[str] = mapped_column(String(5), default="pt")
    # Official sources (Agência Brasil/EBC) are not assigned to any pole.
    es_fuente_oficial: Mapped[bool] = mapped_column(Boolean, default=False)
    feeds: Mapped[list] = mapped_column(JSONType, default=list)  # ingestion config (Phase 2)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    es_ficticio: Mapped[bool] = mapped_column(Boolean, default=False)


class OutletPosition(Base):
    """Estimated position per axis. Append-only: rows are never updated."""
    __tablename__ = "outlet_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"))
    cleavage_id: Mapped[int] = mapped_column(ForeignKey("cleavage.id"))
    score: Mapped[float] = mapped_column(Float)
    ic_inferior: Mapped[float] = mapped_column(Float)
    ic_superior: Mapped[float] = mapped_column(Float)
    metodo: Mapped[str] = mapped_column(String(200))
    n_articulos_base: Mapped[int] = mapped_column(Integer, default=0)
    provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    creado_en: Mapped[datetime] = _now()
    __table_args__ = (
        CheckConstraint("score >= -1 AND score <= 1", name="ck_outlet_score_range"),
        CheckConstraint("ic_inferior <= score AND score <= ic_superior", name="ck_outlet_ic"),
    )


class OwnershipFunding(Base):
    __tablename__ = "ownership_funding"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"))
    propietario: Mapped[str] = mapped_column(String(200))
    grupo_economico: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publicidad_federal_monto: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    periodo: Mapped[str] = mapped_column(String(20))
    fuente_dato: Mapped[str] = mapped_column(String(300))


class OutletReliability(Base):
    __tablename__ = "outlet_reliability"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"))
    correcciones_publicadas: Mapped[int] = mapped_column(Integer, default=0)
    verificaciones_fallidas: Mapped[int] = mapped_column(Integer, default=0)
    periodo: Mapped[str] = mapped_column(String(20))


# --------------------------------------------------------------------- content

class Edition(Base):
    __tablename__ = "edition"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    numero: Mapped[int] = mapped_column(Integer)
    semana_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Mon 00:00 BRT
    semana_fin: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Sun 23:59 BRT
    corte_ingesta: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Fri 23:59 BRT
    publicacion_prevista: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # Mon 06:00 BRT
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # borrador -> en_revision -> aprobada -> publicada
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    es_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobada_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    events: Mapped[list["EditionEvent"]] = relationship(order_by="EditionEvent.orden")
    __table_args__ = (UniqueConstraint("country_id", "numero"),)


class Event(Base):
    __tablename__ = "event"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    titulo_provisional: Mapped[str] = mapped_column(String(300))
    seccion: Mapped[str] = mapped_column(String(30))  # politica/economia/justica/sociedade/meio-ambiente/...
    secciones_tocadas: Mapped[list] = mapped_column(JSONType, default=list)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default="abierto")
    impacto: Mapped[int] = mapped_column(Integer, default=0)  # 0-100, ranks the cover (not audience)
    sensible: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sports/entertainment are excluded unless another domain is affected.
    tema_excepcional: Mapped[bool] = mapped_column(Boolean, default=False)
    razon_inclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    razon_inclusion_confirmada_por: Mapped[str | None] = mapped_column(String(120), nullable=True)
    es_ficticio: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("tema_excepcional = false OR razon_inclusion IS NOT NULL",
                        name="ck_event_exceptional_reason"),
    )


class EditionEvent(Base):
    __tablename__ = "edition_event"
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    orden: Mapped[int] = mapped_column(Integer)
    version_evento: Mapped[int] = mapped_column(Integer, default=1)  # "versão 2, edição do 12/10"
    event: Mapped[Event] = relationship()
    __table_args__ = (UniqueConstraint("edition_id", "event_id"),)


class Article(Base):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlet.id"))
    url: Mapped[str] = mapped_column(String(600))
    titular: Mapped[str] = mapped_column(String(500))
    # Full text is stored only if the outlet's terms allow it (internal analysis only).
    cuerpo: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuerpo_permitido: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_pub: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    autor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idioma: Mapped[str] = mapped_column(String(5), default="pt")
    hash_texto: Mapped[str] = mapped_column(String(64), unique=True)
    # embedding: added in Phase 2 migration (pgvector), see docs/decisiones.md
    es_ficticio: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleEvent(Base):
    __tablename__ = "article_event"
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), primary_key=True)
    score_similitud: Mapped[float] = mapped_column(Float, default=1.0)
    asignacion: Mapped[str] = mapped_column(String(10), default="auto")  # auto/manual


# -------------------------------------------------------------------- analytic

class Claim(Base):
    __tablename__ = "claim"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # public stable id, e.g. "c-1001"
    texto_normalizado: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(10))  # quien/que/cuando/donde/cifra/cita
    verificable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Result of the selection rule (app/rules/selection.py): llano | atribuido | excluido
    modo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    atribucion: Mapped[str | None] = mapped_column(String(300), nullable=True)  # "segundo X"
    medida: Mapped[str | None] = mapped_column(String(120), nullable=True)  # groups disputed figures
    valor: Mapped[float | None] = mapped_column(Float, nullable=True)
    unidad: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fuente_primaria: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # {nombre,url,verificada_en}
    supports: Mapped[list["ClaimSupport"]] = relationship(back_populates="claim")


class ClaimSupport(Base):
    __tablename__ = "claim_support"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claim.id"))
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    fragmento_fuente: Mapped[str] = mapped_column(Text)  # one sentence max in the UI
    postura: Mapped[str] = mapped_column(String(10))  # afirma/contradice/matiza
    confianza: Mapped[float] = mapped_column(Float, default=1.0)
    claim: Mapped[Claim] = relationship(back_populates="supports")
    article: Mapped[Article] = relationship()
    __table_args__ = (CheckConstraint("postura IN ('afirma','contradice','matiza')", name="ck_postura"),)


class FramingAnnotation(Base):
    """Also reused for academic commentary and visuals (target_tipo)."""
    __tablename__ = "framing_annotation"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_tipo: Mapped[str] = mapped_column(String(12), default="article")  # article/commentary/visual
    target_id: Mapped[int] = mapped_column(Integer)
    terminos_cargados: Mapped[list] = mapped_column(JSONType, default=list)
    marco: Mapped[str | None] = mapped_column(String(200), nullable=True)
    carga_emocional: Mapped[float | None] = mapped_column(Float, nullable=True)
    afirmaciones_omitidas: Mapped[list] = mapped_column(JSONType, default=list)  # claim codigos


class CoverageSnapshot(Base):
    """One closing snapshot per edition, per pole."""
    __tablename__ = "coverage_snapshot"
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    pole_id: Mapped[int] = mapped_column(ForeignKey("pole.id"))
    subject: Mapped[str] = mapped_column(String(160), default="evento")  # event or a derived fact
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    medios_que_cubren: Mapped[int] = mapped_column(Integer)
    medios_activos_del_polo: Mapped[int] = mapped_column(Integer)
    pct: Mapped[float] = mapped_column(Float)
    pct_ponderado_audiencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (CheckConstraint("medios_que_cubren <= medios_activos_del_polo", name="ck_cov_denominator"),)


class CoverageDaily(Base):
    """Daily curve of the week, used by timelines."""
    __tablename__ = "coverage_daily"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    pole_id: Mapped[int] = mapped_column(ForeignKey("pole.id"))
    dia: Mapped[date] = mapped_column(Date)
    articulos: Mapped[int] = mapped_column(Integer)


class BlindspotFlag(Base):
    __tablename__ = "blindspot_flag"
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    pole_id: Mapped[int] = mapped_column(ForeignKey("pole.id"))  # pole with LOW coverage
    subject: Mapped[str] = mapped_column(String(160))
    diferencia_cobertura: Mapped[float] = mapped_column(Float)
    umbral_usado: Mapped[float] = mapped_column(Float)
    impacto_estimado: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), default="provisional")  # provisional/confirmada/descartada


class LoadedTerm(Base):
    """Editable list of loaded terms. Reviewed each electoral cycle."""
    __tablename__ = "loaded_term"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    idioma: Mapped[str] = mapped_column(String(5))
    termino: Mapped[str] = mapped_column(String(80))
    patron: Mapped[str] = mapped_column(String(200))  # regex, case-insensitive, word bounded
    alternativa: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nota: Mapped[str] = mapped_column(Text, default="")
    # Allowed when the sentence is attributed or quoted; some allow a legal typification.
    permitido_si: Mapped[str] = mapped_column(String(30), default="atribuido_o_cita")
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)


class NeutralBrief(Base):
    __tablename__ = "neutral_brief"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    titulo: Mapped[str] = mapped_column(String(300))
    modelo: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40))
    fecha: Mapped[datetime] = _now()
    estado: Mapped[str] = mapped_column(String(20), default="borrador")  # borrador/verificada/aprobada/rechazada
    verificacion: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    sentences: Mapped[list["BriefSentence"]] = relationship(order_by="BriefSentence.orden")


class BriefSentence(Base):
    __tablename__ = "brief_sentence"
    id: Mapped[int] = mapped_column(primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("neutral_brief.id"))
    orden: Mapped[int] = mapped_column(Integer)
    parrafo: Mapped[int] = mapped_column(Integer, default=0)
    texto: Mapped[str] = mapped_column(Text)
    claim_ids: Mapped[list] = mapped_column(JSONType)  # claim codigos; never empty
    __table_args__ = (UniqueConstraint("brief_id", "orden"),)


class HumanReview(Base):
    __tablename__ = "human_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_tipo: Mapped[str] = mapped_column(String(20))  # brief/edition/translation/visual/event
    target_id: Mapped[int] = mapped_column(Integer)
    revisor: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(20))  # aprobada/rechazada/cambios
    comentarios: Mapped[str] = mapped_column(Text, default="")
    fecha: Mapped[datetime] = _now()


class FramingSummary(Base):
    """Per-pole headline column of the triptych (2-3 headlines + 'not mentioned')."""
    __tablename__ = "framing_summary"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    pole_id: Mapped[int] = mapped_column(ForeignKey("pole.id"))
    article_ids: Mapped[list] = mapped_column(JSONType, default=list)
    no_menciona: Mapped[list] = mapped_column(JSONType, default=list)  # claim codigos omitted by this pole


# -------------------------------------------------------------------- academic

class Scholar(Base):
    __tablename__ = "scholar"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    nombre: Mapped[str] = mapped_column(String(160))
    disciplina: Mapped[str] = mapped_column(String(80))
    subcampo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    afiliacion: Mapped[str] = mapped_column(String(200))
    pais: Mapped[str] = mapped_column(String(2))
    orcid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    idiomas: Mapped[list] = mapped_column(JSONType, default=list)
    activo_desde: Mapped[date] = mapped_column(Date)
    activo_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    es_ficticio: Mapped[bool] = mapped_column(Boolean, default=False)


class ScholarDisclosure(Base):
    __tablename__ = "scholar_disclosure"
    id: Mapped[int] = mapped_column(primary_key=True)
    scholar_id: Mapped[int] = mapped_column(ForeignKey("scholar.id"))
    tipo: Mapped[str] = mapped_column(String(20))  # financiamiento/cargo/militancia/consultoria/ninguna
    entidad: Mapped[str] = mapped_column(String(200))
    periodo: Mapped[str] = mapped_column(String(40))
    fuente: Mapped[str] = mapped_column(String(300))


class ScholarPosition(Base):
    __tablename__ = "scholar_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    scholar_id: Mapped[int] = mapped_column(ForeignKey("scholar.id"))
    cleavage_id: Mapped[int] = mapped_column(ForeignKey("cleavage.id"))
    score: Mapped[float] = mapped_column(Float)
    ic_inferior: Mapped[float] = mapped_column(Float)
    ic_superior: Mapped[float] = mapped_column(Float)
    metodo: Mapped[str] = mapped_column(String(200))
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)


class DisciplineMap(Base):
    __tablename__ = "discipline_map"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    disciplina: Mapped[str] = mapped_column(String(80))
    familia: Mapped[str] = mapped_column(String(40))  # historia/ciencias_sociales/derecho/ciencias_naturales/filosofia
    pregunta: Mapped[str] = mapped_column(Text)
    justificacion: Mapped[str] = mapped_column(Text, default="")
    propuesto_por: Mapped[str] = mapped_column(String(10), default="editor")  # sistema/editor
    estado: Mapped[str] = mapped_column(String(20), default="validado")


class Commentary(Base):
    """Only the background ('de fondo') format exists in the weekly cadence."""
    __tablename__ = "commentary"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    scholar_id: Mapped[int] = mapped_column(ForeignKey("scholar.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    tipo: Mapped[str] = mapped_column(String(10), default="fondo")
    tradicion_declarada: Mapped[str] = mapped_column(String(300))
    fecha: Mapped[datetime] = _now()
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    idioma: Mapped[str] = mapped_column(String(5), default="pt")
    cargado_por: Mapped[str] = mapped_column(String(120))  # editor who loaded the scholar's text
    statements: Mapped[list["CommentaryStatement"]] = relationship(order_by="CommentaryStatement.orden")
    open_questions: Mapped[list["OpenQuestion"]] = relationship()
    __table_args__ = (CheckConstraint("tipo = 'fondo'", name="ck_commentary_only_background"),)


class CommentaryStatement(Base):
    __tablename__ = "commentary_statement"
    id: Mapped[int] = mapped_column(primary_key=True)
    commentary_id: Mapped[int] = mapped_column(ForeignKey("commentary.id"))
    orden: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(Text)
    plano: Mapped[str] = mapped_column(String(14))  # descriptivo/explicativo/conceptual/normativo
    estatus_epistemico: Mapped[str] = mapped_column(String(14))  # consenso/mayoritaria/disputa/hipotesis/sin_evidencia
    escala_temporal: Mapped[str] = mapped_column(String(16))  # acontecimiento/coyuntura/larga_duracion/transversal
    disciplina: Mapped[str] = mapped_column(String(80))
    claim_ids: Mapped[list] = mapped_column(JSONType, default=list)
    reference_ids: Mapped[list] = mapped_column(JSONType, default=list)
    mecanismo: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidencia_que_refutaria: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Authorship of the text: humano (scholar) is mandatory for explicativo/normativo.
    autoria: Mapped[str] = mapped_column(String(10), default="humano")
    __table_args__ = (
        CheckConstraint("estatus_epistemico <> 'hipotesis' OR plano = 'explicativo'", name="ck_hypothesis_plane"),
        CheckConstraint("estatus_epistemico <> 'hipotesis' OR (mecanismo IS NOT NULL AND evidencia_que_refutaria IS NOT NULL)",
                        name="ck_hypothesis_refutation"),
        CheckConstraint("plano NOT IN ('explicativo','normativo') OR autoria = 'humano'", name="ck_no_llm_explanatory"),
    )


class Reference(Base):
    __tablename__ = "reference"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # articulo/libro/documento_oficial/dato
    rol: Mapped[str] = mapped_column(String(20))  # fundante/estado_del_arte/disidente/primaria
    cita: Mapped[str] = mapped_column(Text)
    doi_o_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    autores: Mapped[str] = mapped_column(String(400))
    anio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_por_pares: Mapped[bool] = mapped_column(Boolean, default=False)
    indicador_influencia: Mapped[float | None] = mapped_column(Float, nullable=True)
    verificada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # mandatory
    verificada_por: Mapped[str] = mapped_column(String(120))
    es_ficticia: Mapped[bool] = mapped_column(Boolean, default=False)


class OpenQuestion(Base):
    __tablename__ = "open_question"
    id: Mapped[int] = mapped_column(primary_key=True)
    commentary_id: Mapped[int] = mapped_column(ForeignKey("commentary.id"))
    pregunta: Mapped[str] = mapped_column(Text)
    razon: Mapped[str] = mapped_column(String(30))  # sin_estudios/otro_contexto/datos_inexistentes/irresoluble_hoy
    anadida_por: Mapped[str] = mapped_column(String(120))


class PeerReview(Base):
    __tablename__ = "peer_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    commentary_id: Mapped[int] = mapped_column(ForeignKey("commentary.id"))
    revisor_id: Mapped[int] = mapped_column(ForeignKey("scholar.id"))
    decision: Mapped[str] = mapped_column(String(20))
    objeciones: Mapped[str] = mapped_column(Text, default="")
    estatus_corregidos: Mapped[list] = mapped_column(JSONType, default=list)
    fuentes_ineludibles_omitidas: Mapped[list] = mapped_column(JSONType, default=list)


class DisciplinaryGap(Base):
    __tablename__ = "disciplinary_gap"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    disciplina: Mapped[str] = mapped_column(String(80))
    motivo: Mapped[str] = mapped_column(Text)


# ---------------------------------------------------------------------- visual

class Palette(Base):
    __tablename__ = "palette"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    cleavage_id: Mapped[int] = mapped_column(ForeignKey("cleavage.id"))
    asignacion_polo_color: Mapped[dict] = mapped_column(JSONType)  # {pole_slug: hex}
    contraste_verificado: Mapped[bool] = mapped_column(Boolean, default=False)
    prueba_ciega_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, default=True)


class Dataset(Base):
    __tablename__ = "dataset"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id"), nullable=True)  # series shown with this event
    fuente_primaria: Mapped[str] = mapped_column(String(300))
    metodo: Mapped[str] = mapped_column(Text)
    fecha_corte: Mapped[date] = mapped_column(Date)
    unidad: Mapped[str] = mapped_column(String(40))
    cobertura_territorial: Mapped[str] = mapped_column(String(120))
    licencia: Mapped[str] = mapped_column(String(80))
    verificada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    datos: Mapped[list] = mapped_column(JSONType, default=list)


class Visual(Base):
    __tablename__ = "visual"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    tipo: Mapped[str] = mapped_column(String(20))  # cobertura/puntociego/cifras/serie/...
    forma: Mapped[str] = mapped_column(String(40))
    nivel: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    brief_version: Mapped[int] = mapped_column(Integer, default=1)
    fecha_corte: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    spec: Mapped[dict] = mapped_column(JSONType, default=dict)  # template parameters
    __table_args__ = (CheckConstraint("nivel BETWEEN 0 AND 2", name="ck_visual_level_v1"),)


class VisualJustification(Base):
    __tablename__ = "visual_justification"
    id: Mapped[int] = mapped_column(primary_key=True)
    visual_id: Mapped[int] = mapped_column(ForeignKey("visual.id"), unique=True)
    pregunta_lector: Mapped[str] = mapped_column(Text)
    forma_de_la_informacion: Mapped[str] = mapped_column(String(80))
    filtro_superado: Mapped[str] = mapped_column(String(80))
    alternativa_textual_descartada: Mapped[str] = mapped_column(Text)
    aprobado_por: Mapped[str] = mapped_column(String(120))


class VisualEncoding(Base):
    __tablename__ = "visual_encoding"
    id: Mapped[int] = mapped_column(primary_key=True)
    visual_id: Mapped[int] = mapped_column(ForeignKey("visual.id"))
    canal: Mapped[str] = mapped_column(String(12))
    variable: Mapped[str] = mapped_column(String(80))
    escala: Mapped[str] = mapped_column(String(40))
    origen_eje: Mapped[float | None] = mapped_column(Float, nullable=True)
    corte_senalado: Mapped[bool] = mapped_column(Boolean, default=False)


class VisualMark(Base):
    __tablename__ = "visual_mark"
    id: Mapped[int] = mapped_column(primary_key=True)
    visual_id: Mapped[int] = mapped_column(ForeignKey("visual.id"))
    claim_ids: Mapped[list] = mapped_column(JSONType, default=list)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("dataset.id"), nullable=True)
    coverage_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("coverage_snapshot.id"), nullable=True)
    valor: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String(300))
    ic_inferior: Mapped[float | None] = mapped_column(Float, nullable=True)
    ic_superior: Mapped[float | None] = mapped_column(Float, nullable=True)
    denominador: Mapped[str | None] = mapped_column(String(80), nullable=True)


class VisualControl(Base):
    __tablename__ = "visual_control"
    id: Mapped[int] = mapped_column(primary_key=True)
    visual_id: Mapped[int] = mapped_column(ForeignKey("visual.id"))
    perspectiva: Mapped[str] = mapped_column(String(12))  # polo/eje/fuente/audiencia/escala
    pregunta_que_responde: Mapped[str] = mapped_column(Text)
    valor_por_defecto: Mapped[str] = mapped_column(String(80))


class VisualReview(Base):
    __tablename__ = "visual_review"
    id: Mapped[int] = mapped_column(primary_key=True)
    visual_id: Mapped[int] = mapped_column(ForeignKey("visual.id"))
    revisor: Mapped[str] = mapped_column(String(120))
    checklist: Mapped[list] = mapped_column(JSONType, default=list)
    decision: Mapped[str] = mapped_column(String(20))
    comentarios: Mapped[str] = mapped_column(Text, default="")


class VisualGap(Base):
    __tablename__ = "visual_gap"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    dato_faltante: Mapped[str] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(String(20))  # no_existe/no_verificable/reservado/no_comparable


class ControlUsage(Base):
    """Aggregated counts only. Never per reader."""
    __tablename__ = "control_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("visual_control.id"))
    periodo: Mapped[str] = mapped_column(String(20))
    usos: Mapped[int] = mapped_column(Integer, default=0)
    vistas: Mapped[int] = mapped_column(Integer, default=0)


# ----------------------------------------------------------------------- style

class ThemeCountry(Base):
    __tablename__ = "theme_country"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    tipografia_titulares: Mapped[str] = mapped_column(String(120))
    color_marca: Mapped[str] = mapped_column(String(9))
    textura_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    direccion_foto: Mapped[str] = mapped_column(Text, default="")
    tokens: Mapped[dict] = mapped_column(JSONType, default=dict)
    provisional: Mapped[bool] = mapped_column(Boolean, default=True)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)


class CulturalReference(Base):
    __tablename__ = "cultural_reference"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    nombre: Mapped[str] = mapped_column(String(200))
    familia: Mapped[str] = mapped_column(String(20))  # material/paisaje/tipografia/lenguaje
    decision: Mapped[str] = mapped_column(String(30))  # candidata/aceptada/solo_seccion/excluida
    justificacion: Mapped[str] = mapped_column(Text, default="")


class ReferencePosition(Base):
    __tablename__ = "reference_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("cultural_reference.id"))
    cleavage_id: Mapped[int] = mapped_column(ForeignKey("cleavage.id"))
    score: Mapped[float] = mapped_column(Float)
    ic_inferior: Mapped[float] = mapped_column(Float)
    ic_superior: Mapped[float] = mapped_column(Float)
    metodo: Mapped[str] = mapped_column(String(200))


class ExclusionList(Base):
    __tablename__ = "exclusion_list"
    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[str] = mapped_column(ForeignKey("country.id"))
    elemento: Mapped[str] = mapped_column(String(200))
    colores: Mapped[list] = mapped_column(JSONType, default=list)  # hex values for distance checks
    motivo: Mapped[str] = mapped_column(String(20))  # partidario/emblema/religioso/conflicto
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    vigente_desde: Mapped[date] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)


class ThemeSection(Base):
    __tablename__ = "theme_section"
    id: Mapped[int] = mapped_column(primary_key=True)
    theme_country_id: Mapped[int] = mapped_column(ForeignKey("theme_country.id"))
    seccion: Mapped[str] = mapped_column(String(30))
    tono_derivado: Mapped[str] = mapped_column(String(9))
    uso_textura: Mapped[bool] = mapped_column(Boolean, default=False)
    direccion_imagen: Mapped[str] = mapped_column(Text, default="")
    austeridad: Mapped[int] = mapped_column(Integer, default=0)  # higher = more austere


class ThemeBlindTest(Base):
    __tablename__ = "theme_blind_test"
    id: Mapped[int] = mapped_column(primary_key=True)
    theme_country_id: Mapped[int] = mapped_column(ForeignKey("theme_country.id"))
    fecha: Mapped[date] = mapped_column(Date)
    muestra_por_polo: Mapped[dict] = mapped_column(JSONType)
    reconocimiento: Mapped[float] = mapped_column(Float)
    inclinacion_percibida: Mapped[float] = mapped_column(Float)


# ----------------------------------------------------------------- translation

class Translation(Base):
    """Translated text of any translatable field. claim_ids travel with the text."""
    __tablename__ = "translation"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_tipo: Mapped[str] = mapped_column(String(30))  # brief_sentence/neutral_brief/event/claim/...
    source_id: Mapped[int] = mapped_column(Integer)
    campo: Mapped[str] = mapped_column(String(40), default="texto")
    idioma: Mapped[str] = mapped_column(String(5))
    texto: Mapped[str] = mapped_column(Text)
    claim_ids: Mapped[list] = mapped_column(JSONType, default=list)
    metodo: Mapped[str] = mapped_column(String(20))  # humano/maquina_revisada/maquina_sin_revisar
    revisor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fecha: Mapped[datetime] = _now()
    __table_args__ = (
        UniqueConstraint("source_tipo", "source_id", "campo", "idioma"),
        CheckConstraint("metodo IN ('humano','maquina_revisada','maquina_sin_revisar')", name="ck_tr_method"),
        CheckConstraint("metodo = 'maquina_sin_revisar' OR revisor IS NOT NULL", name="ck_tr_reviewer"),
    )


# ---------------------------------------------------------------- conversation

class ChatSession(Base):
    """No persistent reader identifier: a random id lives only in the tab."""
    __tablename__ = "chat_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    idioma: Mapped[str] = mapped_column(String(5))
    modo_factual: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = _now()
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_session.id", ondelete="CASCADE"))
    rol: Mapped[str] = mapped_column(String(10))  # lector/asistente
    contenido: Mapped[dict] = mapped_column(JSONType)  # for assistant: verified segments
    verificacion: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = _now()


class ChatSuggestion(Base):
    """Data a reader brought that is not in the edition; routed to extraction.
    Stored without any session link or personal data."""
    __tablename__ = "chat_suggestion"
    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("edition.id"))
    texto: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    creado_en: Mapped[datetime] = _now()


class ChatUsageDaily(Base):
    """Aggregate counters for the daily cost budget and quality metrics."""
    __tablename__ = "chat_usage_daily"
    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    preguntas: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    costo_centavos: Mapped[float] = mapped_column(Float, default=0)
    rechazos_verificador: Mapped[int] = mapped_column(Integer, default=0)
    negativas: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------- dispute

class Dispute(Base):
    """Public dispute channel: anyone can contest a sentence, claim, visual,
    commentary statement or outlet position, with evidence. Contact is optional."""
    __tablename__ = "dispute"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_tipo: Mapped[str] = mapped_column(String(30))  # brief_sentence/claim/visual/commentary_statement/outlet_position/theme
    target_ref: Mapped[str] = mapped_column(String(80))
    texto: Mapped[str] = mapped_column(Text)
    evidencia: Mapped[str] = mapped_column(Text, default="")
    contacto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="recibida")  # recibida/en_analisis/aceptada/rechazada
    resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = _now()
