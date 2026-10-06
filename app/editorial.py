"""Editorial workflow: verification in every language, human approval gates.

Nothing is published without a named human editor. Approval of an edition
is refused while any gate fails; the reasons are returned to the panel.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .config import LANGS
from .rules.loaded_terms import Term
from .rules.verifier import ClaimRef, verify_brief

MIN_EVENTS, MAX_EVENTS = 6, 12


def load_terms(s: Session, country_id: str, lang: str | None = None, at: date | None = None) -> list[Term]:
    at = at or date.today()
    q = select(m.LoadedTerm).where(m.LoadedTerm.country_id == country_id, m.LoadedTerm.vigente_desde <= at)
    if lang:
        q = q.where(m.LoadedTerm.idioma == lang)
    return [Term(t.termino, t.patron, t.idioma, t.permitido_si, t.alternativa) for t in s.scalars(q)
            if t.vigente_hasta is None or t.vigente_hasta >= at]


def claim_refs(s: Session, event_ids: list[int] | None = None) -> dict[str, ClaimRef]:
    q = select(m.Claim)
    if event_ids is not None:
        q = q.where(m.Claim.event_id.in_(event_ids))
    return {c.codigo: ClaimRef(c.codigo, c.event_id, c.modo, c.medida, c.valor) for c in s.scalars(q)}


def translation_of(s: Session, tipo: str, sid: int, campo: str, lang: str) -> m.Translation | None:
    return s.scalars(select(m.Translation).where(m.Translation.source_tipo == tipo, m.Translation.source_id == sid,
                                                 m.Translation.campo == campo, m.Translation.idioma == lang)).first()


def verify_brief_all_languages(s: Session, brief: m.NeutralBrief) -> dict:
    event = s.get(m.Event, brief.event_id)
    claims = claim_refs(s, [brief.event_id])
    out = {}
    sents = s.scalars(select(m.BriefSentence).where(m.BriefSentence.brief_id == brief.id)
                      .order_by(m.BriefSentence.orden)).all()
    for lang in LANGS:
        terms = load_terms(s, event.country_id, lang)
        rows = []
        missing = []
        for st in sents:
            if lang == "pt":
                rows.append({"orden": st.orden, "texto": st.texto, "claim_ids": st.claim_ids})
            else:
                tr = translation_of(s, "brief_sentence", st.id, "texto", lang)
                if tr is None:
                    missing.append(st.orden)
                    continue
                if sorted(tr.claim_ids) != sorted(st.claim_ids):
                    missing.append(st.orden)
                rows.append({"orden": st.orden, "texto": tr.texto, "claim_ids": tr.claim_ids})
        res = verify_brief(rows, brief.event_id, claims, terms, lang).as_dict()
        for o in missing:
            res["ok"] = False
            res["issues"].append({"orden": o, "codigo": "traduccion_faltante_o_claims_distintos",
                                  "detalle": "Tradução ausente ou com claim_ids diferentes do original"})
        out[lang] = res
    return out


def approve_brief(s: Session, brief: m.NeutralBrief, editor: str, comentarios: str = "") -> None:
    result = verify_brief_all_languages(s, brief)
    brief.verificacion = result
    if not all(r["ok"] for r in result.values()):
        raise ValueError("A crônica não passou no verificador em todas as línguas; não pode ser aprovada.")
    brief.estado = "aprobada"
    s.add(m.HumanReview(target_tipo="brief", target_id=brief.id, revisor=editor, decision="aprobada",
                        comentarios=comentarios))


def mark_translation_reviewed(s: Session, tr: m.Translation, editor: str) -> None:
    tr.metodo = "maquina_revisada"
    tr.revisor = editor
    tr.fecha = datetime.now(timezone.utc)


def edition_gates(s: Session, ed: m.Edition) -> list[str]:
    problems: list[str] = []
    n = len(ed.events)
    if not ed.es_demo and not (MIN_EVENTS <= n <= MAX_EVENTS):
        problems.append(f"A edição tem {n} eventos; o intervalo é {MIN_EVENTS}–{MAX_EVENTS}.")
    for ee in ed.events:
        ev = ee.event
        brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id,
                                                      m.NeutralBrief.edition_id == ed.id)
                          .order_by(m.NeutralBrief.version.desc())).first()
        if brief is None:
            problems.append(f"[{ev.slug}] sem crônica")
            continue
        if brief.estado != "aprobada":
            problems.append(f"[{ev.slug}] crônica não aprovada por editor (estado: {brief.estado})")
        if ev.tema_excepcional and not ev.razon_inclusion_confirmada_por:
            problems.append(f"[{ev.slug}] inclusão excepcional sem confirmação do editor")
        for v in s.scalars(select(m.Visual).where(m.Visual.event_id == ev.id, m.Visual.edition_id == ed.id)):
            if v.estado not in ("verificada", "aprobada"):
                problems.append(f"[{ev.slug}] peça visual {v.tipo} não verificada")
    return problems


def approve_edition(s: Session, ed: m.Edition, editor: str) -> list[str]:
    problems = edition_gates(s, ed)
    if problems:
        return problems
    ed.estado = "publicada"
    ed.aprobada_por = editor
    ed.publicada_en = datetime.now(timezone.utc)
    s.add(m.HumanReview(target_tipo="edition", target_id=ed.id, revisor=editor, decision="aprobada"))
    return []
