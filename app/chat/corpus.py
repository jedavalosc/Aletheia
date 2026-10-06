"""The chat's whole world: the PUBLISHED corpus of one edition.

Documents: claims (with their support and selection mode), chronicle
sentences, coverage per event and axis, blind-spot flags, academic statements
(with plane, status and author), open questions, visual findings, edition
metadata and the methodology. Each document has a stable id that the model
must cite and that the verifier checks.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..analytics.visuals import texts_for
from ..config import LANGS
from ..i18n import Tr, fmt_date, fmt_datetime_brt, fmt_pct, t
from ..methodology_text import METHOD


@dataclass
class Doc:
    id: str
    tipo: str  # claim / frase / cobertura / ponto_cego / academico / pergunta_aberta / visual / edicao / metodo
    event: str | None
    text: dict[str, str]  # per language
    claim_ids: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    search: dict[str, str] | None = None  # text indexed for retrieval (without the event title noise)


@dataclass
class Corpus:
    edition_id: int
    numero: int
    es_demo: bool
    corte: dict[str, str]
    docs: dict[str, Doc]
    claims: dict[str, dict]  # codigo -> {modo, medida, valor, event_id, texts}
    events: dict[str, dict]  # slug -> {titulo per lang, omitted: claims some pole barely covers}
    index: "BM25 | None" = None


_STOP = set("""a o as os de da do das dos e em no na nos nas um uma uns umas que se por para com como ao aos à às é foi ser sobre
el la los las del y en un una unos unas que se por para con como al es fue ser sobre lo le
the of and in on a an to for with as is was be by about that this it what who which how
qual quais quem onde quando porque por que cual cuales quien donde cuando why where when""".split())


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(s: str) -> list[str]:
    out = []
    for w in re.findall(r"\w+", fold(s)):
        if w in _STOP or len(w) < 2:
            continue
        out.append(w[:6] if not w.isdigit() else w)  # crude stemming across pt/es/en
    return out


class BM25:
    def __init__(self, docs: list[Doc], k1: float = 1.4, b: float = 0.7):
        self.docs = docs
        self.tf = [Counter(tokens(" ".join((d.search or d.text).values()))) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, k: int = 12, event: str | None = None, allow: set[str] | None = None) -> list[tuple[float, Doc]]:
        q = tokens(query)
        res = []
        for i, d in enumerate(self.docs):
            if allow is not None and d.tipo not in allow:
                continue
            tf, dl, score = self.tf[i], self.len[i], 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    score += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            if score > 0:
                if event and d.event == event:
                    score *= 1.25
                res.append((score, d))
        res.sort(key=lambda x: -x[0])
        return res[:k]


def build_corpus(s: Session, ed: m.Edition) -> Corpus:
    tr = Tr(s)
    docs: dict[str, Doc] = {}
    claims: dict[str, dict] = {}
    events: dict[str, dict] = {}
    corte = {lang: fmt_datetime_brt(ed.corte_ingesta, lang) for lang in LANGS}

    def add(d: Doc):
        docs[d.id] = d

    principal = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ed.country_id,
                                                   m.Cleavage.tipo == "principal", m.Cleavage.activo.is_(True))).first()
    titles_line = []
    for ee in ed.events:
        ev = ee.event
        brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id, m.NeutralBrief.edition_id == ed.id,
                                                      m.NeutralBrief.estado == "aprobada")).first()
        if brief is None:
            continue
        title = {lang: tr.get("neutral_brief", brief.id, "titulo", lang, brief.titulo) for lang in LANGS}
        omitted: list[str] = []
        ev_claims = {c.codigo: c for c in s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id))}
        for fs in s.scalars(select(m.FramingSummary).where(m.FramingSummary.event_id == ev.id)
                            .join(m.Pole, m.Pole.id == m.FramingSummary.pole_id).where(m.Pole.cleavage_id == principal.id)):
            for key in fs.no_menciona:
                codes = ([k for k, c in ev_claims.items() if c.medida == key[7:]] if key.startswith("medida:") else [key])
                omitted += [k for k in codes if k not in omitted]
        events[ev.slug] = {"titulo": title, "id": ev.id, "omitted": omitted}
        titles_line.append(title)
        for c in s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id)):
            texts = {lang: tr.get("claim", c.id, "texto", lang, c.texto_normalizado) for lang in LANGS}
            claims[c.codigo] = {"modo": c.modo, "medida": c.medida, "valor": c.valor, "event_id": ev.id, "event": ev.slug,
                                "texts": texts, "atribucion": c.atribucion}
            outlets = sorted({sp.article.outlet_id for sp in c.supports})
            text = {}
            for lang in LANGS:
                mode = t(f"mode_{c.modo}", lang)
                src = f" {t('primary_source', lang)}: {c.fuente_primaria['nombre']}." if c.fuente_primaria else ""
                text[lang] = f"[{c.codigo}] {texts[lang]} ({mode}; {t('supported_by', lang)} {len(outlets)}.{src}) — {title[lang]}"
            add(Doc(f"claim:{c.codigo}", "claim", ev.slug, text, [c.codigo], {"modo": c.modo}, search=dict(texts)))
        for st in brief.sentences:
            plain = {lang: tr.get('brief_sentence', st.id, 'texto', lang, st.texto) for lang in LANGS}
            text = {lang: f"{plain[lang]} — {title[lang]}" for lang in LANGS}
            add(Doc(f"frase:{ev.slug}:{st.orden}", "frase", ev.slug, text, list(st.claim_ids), search=plain))
        # Coverage per axis (event subject) and blind-spot flags
        for ax in s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ev.country_id, m.Cleavage.activo.is_(True))):
            parts = {lang: [] for lang in LANGS}
            for sn in s.scalars(select(m.CoverageSnapshot).join(m.Pole, m.Pole.id == m.CoverageSnapshot.pole_id).where(
                    m.CoverageSnapshot.event_id == ev.id, m.CoverageSnapshot.edition_id == ed.id,
                    m.CoverageSnapshot.subject == "evento", m.Pole.cleavage_id == ax.id).order_by(m.Pole.orden)):
                pole = s.get(m.Pole, sn.pole_id)
                for lang in LANGS:
                    pl = tr.get("pole", pole.id, "etiqueta", lang, pole.etiqueta)
                    parts[lang].append(f"{pl}: {t('of_outlets', lang, a=sn.medios_que_cubren, b=sn.medios_activos_del_polo)} "
                                       f"({fmt_pct(sn.pct, lang)}; {t('audience_weighted', lang)} {fmt_pct(sn.pct_ponderado_audiencia, lang)})")
            text = {lang: f"{t('coverage', lang)} — {title[lang]} — {t('axis', lang)} "
                          f"{tr.get('cleavage', ax.id, 'nombre', lang, ax.nombre)}: " + "; ".join(parts[lang]) for lang in LANGS}
            add(Doc(f"cobertura:{ev.slug}:{ax.slug}", "cobertura", ev.slug, text))
        for fl in s.scalars(select(m.BlindspotFlag).where(m.BlindspotFlag.event_id == ev.id, m.BlindspotFlag.edition_id == ed.id)):
            pole = s.get(m.Pole, fl.pole_id)
            code = fl.subject.split(":", 1)[1] if fl.subject.startswith("claim:") else None
            snaps = {sn.pole_id: sn for sn in s.scalars(select(m.CoverageSnapshot).where(
                m.CoverageSnapshot.event_id == ev.id, m.CoverageSnapshot.edition_id == ed.id,
                m.CoverageSnapshot.subject == fl.subject))}
            text = {}
            for lang in LANGS:
                pl = tr.get("pole", pole.id, "etiqueta", lang, pole.etiqueta)
                detail = "; ".join(
                    f"{tr.get('pole', p.id, 'etiqueta', lang, p.etiqueta)}: {t('of_outlets', lang, a=snaps[p.id].medios_que_cubren, b=snaps[p.id].medios_activos_del_polo)}"
                    for p in principal.poles if p.id in snaps)
                subj = claims[code]["texts"][lang] if code else title[lang]
                text[lang] = f"{t('blindspot', lang, p=pl)} — {t('blindspot_subject', lang)}: {subj} ({detail}). {t('blindspot_note', lang)}"
            add(Doc(f"ponto_cego:{fl.id}", "ponto_cego", ev.slug, text, [code] if code else []))
        # Academic layer
        com = s.scalars(select(m.Commentary).where(m.Commentary.event_id == ev.id, m.Commentary.edition_id == ed.id,
                                                   m.Commentary.estado == "aprobado_pares")).first()
        if com is not None:
            sch = s.get(m.Scholar, com.scholar_id)
            for st in com.statements:
                text = {lang: (f"{tr.get('commentary_statement', st.id, 'texto', lang, st.texto)} "
                               f"({t('academic_label', lang)}) "
                               f"[{t('plane_' + st.plano, lang)} · {t('status_' + st.estatus_epistemico, lang)} · "
                               f"{t('scale_' + st.escala_temporal, lang)} · {st.disciplina} · {sch.nombre}] — {title[lang]}")
                        for lang in LANGS}
                add(Doc(f"academico:{st.id}", "academico", ev.slug, text, list(st.claim_ids),
                        {"scholar": sch.nombre, "plano": st.plano, "estatus": st.estatus_epistemico,
                         "disciplina": st.disciplina}, search={lang: text[lang].split(" — ")[0] for lang in LANGS}))
            for q in com.open_questions:
                text = {lang: f"{t('what_we_dont_know', lang)}: {tr.get('open_question', q.id, 'pregunta', lang, q.pregunta)} "
                              f"({t('reason_' + q.razon, lang)}. {tr.get('open_question', q.id, 'por', lang, '')}) — {title[lang]}"
                        for lang in LANGS}
                add(Doc(f"pergunta_aberta:{q.id}", "pergunta_aberta", ev.slug, text, [], {"scholar": sch.nombre},
                        search={lang: f"{text[lang].split(' — ')[0]} {t('academic_label', lang)}" for lang in LANGS}))
        for v in s.scalars(select(m.Visual).where(m.Visual.event_id == ev.id, m.Visual.edition_id == ed.id,
                                                  m.Visual.estado.in_(["verificada", "aprobada"]))):
            text = {lang: texts_for(s, tr, v, lang)["alt"] + f" — {title[lang]}" for lang in LANGS}
            add(Doc(f"visual:{v.id}", "visual", ev.slug, text))

    # Edition metadata and methodology
    country = s.get(m.Country, ed.country_id)
    ed_text = {}
    for i, lang in enumerate(LANGS):
        lst = "; ".join(tl[lang] for tl in titles_line)
        demo = f" {t('demo_banner', lang)}." if ed.es_demo else ""
        ed_text[lang] = (f"{t('edition_n', lang, n=ed.numero)}. {t('cutoff', lang)}: {corte[lang]}. "
                         f"{t('cutoff_note', lang, d=fmt_date(ed.corte_ingesta, lang))} {t('events_by_impact', lang)}: {lst}.{demo}")
    add(Doc("edicao", "edicao", None, ed_text))
    for key in ("sel", "ver", "pol", "cov", "tr", "chat"):
        add(Doc(f"metodo:{key}", "metodo", None, {lang: f"{METHOD[lang][key + '_h']}: {METHOD[lang][key]}" for lang in LANGS}))
    for gi, gap in enumerate(country.data_gaps):
        add(Doc(f"metodo:vazio{gi}", "metodo", None, {lang: f"{t('data_gap', lang)}: {gap[lang]}" for lang in LANGS}))

    corpus = Corpus(ed.id, ed.numero, ed.es_demo, corte, docs, claims, events)
    corpus.index = BM25(list(docs.values()))
    return corpus
