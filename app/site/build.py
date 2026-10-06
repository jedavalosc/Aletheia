"""Static site generator. Builds /pt, /es, /en from PUBLISHED editions only
(state 'publicada', i.e. approved by a named editor). Regenerated on approval
and at app start (the Fly filesystem is ephemeral)."""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..analytics.visuals import render, texts_for, variants
from ..config import DEFAULT_LANG, LANGS, get_settings
from ..editorial import load_terms
from ..methodology_text import METHOD
from ..i18n import Tr, fmt_date, fmt_datetime_brt, fmt_num, fmt_pct, t
from ..rules.loaded_terms import highlight

HERE = Path(__file__).parent
PAGE_BUDGET = 300 * 1024


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals.update(t=t, fmt_date=fmt_date, fmt_pct=fmt_pct, fmt_num=fmt_num, LANGS=LANGS)
    return env


def published_editions(s: Session, country: str) -> list[m.Edition]:
    return s.scalars(select(m.Edition).where(m.Edition.country_id == country, m.Edition.estado == "publicada")
                     .order_by(m.Edition.numero.desc())).all()


def _tr_note(tr: Tr, tipo: str, sid: int, campo: str, lang: str) -> str | None:
    if lang == "pt":
        return None
    row = tr.row(tipo, sid, campo, lang)
    if row is None or row.metodo == "maquina_sin_revisar":
        return t("machine_tr", lang)
    if row.metodo == "maquina_revisada":
        return t("machine_tr_reviewed", lang, r=row.revisor)
    return t("human_tr", lang)


class Ctx:
    """Per-build lookups."""

    def __init__(self, s: Session, ed: m.Edition):
        self.s, self.ed, self.tr = s, ed, Tr(s)
        self.outlets = {o.id: o for o in s.scalars(select(m.Outlet))}
        self.axes = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ed.country_id)
                              .order_by(m.Cleavage.orden)).all()
        self.active_axes = [a for a in self.axes if a.activo]
        self.principal = next(a for a in self.active_axes if a.tipo == "principal")
        from ..analytics.core import pole_members
        self.pole_of: dict[int, dict[int, m.Pole]] = {}
        for a in self.active_axes:
            self.pole_of[a.id] = {oid: pm.pole for pm in pole_members(s, a, ed.corte_ingesta) for oid in pm.outlet_ids}
        self.terms = {lang: load_terms(s, ed.country_id, lang) for lang in LANGS}
        self.country = s.get(m.Country, ed.country_id)

    def pole_label(self, pole: m.Pole, lang: str) -> str:
        return self.tr.get("pole", pole.id, "etiqueta", lang, pole.etiqueta)

    def axis_label(self, axis: m.Cleavage, lang: str) -> str:
        return self.tr.get("cleavage", axis.id, "nombre", lang, axis.nombre)

    def outlet_tag(self, outlet_id: int, lang: str, axis_id: int | None = None) -> str:
        o = self.outlets[outlet_id]
        axis_id = axis_id or self.principal.id
        if o.es_fuente_oficial:
            tag = t("official_source", lang)
        else:
            p = self.pole_of[axis_id].get(outlet_id)
            tag = self.pole_label(p, lang) if p else t("no_pole", lang)
        fict = f" ({t('fictional', lang)})" if o.es_ficticio else ""
        return f"{o.nombre}{fict} · {tag}"


def _headline_html(text: str, ctx: Ctx) -> Markup:
    parts = highlight(text, ctx.terms["pt"], "pt")
    return Markup("".join(f"<mark>{escape(c)}</mark>" if hot else str(escape(c)) for c, hot in parts))


