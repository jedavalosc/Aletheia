"""Load the FICTIONAL demo edition through the normal code paths:
selection rule -> coverage and blind spots -> framing -> brief verifier
(in all three languages) -> standard visuals. Nothing is marked approved
unless an editor approves it (panel) or --aprovar-como is given explicitly."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..analytics.core import run_event
from ..analytics.visuals import build_standard_visuals
from ..editorial import verify_brief_all_languages
from . import demo_content as D
from .brasil import _tr, seed_brasil

DEMO_METHOD = "Demonstração: posição inventada para o exemplo, sem estimação"
TRANSLATOR = "maquina_sin_revisar"


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def seed_demo(s: Session, approve_as: str | None = None) -> m.Edition:
    seed_brasil(s)
    if s.scalars(select(m.Edition).where(m.Edition.country_id == "BR", m.Edition.numero == D.EDITION["numero"])).first():
        raise SystemExit("A edição de demonstração já existe. Use 'reset-demo' para recriá-la.")
    axes = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == "BR").order_by(m.Cleavage.orden)).all()
    start = _dt(D.EDITION["semana_inicio"])
    ed = m.Edition(country_id="BR", numero=D.EDITION["numero"], semana_inicio=start,
                   semana_fin=_dt(D.EDITION["semana_fin"]), corte_ingesta=_dt(D.EDITION["corte_ingesta"]),
                   publicacion_prevista=_dt(D.EDITION["publicacion_prevista"]), estado="borrador", es_demo=True)
    s.add(ed)
    s.flush()

    # Fictional outlets and invented positions (provisional, demo method).
    outlets: dict[str, m.Outlet] = {}
    for code, nombre, tipo, alcance, region, aud, *scores in D.OUTLETS:
        o = m.Outlet(country_id="BR", nombre=nombre, tipo=tipo, alcance=alcance, region=region,
                     audiencia_estimada=aud, url=f"https://{code}.exemplo.invalid", idioma="pt", es_ficticio=True)
        s.add(o)
        s.flush()
        outlets[code] = o
        for axis, sc in zip(axes[:3], scores):
            lo, hi = max(-1, sc - D.CI_HALF_WIDTH), min(1, sc + D.CI_HALF_WIDTH)
            s.add(m.OutletPosition(outlet_id=o.id, cleavage_id=axis.id, score=sc, ic_inferior=round(lo, 3),
                                   ic_superior=round(hi, 3), metodo=DEMO_METHOD, n_articulos_base=0,
                                   provisional=True, vigente_desde=date(2026, 9, 1)))
    code, nombre, tipo, alcance, region, aud = D.OFFICIAL_OUTLET
    mu = m.Outlet(country_id="BR", nombre=nombre, tipo=tipo, alcance=alcance, region=region, audiencia_estimada=aud,
                  url=f"https://{code}.exemplo.invalid", idioma="pt", es_fuente_oficial=True, es_ficticio=True)
    s.add(mu)
    s.flush()
    outlets[code] = mu

    for order, ev in enumerate(D.EVENTS):
        event = m.Event(country_id="BR", slug=ev["slug"], titulo_provisional=ev["titulo"]["pt"], seccion=ev["seccion"],
                        secciones_tocadas=ev["secciones"], fecha_inicio=start + timedelta(days=ev["fecha"]),
                        impacto=ev["impacto"], sensible=ev["sensible"], tema_excepcional=ev["excepcional"],
                        razon_inclusion=ev["razon"]["pt"] if ev["razon"] else None, es_ficticio=True)
        s.add(event)
        s.flush()
        for lang in ("es", "en"):
            _tr(s, "event", event.id, "titulo", lang, ev["titulo"][lang])
            if ev["razon"]:
                _tr(s, "event", event.id, "razon_inclusion", lang, ev["razon"][lang])
        s.add(m.EditionEvent(edition_id=ed.id, event_id=event.id, orden=order, version_evento=1))

        arts: dict[str, m.Article] = {}
        for ocode, day, headline in ev["articles"]:
            fecha = start + timedelta(days=day, hours=9 + (hash(ocode) % 8))
            a = m.Article(outlet_id=outlets[ocode].id, url=f"https://{ocode}.exemplo.invalid/{ev['slug']}",
                          titular=headline, cuerpo=None, cuerpo_permitido=False, fecha_pub=fecha, idioma="pt",
                          hash_texto=hashlib.sha256(f"{ocode}|{ev['slug']}|{headline}".encode()).hexdigest(),
                          es_ficticio=True)
            s.add(a)
            s.flush()
            arts[ocode] = a
            s.add(m.ArticleEvent(article_id=a.id, event_id=event.id, score_similitud=1.0, asignacion="manual"))

        for c in ev["claims"]:
            medida = c.get("medida")
            claim = m.Claim(event_id=event.id, codigo=c["codigo"], texto_normalizado=c["texto"]["pt"], tipo=c["tipo"],
                            verificable=True, atribucion=c.get("atribucion"),
                            medida=medida["pt"] if medida else None, valor=c.get("valor"), unidad=c.get("unidad"),
                            fuente_primaria={"nombre": c["primaria"], "url": None,
                                             "verificada_en": "2026-10-02 (dado fictício)"} if c.get("primaria") else None)
            s.add(claim)
            s.flush()
            for lang in ("es", "en"):
                _tr(s, "claim", claim.id, "texto", lang, c["texto"][lang], [c["codigo"]])
                if medida:
                    _tr(s, "claim", claim.id, "medida", lang, medida[lang])
            for ocode in c["supports"]:
                s.add(m.ClaimSupport(claim_id=claim.id, article_id=arts[ocode].id, fragmento_fuente=c["fragmento"],
                                     postura="afirma", confianza=1.0))
        s.flush()
        run_event(s, ed, event)

        b = ev["brief"]
        brief = m.NeutralBrief(event_id=event.id, edition_id=ed.id, version=1, titulo=b["titulo"]["pt"],
                               modelo="redação de demonstração (sem modelo; texto fixo)", prompt_version="demo-1",
                               estado="borrador")
        s.add(brief)
        s.flush()
        for lang in ("es", "en"):
            _tr(s, "neutral_brief", brief.id, "titulo", lang, b["titulo"][lang])
        orden = 0
        for pi, para in enumerate(b["paragraphs"]):
            for text, cids in para:
                sent = m.BriefSentence(brief_id=brief.id, orden=orden, parrafo=pi, texto=text["pt"], claim_ids=cids)
                s.add(sent)
                s.flush()
                for lang in ("es", "en"):
                    _tr(s, "brief_sentence", sent.id, "texto", lang, text[lang], cids)
                orden += 1
        s.flush()
        result = verify_brief_all_languages(s, brief)
        brief.verificacion = result
        brief.estado = "verificada" if all(r["ok"] for r in result.values()) else "rechazada"

        if ev.get("commentary"):
            _seed_commentary(s, ed, event)
        if ev.get("series"):
            sr = ev["series"]
            s.add(m.Dataset(nombre=sr["nombre"], event_id=event.id, fuente_primaria=sr["fuente"],
                            metodo="Contagem de decretos publicados por ano (dados fictícios).",
                            fecha_corte=ed.corte_ingesta.date(), unidad="decretos", cobertura_territorial="Estado de Itaquara",
                            licencia="demonstração", verificada_en=ed.corte_ingesta, datos=sr["datos"]))
            s.flush()
    s.flush()
    build_standard_visuals(s, ed)
    ed.estado = "en_revision"
    if approve_as:
        from ..editorial import approve_edition
        for ee in ed.events:
            brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ee.event_id)).first()
            from ..editorial import approve_brief
            approve_brief(s, brief, approve_as, "Aprovação explícita na carga da demonstração")
            if ee.event.tema_excepcional:
                ee.event.razon_inclusion_confirmada_por = approve_as
        approve_edition(s, ed, approve_as)
    return ed


def _seed_commentary(s: Session, ed: m.Edition, event: m.Event) -> None:
    sch = m.Scholar(country_id="BR", pais="BR", idiomas=["pt"], activo_desde=date(2026, 9, 1), es_ficticio=True, **D.SCHOLAR)
    rev = m.Scholar(country_id="BR", pais="BR", idiomas=["pt"], activo_desde=date(2026, 9, 1), es_ficticio=True, **D.REVIEWER)
    s.add_all([sch, rev])
    s.flush()
    s.add(m.ScholarDisclosure(scholar_id=sch.id, tipo="ninguna", entidad="Nenhum vínculo declarado (dado fictício)",
                              periodo="2021–2026", fuente="Formulário de declaração (fictício)"))
    refs = {}
    for r in D.REFERENCES:
        ref = m.Reference(tipo=r["tipo"], rol=r["rol"], cita=r["cita"], autores=r["autores"], anio=r["anio"],
                          revision_por_pares=r["tipo"] == "articulo", verificada_en=ed.corte_ingesta,
                          verificada_por="Referência fictícia de demonstração: não verificável", es_ficticia=True)
        s.add(ref)
        s.flush()
        refs[r["key"]] = ref.id
    com = m.Commentary(event_id=event.id, edition_id=ed.id, scholar_id=sch.id, version=1, tipo="fondo",
                       tradicion_declarada=D.TRADITION["pt"], estado="aprobado_pares", idioma="pt",
                       cargado_por="Carga de demonstração")
    s.add(com)
    s.flush()
    for lang in ("es", "en"):
        _tr(s, "commentary", com.id, "tradicion", lang, D.TRADITION[lang])
    for i, st in enumerate(D.STATEMENTS):
        row = m.CommentaryStatement(commentary_id=com.id, orden=i, texto=st["texto"]["pt"], plano=st["plano"],
                                    estatus_epistemico=st["estatus"], escala_temporal=st["escala"],
                                    disciplina=st["disciplina"], claim_ids=st["claims"],
                                    reference_ids=[refs[k] for k in st["refs"]], autoria="modelo")
        s.add(row)
        s.flush()
        for lang in ("es", "en"):
            _tr(s, "commentary_statement", row.id, "texto", lang, st["texto"][lang], st["claims"])
    for q in D.OPEN_QUESTIONS:
        oq = m.OpenQuestion(commentary_id=com.id, pregunta=q["texto"]["pt"], razon=q["razon"], anadida_por="comentador")
        s.add(oq)
        s.flush()
        _tr(s, "open_question", oq.id, "por", "pt", q["por"]["pt"], metodo="humano", revisor="Carga de demonstração")
        for lang in ("es", "en"):
            _tr(s, "open_question", oq.id, "pregunta", lang, q["texto"][lang])
            _tr(s, "open_question", oq.id, "por", lang, q["por"][lang])
    for disc, fam, q in D.DISCIPLINES:
        dm = m.DisciplineMap(event_id=event.id, disciplina=disc, familia=fam, pregunta=q["pt"], propuesto_por="editor")
        s.add(dm)
        s.flush()
        for lang in ("es", "en"):
            _tr(s, "discipline_map", dm.id, "pregunta", lang, q[lang])
    gap = m.DisciplinaryGap(event_id=event.id, disciplina=D.GAP[0], motivo=D.GAP[1]["pt"])
    s.add(gap)
    s.flush()
    for lang in ("es", "en"):
        _tr(s, "disciplinary_gap", gap.id, "motivo", lang, D.GAP[1][lang])
    s.add(m.PeerReview(commentary_id=com.id, revisor_id=rev.id, decision="aprobado",
                       objeciones="Revisão fictícia de demonstração."))


def reset_demo(s: Session) -> None:
    """Remove the demo edition and every fictional row."""
    from sqlalchemy import text
    ed = s.scalars(select(m.Edition).where(m.Edition.es_demo.is_(True))).first()
    ev_ids = [e.id for e in s.scalars(select(m.Event).where(m.Event.es_ficticio.is_(True)))]
    if ev_ids:
        ids = ",".join(map(str, ev_ids))
        com_ids = [c for c in s.scalars(select(m.Commentary.id).where(m.Commentary.event_id.in_(ev_ids)))]
        vis_ids = [v for v in s.scalars(select(m.Visual.id).where(m.Visual.event_id.in_(ev_ids)))]
        brief_ids = [b for b in s.scalars(select(m.NeutralBrief.id).where(m.NeutralBrief.event_id.in_(ev_ids)))]
        claim_ids = [c for c in s.scalars(select(m.Claim.id).where(m.Claim.event_id.in_(ev_ids)))]
        if vis_ids:
            v = ",".join(map(str, vis_ids))
            for t in ("visual_mark", "visual_justification", "visual_encoding", "visual_review"):
                s.execute(text(f"DELETE FROM {t} WHERE visual_id IN ({v})"))
            s.execute(text(f"DELETE FROM control_usage WHERE control_id IN (SELECT id FROM visual_control WHERE visual_id IN ({v}))"))
            s.execute(text(f"DELETE FROM visual_control WHERE visual_id IN ({v})"))
            s.execute(text(f"DELETE FROM translation WHERE source_tipo='visual' AND source_id IN ({v})"))
            s.execute(text(f"DELETE FROM visual WHERE id IN ({v})"))
        if com_ids:
            c = ",".join(map(str, com_ids))
            st_ids = [r[0] for r in s.execute(text(f"SELECT id FROM commentary_statement WHERE commentary_id IN ({c})"))]
            oq_ids = [r[0] for r in s.execute(text(f"SELECT id FROM open_question WHERE commentary_id IN ({c})"))]
            for tipo, idl in (("commentary_statement", st_ids), ("open_question", oq_ids), ("commentary", com_ids)):
                if idl:
                    s.execute(text(f"DELETE FROM translation WHERE source_tipo='{tipo}' AND source_id IN ({','.join(map(str, idl))})"))
            for t in ("commentary_statement", "open_question", "peer_review"):
                s.execute(text(f"DELETE FROM {t} WHERE commentary_id IN ({c})"))
            s.execute(text(f"DELETE FROM commentary WHERE id IN ({c})"))
        if brief_ids:
            b = ",".join(map(str, brief_ids))
            s.execute(text(f"DELETE FROM translation WHERE source_tipo='brief_sentence' AND source_id IN (SELECT id FROM brief_sentence WHERE brief_id IN ({b}))"))
            s.execute(text(f"DELETE FROM translation WHERE source_tipo='neutral_brief' AND source_id IN ({b})"))
            s.execute(text(f"DELETE FROM human_review WHERE target_tipo='brief' AND target_id IN ({b})"))
            s.execute(text(f"DELETE FROM brief_sentence WHERE brief_id IN ({b})"))
            s.execute(text(f"DELETE FROM neutral_brief WHERE id IN ({b})"))
        if claim_ids:
            cl = ",".join(map(str, claim_ids))
            s.execute(text(f"DELETE FROM translation WHERE source_tipo='claim' AND source_id IN ({cl})"))
            s.execute(text(f"DELETE FROM claim_support WHERE claim_id IN ({cl})"))
            s.execute(text(f"DELETE FROM claim WHERE id IN ({cl})"))
        dm = [r[0] for r in s.execute(text(f"SELECT id FROM discipline_map WHERE event_id IN ({ids})"))]
        dg = [r[0] for r in s.execute(text(f"SELECT id FROM disciplinary_gap WHERE event_id IN ({ids})"))]
        for tipo, idl in (("discipline_map", dm), ("disciplinary_gap", dg)):
            if idl:
                s.execute(text(f"DELETE FROM translation WHERE source_tipo='{tipo}' AND source_id IN ({','.join(map(str, idl))})"))
        for t in ("coverage_snapshot", "coverage_daily", "blindspot_flag", "framing_summary", "discipline_map",
                  "disciplinary_gap", "visual_gap", "edition_event", "article_event"):
            s.execute(text(f"DELETE FROM {t} WHERE event_id IN ({ids})"))
        s.execute(text(f"DELETE FROM dataset WHERE event_id IN ({ids})"))
        s.execute(text(f"DELETE FROM translation WHERE source_tipo='event' AND source_id IN ({ids})"))
        s.execute(text(f"DELETE FROM event WHERE id IN ({ids})"))
    s.execute(text("DELETE FROM article WHERE es_ficticio"))
    s.execute(text("DELETE FROM scholar_disclosure WHERE scholar_id IN (SELECT id FROM scholar WHERE es_ficticio)"))
    s.execute(text("DELETE FROM scholar WHERE es_ficticio"))
    s.execute(text("DELETE FROM reference WHERE es_ficticia"))
    s.execute(text("DELETE FROM outlet_position WHERE outlet_id IN (SELECT id FROM outlet WHERE es_ficticio)"))
    s.execute(text("DELETE FROM outlet WHERE es_ficticio"))
    if ed:
        s.execute(text(f"DELETE FROM chat_message WHERE session_id IN (SELECT id FROM chat_session WHERE edition_id={ed.id})"))
        s.execute(text(f"DELETE FROM chat_session WHERE edition_id={ed.id}"))
        s.execute(text(f"DELETE FROM chat_suggestion WHERE edition_id={ed.id}"))
        s.execute(text(f"DELETE FROM human_review WHERE target_tipo='edition' AND target_id={ed.id}"))
        s.execute(text(f"DELETE FROM edition WHERE id={ed.id}"))
