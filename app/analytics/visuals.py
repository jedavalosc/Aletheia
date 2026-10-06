"""Standard visual pieces (design doc s.2): produced for every event in the
same format, recorded as decisions (justification, encodings, marks,
controls), rendered from those decisions, then verified."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import LANGS
from ..editorial import load_terms
from ..i18n import Tr, fmt_date, fmt_num, fmt_pct, t
from ..rules.visual import verify_visual
from ..site import svg

BG = svg.BG
EDITOR = "sistema (plantilla estándar)"


def _palette(s: Session, cleavage_id: int) -> dict[str, str]:
    p = s.scalars(select(m.Palette).where(m.Palette.cleavage_id == cleavage_id)).first()
    return p.asignacion_polo_color if p else {}


def _snapshots(s: Session, ed: m.Edition, ev: m.Event, subject: str) -> dict[int, m.CoverageSnapshot]:
    return {c.pole_id: c for c in s.scalars(select(m.CoverageSnapshot).where(
        m.CoverageSnapshot.edition_id == ed.id, m.CoverageSnapshot.event_id == ev.id,
        m.CoverageSnapshot.subject == subject))}


def _n_outlets(s: Session, ed: m.Edition) -> int:
    from .core import active_outlets
    return len(active_outlets(s, ed))


def footer(s: Session, ed: m.Edition, lang: str, source_line: str, extra: list[str] | None = None) -> list[str]:
    country = s.get(m.Country, ed.country_id)
    lines = [f"{t('source', lang)}: {source_line}",
             f"{t('cutoff', lang)}: {fmt_date(ed.corte_ingesta, lang)} · {t('edition_n', lang, n=ed.numero)} · Aletheia News Brasil"]
    lines += extra or []
    for gap in country.data_gaps:
        lines.append(f"{t('data_gap', lang)}: {gap[lang]}")
    if ed.es_demo:
        lines.append(t("demo_banner", lang))
    return lines


def texts_for(s: Session, tr: Tr, v: m.Visual, lang: str) -> dict:
    """Title, finding (alt), short note and footer for one language. Generated
    from the recorded data, never written freehand."""
    ed = s.get(m.Edition, v.edition_id)
    ev = s.get(m.Event, v.event_id)
    sp = v.spec
    n_out = _n_outlets(s, ed)
    if v.tipo in ("cobertura", "puntociego"):
        axis_id = sp["axis_id"]
        poles = sp["poles"]
        labels = [tr.get("pole", p["pole_id"], "etiqueta", lang, p["label_pt"]) for p in poles]
        measure = sp.get("measure", "medios")
        if v.tipo == "cobertura":
            subj = tr.get("event", ev.id, "titulo", lang, ev.titulo_provisional)
            title = f"{t('coverage', lang)}: {subj}"
        else:
            c = s.scalars(select(m.Claim).where(m.Claim.codigo == sp["claim"])).one()
            subj = tr.get("claim", c.id, "texto", lang, c.texto_normalizado)
            title = f"{t('blindspot_subject', lang)}: {subj}"
        if measure == "audiencia":
            parts = [f"{lb}: {fmt_pct(p['pct_aud'], lang)} ({t('audience_weighted', lang)})" for lb, p in zip(labels, poles)]
        else:
            parts = [f"{lb}: {fmt_pct(p['pct'], lang)} ({t('of_outlets', lang, a=p['num'], b=p['den'])})" for lb, p in zip(labels, poles)]
        alt = f"{t('coverage', lang)}. " + "; ".join(parts) + "."
        note = None
        if v.tipo == "puntociego":
            low = next(lb for lb, p in zip(labels, poles) if p["pole_id"] == sp["low_pole_id"])
            note = f"{t('blindspot', lang, p=low)}. {t('blindspot_note', lang)}"
            alt = note + " " + alt
        den = {"pt": "veículos do polo com ao menos um texto publicado na semana",
               "es": "medios del polo con al menos un texto publicado en la semana",
               "en": "outlets of the pole that published at least one text that week"}[lang]
        return {"title": title, "alt": alt, "note": note,
                "footer": footer(s, ed, lang, {"pt": f"coleta Aletheia de {n_out} veículos", "es": f"recolección Aletheia de {n_out} medios",
                                               "en": f"Aletheia collection from {n_out} outlets"}[lang],
                                 [f"{t('denominator', lang)}: {den}"])}
    if v.tipo == "cifras":
        claims = [s.scalars(select(m.Claim).where(m.Claim.codigo == p["claim"])).one() for p in sp["points"]]
        medida = tr.get("claim", claims[0].id, "medida", lang, claims[0].medida)
        title = f"{t('figures_by_source', lang)}: {medida}"
        parts = [f"{p['fuente']}: {fmt_num(p['valor'], lang)}" for p in sp["points"]]
        alt = f"{medida[:1].upper() + medida[1:]}: " + "; ".join(parts) + f". {t('figures_note', lang)}"
        return {"title": title, "alt": alt, "note": t("figures_note", lang),
                "footer": footer(s, ed, lang, ", ".join(p["fuente"] for p in sp["points"]),
                                 [f"{t('denominator', lang)}: {sp['unidad']}"])}
    if v.tipo == "serie":
        ds = s.get(m.Dataset, sp["dataset_id"])
        prev = [d for d in ds.datos if d["ano"] != sp["current"]]
        years = sum(1 for d in prev if d["decretos"] > 0)
        rng = f"{prev[0]['ano']}–{prev[-1]['ano']}"
        title = {"pt": f"{t('series', lang)}: decretos de emergência por estiagem, {rng} e {sp['current']}",
                 "es": f"{t('series', lang)}: decretos de emergencia por sequía, {rng} y {sp['current']}",
                 "en": f"{t('series', lang)}: drought emergency decrees, {rng} and {sp['current']}"}[lang]
        alt = {"pt": f"Houve decreto de emergência por estiagem em {years} dos {len(prev)} anos entre {rng}; o de {sp['current']} é o atual.",
               "es": f"Hubo decreto de emergencia por sequía en {years} de los {len(prev)} años entre {rng}; el de {sp['current']} es el actual.",
               "en": f"A drought emergency was declared in {years} of the {len(prev)} years from {rng}; the {sp['current']} one is the current decree."}[lang]
        return {"title": title, "alt": alt, "note": None,
                "footer": footer(s, ed, lang, ds.fuente_primaria, [f"{t('denominator', lang)}: {ds.unidad}/ano" if lang == "pt" else f"{t('denominator', lang)}: {ds.unidad}"])}
    raise ValueError(v.tipo)


def render(s: Session, tr: Tr, v: m.Visual, lang: str, variant: dict | None = None) -> str:
    """variant overrides spec keys (e.g. {'axis_id':.., 'poles':.., 'measure':..}) for level-2 controls."""
    spec = dict(v.spec)
    if variant:
        spec.update(variant)
    proxy = _Proxy(v, spec)
    tx = texts_for(s, tr, proxy, lang)
    uid = f"v{v.id}-{lang}-{spec.get('axis_id', '')}-{spec.get('measure', '')}"
    if v.tipo in ("cobertura", "puntociego"):
        pal = _palette(s, spec["axis_id"])
        rows = []
        for p in spec["poles"]:
            label = tr.get("pole", p["pole_id"], "etiqueta", lang, p["label_pt"])
            if spec.get("measure") == "audiencia":
                val, right = p["pct_aud"] or 0, f"{fmt_pct(p['pct_aud'], lang)} · {t('audience_weighted', lang)}"
            else:
                val, right = p["pct"], f"{fmt_pct(p['pct'], lang)} · {t('of_outlets', lang, a=p['num'], b=p['den'])}"
            rows.append({"label": label, "value": val, "right_text": right, "color": pal.get(p["pole_slug"], "#666")})
        return svg.bars(tx, rows, uid)
    if v.tipo == "cifras":
        pts = [{"label": p["fuente"], "value": p["valor"], "value_text": fmt_num(p["valor"], lang)}
               for p in sorted(spec["points"], key=lambda p: p["valor"])]
        return svg.points(tx, pts, max(p["valor"] for p in spec["points"]), uid)
    if v.tipo == "serie":
        ds = s.get(m.Dataset, spec["dataset_id"])
        return svg.series(tx, ds.datos, spec["current"], uid, t("current", lang))
    raise ValueError(v.tipo)


class _Proxy:
    def __init__(self, v: m.Visual, spec: dict):
        self.id, self.tipo, self.edition_id, self.event_id, self.spec = v.id, v.tipo, v.edition_id, v.event_id, spec


def _poles_payload(s: Session, ed: m.Edition, ev: m.Event, cleavage: m.Cleavage, subject: str) -> list[dict]:
    snaps = _snapshots(s, ed, ev, subject)
    out = []
    for p in sorted(cleavage.poles, key=lambda p: p.orden):
        sn = snaps[p.id]
        out.append({"pole_id": p.id, "pole_slug": p.slug, "label_pt": p.etiqueta, "num": sn.medios_que_cubren,
                    "den": sn.medios_activos_del_polo, "pct": sn.pct, "pct_aud": sn.pct_ponderado_audiencia,
                    "snapshot_id": sn.id})
    return out


def variants(s: Session, v: m.Visual) -> list[dict]:
    """All states of a level-2 piece (axis x measure). Each is a full static SVG."""
    if v.tipo != "cobertura":
        return [{}]
    ed, ev = s.get(m.Edition, v.edition_id), s.get(m.Event, v.event_id)
    out = []
    for axis in v.spec["axes"]:
        cl = s.get(m.Cleavage, axis)
        poles = _poles_payload(s, ed, ev, cl, "evento")
        for measure in ("medios", "audiencia"):
            out.append({"axis_id": axis, "poles": poles, "measure": measure})
    return out


def build_standard_visuals(s: Session, ed: m.Edition) -> None:
    tr = Tr(s)
    for ee in ed.events:
        ev = ee.event
        s.query(m.VisualMark).filter(m.VisualMark.visual_id.in_(
            select(m.Visual.id).where(m.Visual.event_id == ev.id, m.Visual.edition_id == ed.id))).delete(synchronize_session=False)
        axes = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ev.country_id, m.Cleavage.activo.is_(True))
                         .order_by(m.Cleavage.orden)).all()
        principal = next(a for a in axes if a.tipo == "principal")
        created: list[m.Visual] = []

        # 1. Coverage by pole with denominator — level 2 (axis switch + audience weighting)
        v = m.Visual(event_id=ev.id, edition_id=ed.id, tipo="cobertura", forma="barras", nivel=2, version=1,
                     brief_version=1, fecha_corte=ed.corte_ingesta, estado="borrador",
                     spec={"tipo": "cobertura", "forma": "barras", "origen": 0, "axis_id": principal.id,
                           "measure": "medios", "axes": [a.id for a in axes],
                           "poles": _poles_payload(s, ed, ev, principal, "evento")})
        s.add(v)
        s.flush()
        _record(s, v, "¿Cuánto cubrió cada polo?", "comparación entre polos con denominador",
                "pieza estándar: todo evento con crónica", "Una oración con dos porcentajes oculta el denominador.",
                [("longitud", "pct de medios del polo", "lineal 0–100%")], [
                    ("eje", "¿Y si lo miro desde lo territorial o lo institucional?", principal.slug),
                    ("audiencia", "¿Cuánta gente lo vio, no cuántos medios?", "medios")])
        created.append(v)

        # 2. Blind-spot gap, both poles — level 1
        for fl in s.scalars(select(m.BlindspotFlag).where(m.BlindspotFlag.event_id == ev.id,
                                                          m.BlindspotFlag.edition_id == ed.id)):
            codigo = fl.subject.split(":", 1)[1] if fl.subject.startswith("claim:") else None
            if codigo is None:
                continue
            v = m.Visual(event_id=ev.id, edition_id=ed.id, tipo="puntociego", forma="barras_espejo", nivel=1,
                         version=1, brief_version=1, fecha_corte=ed.corte_ingesta, estado="borrador",
                         spec={"tipo": "puntociego", "forma": "barras_espejo", "origen": 0, "axis_id": principal.id,
                               "claim": codigo, "low_pole_id": fl.pole_id, "flag_id": fl.id,
                               "poles": _poles_payload(s, ed, ev, principal, fl.subject)})
            s.add(v)
            s.flush()
            _record(s, v, "¿Cubrieron los dos polos este hecho derivado?", "brecha entre polos",
                    "pieza estándar: bandera de punto ciego", "La crónica no muestra la brecha.",
                    [("longitud", "pct de medios del polo", "lineal 0–100%")], [])
            created.append(v)

        # 3. Disputed figures: points by source only with >= 3 sources for the same measure
        groups = defaultdict(list)
        for c in s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id, m.Claim.medida.is_not(None))):
            groups[c.medida].append(c)
        for medida, cl in groups.items():
            if len({c.valor for c in cl}) < 3:
                continue  # two sources -> table in the page, not a chart
            v = m.Visual(event_id=ev.id, edition_id=ed.id, tipo="cifras", forma="puntos", nivel=1, version=1,
                         brief_version=1, fecha_corte=ed.corte_ingesta, estado="borrador",
                         spec={"tipo": "cifras", "forma": "puntos", "origen": 0, "unidad": cl[0].unidad,
                               "points": [{"claim": c.codigo, "fuente": c.atribucion, "valor": c.valor} for c in cl]})
            s.add(v)
            s.flush()
            _record(s, v, "¿Cuántos hubo, según quién?", "tres o más cifras de fuentes distintas",
                    "pieza estándar: cifras en disputa", "Una oración enumera, pero no deja ver la distancia entre cifras.",
                    [("posición", medida, "lineal desde 0")], [])
            created.append(v)

        # 4. Recurring series (only with a verified dataset)
        ds = s.scalars(select(m.Dataset).where(m.Dataset.event_id == ev.id)).first()
        if ds is not None and ds.verificada_en is not None:
            v = m.Visual(event_id=ev.id, edition_id=ed.id, tipo="serie", forma="barras_serie", nivel=0, version=1,
                         brief_version=1, fecha_corte=ed.corte_ingesta, estado="borrador",
                         spec={"tipo": "serie", "forma": "barras", "origen": 0, "dataset_id": ds.id,
                               "current": ed.corte_ingesta.year})
            s.add(v)
            s.flush()
            _record(s, v, "¿Es un caso aislado o recurrente?", "serie de eventos comparables",
                    "pieza estándar: evento de serie recurrente", "La recurrencia no se ve en la crónica.",
                    [("longitud", "decretos por año", "lineal desde 0")], [])
            created.append(v)

        s.flush()
        # Marks and verification
        for v in created:
            _marks(s, v)
            verify_and_set(s, tr, v)


def _record(s, v, pregunta, forma_info, filtro, alternativa, encodings, controls):
    s.add(m.VisualJustification(visual_id=v.id, pregunta_lector=pregunta, forma_de_la_informacion=forma_info,
                                filtro_superado=filtro, alternativa_textual_descartada=alternativa, aprobado_por=EDITOR))
    for canal, variable, escala in encodings:
        s.add(m.VisualEncoding(visual_id=v.id, canal=canal, variable=variable, escala=escala, origen_eje=0,
                               corte_senalado=False))
    for persp, q, default in controls:
        s.add(m.VisualControl(visual_id=v.id, perspectiva=persp, pregunta_que_responde=q, valor_por_defecto=default))


def _marks(s: Session, v: m.Visual) -> None:
    sp = v.spec
    if v.tipo in ("cobertura", "puntociego"):
        for p in sp["poles"]:
            s.add(m.VisualMark(visual_id=v.id, coverage_snapshot_id=p["snapshot_id"], valor=p["pct"],
                               claim_ids=[sp["claim"]] if v.tipo == "puntociego" else [],
                               fuente="coverage_snapshot", denominador=f"{p['num']}/{p['den']}"))
    elif v.tipo == "cifras":
        for p in sp["points"]:
            s.add(m.VisualMark(visual_id=v.id, claim_ids=[p["claim"]], valor=p["valor"], fuente=p["fuente"],
                               denominador=sp["unidad"]))
    elif v.tipo == "serie":
        ds = s.get(m.Dataset, sp["dataset_id"])
        for d in ds.datos:
            s.add(m.VisualMark(visual_id=v.id, dataset_id=ds.id, valor=d["decretos"], fuente=ds.fuente_primaria,
                               denominador=ds.unidad))
    s.flush()


def verify_and_set(s: Session, tr: Tr, v: m.Visual) -> list[str]:
    marks = [{"claim_ids": mk.claim_ids, "dataset_id": mk.dataset_id, "coverage_snapshot_id": mk.coverage_snapshot_id,
              "denominador": mk.denominador} for mk in s.scalars(select(m.VisualMark).where(m.VisualMark.visual_id == v.id))]
    ev = s.get(m.Event, v.event_id)
    texts = {lang: texts_for(s, tr, v, lang) for lang in LANGS}
    for lang in LANGS:
        texts[lang]["footer"] = " ".join(texts[lang]["footer"])
    palette = _palette(s, v.spec["axis_id"]) if "axis_id" in v.spec else {}
    sizes = {}
    for lang in LANGS:
        sizes[lang] = max(len(render(s, tr, v, lang, var).encode()) for var in variants(s, v))
    terms = {lang: load_terms(s, ev.country_id, lang) for lang in LANGS}
    issues = verify_visual(v.spec, marks, texts, palette, BG, terms, sizes)
    v.estado = "verificada" if not issues else "rechazada"
    s.add(m.VisualReview(visual_id=v.id, revisor="verificador automático", checklist=issues or ["ok"],
                         decision="aprobada" if not issues else "rechazada"))
    return issues