def event_view(ctx: Ctx, ee: m.EditionEvent, lang: str, index: int) -> dict:
    s, tr, ed = ctx.s, ctx.tr, ctx.ed
    ev = ee.event
    brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id, m.NeutralBrief.edition_id == ed.id,
                                                  m.NeutralBrief.estado == "aprobada")
                      .order_by(m.NeutralBrief.version.desc())).first()
    claims = {c.codigo: c for c in s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id))}

    def claim_view(c: m.Claim) -> dict:
        sups = []
        for sp in c.supports:
            sups.append({"outlet": ctx.outlet_tag(sp.article.outlet_id, lang), "fragment": sp.fragmento_fuente,
                         "stance": t(f"stance_{sp.postura}", lang), "url": sp.article.url, "headline": sp.article.titular})
        return {"codigo": c.codigo, "texto": tr.get("claim", c.id, "texto", lang, c.texto_normalizado),
                "modo": c.modo, "modo_label": t(f"mode_{c.modo}", lang), "modo_why": t(f"mode_{c.modo}_why", lang),
                "primaria": (c.fuente_primaria or {}).get("nombre"), "supports": sups}

    # Chronicle paragraphs and sentences
    paragraphs = defaultdict(list)
    for st in brief.sentences:
        txt = tr.get("brief_sentence", st.id, "texto", lang, st.texto)
        paragraphs[st.parrafo].append({"texto": txt, "claim_ids": st.claim_ids})
    paras = []
    for pi in sorted(paragraphs):
        sents = paragraphs[pi]
        cids = []
        for sn in sents:
            for c in sn["claim_ids"]:
                if c not in cids:
                    cids.append(c)
        paras.append({"id": f"src-{ev.slug}-{pi}", "sentences": sents, "claims": [claim_view(claims[c]) for c in cids]})

    # Triptych columns per active axis. Pole order alternates between events (logged in methodology).
    flip = (ed.numero + index) % 2 == 1
    axes_views = []
    for a in ctx.active_axes:
        cols = []
        for fs in s.scalars(select(m.FramingSummary).where(m.FramingSummary.event_id == ev.id)
                            .join(m.Pole, m.Pole.id == m.FramingSummary.pole_id).where(m.Pole.cleavage_id == a.id)
                            .order_by(m.Pole.orden)):
            pole = s.get(m.Pole, fs.pole_id)
            heads = []
            for aid in fs.article_ids:
                art = s.get(m.Article, aid)
                heads.append({"html": _headline_html(art.titular, ctx), "outlet": ctx.outlet_tag(art.outlet_id, lang, a.id),
                              "url": art.url})
            omitted = []
            for key in fs.no_menciona:
                if key.startswith("medida:"):
                    any_c = next(c for c in claims.values() if c.medida == key[7:])
                    omitted.append(t("not_mention_measure", lang, m=tr.get("claim", any_c.id, "medida", lang, any_c.medida)))
                else:
                    c = claims[key]
                    omitted.append(tr.get("claim", c.id, "texto", lang, c.texto_normalizado))
            cols.append({"pole": ctx.pole_label(pole, lang), "slot": "a" if pole.orden == 0 else "b",
                         "heads": heads, "omitted": omitted})
        if flip:
            cols.reverse()
        axes_views.append({"id": a.slug, "label": ctx.axis_label(a, lang), "cols": cols,
                           "principal": a.id == ctx.principal.id})

    # Visuals
    figures = []
    for v in s.scalars(select(m.Visual).where(m.Visual.event_id == ev.id, m.Visual.edition_id == ed.id,
                                              m.Visual.estado.in_(["verificada", "aprobada"])).order_by(m.Visual.id)):
        tx = texts_for(s, tr, v, lang)
        vs = []
        for var in variants(s, v):
            axis = s.get(m.Cleavage, var.get("axis_id", v.spec.get("axis_id"))) if "axis_id" in (var or v.spec) else None
            vs.append({"svg": Markup(render(s, tr, v, lang, var or None)),
                       "axis": axis.slug if axis else "", "measure": var.get("measure", "medios") if var else "medios",
                       "default": (not var) or (var.get("axis_id") == ctx.principal.id and var.get("measure") == "medios")})
        flag = None
        if v.tipo == "puntociego":
            low = s.get(m.Pole, v.spec["low_pole_id"])
            flag = t("blindspot", lang, p=ctx.pole_label(low, lang))
        figures.append({"tipo": v.tipo, "nivel": v.nivel, "variants": vs, "alt": tx["alt"], "flag": flag,
                        "multi": len(vs) > 1})

    # Disputed figures table (any measure with >= 2 different values)
    disputed = defaultdict(list)
    for c in claims.values():
        if c.medida and c.valor is not None:
            disputed[c.medida].append(c)
    tables = []
    for medida, group in disputed.items():
        if len({c.valor for c in group}) < 2:
            continue
        tables.append({"medida": tr.get("claim", group[0].id, "medida", lang, medida),
                       "rows": [{"fonte": c.atribucion, "valor": fmt_num(c.valor, lang), "unidad": c.unidad, "codigo": c.codigo}
                                for c in group]})

    return {
        "slug": ev.slug, "url": f"/{lang}/eventos/{ev.slug}.html",
        "titulo": tr.get("neutral_brief", brief.id, "titulo", lang, brief.titulo),
        "seccion": ev.seccion, "seccion_label": t(f"section_{ev.seccion}", lang),
        "impacto": ev.impacto, "version": ee.version_evento, "brief_version": brief.version,
        "excepcional": tr.get("event", ev.id, "razon_inclusion", lang, ev.razon_inclusion) if ev.tema_excepcional else None,
        "paras": paras, "axes": axes_views, "figures": figures, "tables": tables,
        "tr_note": _tr_note(tr, "neutral_brief", brief.id, "titulo", lang),
        "flip": flip, "academic": academic_view(ctx, ev, lang),
        "cover_bars": _cover_bars(ctx, ev, lang),
    }


def _cover_bars(ctx: Ctx, ev: m.Event, lang: str) -> list[dict]:
    rows = []
    for sn in ctx.s.scalars(select(m.CoverageSnapshot).where(
            m.CoverageSnapshot.event_id == ev.id, m.CoverageSnapshot.edition_id == ctx.ed.id,
            m.CoverageSnapshot.subject == "evento")
            .join(m.Pole, m.Pole.id == m.CoverageSnapshot.pole_id).where(m.Pole.cleavage_id == ctx.principal.id)
            .order_by(m.Pole.orden)):
        pole = ctx.s.get(m.Pole, sn.pole_id)
        rows.append({"label": ctx.pole_label(pole, lang), "pct": sn.pct, "slot": "a" if pole.orden == 0 else "b",
                     "text": f"{fmt_pct(sn.pct, lang)} · {t('of_outlets', lang, a=sn.medios_que_cubren, b=sn.medios_activos_del_polo)}"})
    return rows


def academic_view(ctx: Ctx, ev: m.Event, lang: str) -> dict | None:
    s, tr = ctx.s, ctx.tr
    com = s.scalars(select(m.Commentary).where(m.Commentary.event_id == ev.id, m.Commentary.edition_id == ctx.ed.id,
                                               m.Commentary.estado == "aprobado_pares")).first()
    if com is None:
        return None
    sch = s.get(m.Scholar, com.scholar_id)
    pr = s.scalars(select(m.PeerReview).where(m.PeerReview.commentary_id == com.id)).first()
    reviewer = s.get(m.Scholar, pr.revisor_id) if pr else None
    refs = {r.id: r for r in s.scalars(select(m.Reference))}
    by_disc = defaultdict(list)
    scales = defaultdict(list)
    for st in com.statements:
        item = {"texto": tr.get("commentary_statement", st.id, "texto", lang, st.texto),
                "plano": t(f"plane_{st.plano}", lang), "estatus": st.estatus_epistemico,
                "estatus_label": t(f"status_{st.estatus_epistemico}", lang),
                "escala": t(f"scale_{st.escala_temporal}", lang), "claims": st.claim_ids,
                "refs": [{"cita": refs[r].cita, "rol": refs[r].rol, "ficticia": refs[r].es_ficticia} for r in st.reference_ids],
                "demo": st.autoria != "humano"}
        by_disc[st.disciplina].append(item)
        if st.escala_temporal in ("acontecimiento", "coyuntura", "larga_duracion"):
            scales[st.escala_temporal].append(st.disciplina)
    disclosures = s.scalars(select(m.ScholarDisclosure).where(m.ScholarDisclosure.scholar_id == sch.id)).all()
    return {
        "scholar": sch.nombre, "affiliation": sch.afiliacion, "discipline": sch.disciplina,
        "tradition": tr.get("commentary", com.id, "tradicion", lang, com.tradicion_declarada),
        "reviewer": f"{reviewer.nombre}, {reviewer.afiliacion}" if reviewer else None,
        "disclosures": [d.entidad for d in disclosures],
        "by_discipline": [{"name": k, "items": v} for k, v in by_disc.items()],
        "scales": [{"label": t(f"scale_{k}", lang), "items": scales.get(k, [])}
                   for k in ("acontecimiento", "coyuntura", "larga_duracion")],
        "discipline_map": [{"name": d.disciplina, "q": tr.get("discipline_map", d.id, "pregunta", lang, d.pregunta)}
                           for d in s.scalars(select(m.DisciplineMap).where(m.DisciplineMap.event_id == ev.id))],
        "gaps": [{"name": g.disciplina, "why": tr.get("disciplinary_gap", g.id, "motivo", lang, g.motivo)}
                 for g in s.scalars(select(m.DisciplinaryGap).where(m.DisciplinaryGap.event_id == ev.id))],
        "dont_know": [{"q": tr.get("open_question", q.id, "pregunta", lang, q.pregunta),
                       "why": tr.get("open_question", q.id, "por", lang, ""),
                       "reason": t(f"reason_{q.razon}", lang)} for q in com.open_questions],
        "demo_statements": any(st.autoria != "humano" for st in com.statements),
        "has_explanatory": any(st.plano in ("explicativo", "normativo") for st in com.statements),
    }


def methodology_view(ctx: Ctx, lang: str) -> dict:
    s = ctx.s
    rows = []
    for o in s.scalars(select(m.Outlet).where(m.Outlet.country_id == ctx.ed.country_id).order_by(m.Outlet.es_ficticio.desc(), m.Outlet.nombre)):
        pos = []
        for a in ctx.active_axes:
            p = s.scalars(select(m.OutletPosition).where(m.OutletPosition.outlet_id == o.id, m.OutletPosition.cleavage_id == a.id)
                          .order_by(m.OutletPosition.vigente_desde.desc())).first()
            pos.append(None if p is None else {"score": f"{p.score:+.2f}", "ic": f"[{p.ic_inferior:+.2f}; {p.ic_superior:+.2f}]",
                                                "pole": ctx.pole_label(ctx.pole_of[a.id][o.id], lang) if o.id in ctx.pole_of[a.id] else t("no_pole", lang),
                                                "method": p.metodo, "provisional": p.provisional})
        rows.append({"name": o.nombre, "fict": o.es_ficticio, "official": o.es_fuente_oficial, "tipo": o.tipo,
                     "region": o.region, "pos": pos})
    axes = []
    for a in ctx.axes:
        axes.append({"label": ctx.axis_label(a, lang), "tipo": a.tipo, "activo": a.activo, "hipotesis": a.es_hipotesis,
                     "desde": fmt_date(a.vigente_desde, lang), "desc": a.descripcion,
                     "poles": [ctx.pole_label(p, lang) for p in a.poles]})
    terms = s.scalars(select(m.LoadedTerm).where(m.LoadedTerm.country_id == ctx.ed.country_id, m.LoadedTerm.idioma == lang)).all()
    excl = s.scalars(select(m.ExclusionList).where(m.ExclusionList.country_id == ctx.ed.country_id)).all()
    return {"outlets": rows, "axes": axes, "active_axes": [ctx.axis_label(a, lang) for a in ctx.active_axes],
            "terms": [{"t": x.termino, "alt": x.alternativa, "only_quote": x.permitido_si == "cita", "nota": x.nota} for x in terms],
            "exclusions": [{"e": x.elemento, "motivo": x.motivo, "confirmado": x.confirmado} for x in excl],
            "gaps": [g[lang] for g in ctx.country.data_gaps], "context": ctx.country.contexto}


def _claims_json(ctx: Ctx, ed: m.Edition, lang: str) -> dict:
    out = {}
    for ee in ed.events:
        ev = ee.event
        brief = ctx.s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id)).first()
        title = ctx.tr.get("neutral_brief", brief.id, "titulo", lang, brief.titulo)
        for c in ctx.s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id)):
            out[c.codigo] = {"texto": ctx.tr.get("claim", c.id, "texto", lang, c.texto_normalizado),
                             "modo": t(f"mode_{c.modo}", lang), "evento": title, "url": f"/{lang}/eventos/{ev.slug}.html"}
    return out


def build_site(s: Session, out: Path | None = None) -> Path:
    settings = get_settings()
    out = Path(out or settings.site_dir)
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    shutil.copytree(HERE / "static", tmp / "static")
    env = _env()
    eds = published_editions(s, settings.country_code)
    base_url = settings.public_base_url.rstrip("/")
    common = {"base_url": base_url, "retention": settings.chat_retention_days}
    for lang in LANGS:
        (tmp / lang / "eventos").mkdir(parents=True, exist_ok=True)
    if not eds:
        for lang in LANGS:
            _write(tmp / lang / "index.html", env.get_template("empty.html").render(lang=lang, path="index.html", **common))
    else:
        ed = eds[0]
        ctx = Ctx(s, ed)
        ed_meta = lambda lang: {
            "numero": ed.numero, "demo": ed.es_demo, "corte": fmt_datetime_brt(ed.corte_ingesta, lang),
            "corte_dia": fmt_date(ed.corte_ingesta.astimezone(_tz()), lang),
            "semana": f"{fmt_date(ed.semana_inicio.astimezone(_tz()), lang)} – {fmt_date(ed.semana_fin.astimezone(_tz()), lang)}",
            "publicada": fmt_date((ed.publicada_en or ed.publicacion_prevista).astimezone(_tz()), lang),
            "aprobada_por": ed.aprobada_por}
        for lang in LANGS:
            evs = [event_view(ctx, ee, lang, i) for i, ee in enumerate(ed.events)]
            ordered = sorted(evs, key=lambda e: -e["impacto"])
            meta = ed_meta(lang)
            _write(tmp / lang / "index.html", env.get_template("cover.html").render(
                lang=lang, path="index.html", ed=meta, events=ordered, archive=[e.numero for e in eds], **common))
            for e in evs:
                _write(tmp / lang / "eventos" / f"{e['slug']}.html", env.get_template("event.html").render(
                    lang=lang, path=f"eventos/{e['slug']}.html", ed=meta, ev=e, **common))
            _write(tmp / lang / "metodologia.html", env.get_template("methodology.html").render(
                lang=lang, path="metodologia.html", ed=meta, mv=methodology_view(ctx, lang), method=METHOD,
                pole_order=[{"slug": e["slug"], "titulo": e["titulo"], "flip": e["flip"]} for e in evs], **common))
            _write(tmp / lang / "contestar.html", env.get_template("dispute.html").render(
                lang=lang, path="contestar.html", ed=meta, **common))
            (tmp / lang / "claims.json").write_text(json.dumps(_claims_json(ctx, ed, lang), ensure_ascii=False), encoding="utf-8")
    _write(tmp / "index.html", env.get_template("root.html").render(lang=DEFAULT_LANG, **common))
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    return out


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/Sao_Paulo")


def _write(path: Path, html: str) -> None:
    html = re.sub(r"\n\s*\n+", "\n", html)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def page_weight(site: Path, page: Path) -> int:
    """First-load weight: HTML + CSS + JS + fonts referenced (all self-hosted)."""
    total = page.stat().st_size
    for f in ("static/aletheia.css", "static/aletheia.js"):
        total += (site / f).stat().st_size
    for f in (site / "static" / "fonts").glob("*.woff2"):
        total += f.stat().st_size
    return total
