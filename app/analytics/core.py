"""Coverage, blind spots, claim selection and per-pole omissions.

Everything here is derived from articles, claim supports and the estimated
outlet positions in force for the edition. Nothing is entered by hand.

Pole membership (binary axes, Phase 1): an outlet belongs to the first pole
of an axis if the upper bound of its interval is below 0, to the second if the
lower bound is above 0, and to no pole if the interval crosses 0. Outlets
without a pole count in no denominator. Official sources never have a pole.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..rules.selection import ClaimView, SupportView, decide

BLINDSPOT_GAP_THRESHOLD = 0.40  # difference in share of pole outlets
BLINDSPOT_MIN_IMPACT = 60
OMISSION_MAX_SHARE = 0.25  # a pole "does not mention" a broad claim if <= 25% of its outlets do


@dataclass
class PoleMembers:
    pole: m.Pole
    outlet_ids: set[int]


def positions_in_force(s: Session, cleavage_id: int, at: datetime) -> dict[int, m.OutletPosition]:
    rows = s.scalars(select(m.OutletPosition).where(
        m.OutletPosition.cleavage_id == cleavage_id,
        m.OutletPosition.vigente_desde <= at.date(),
    ).order_by(m.OutletPosition.vigente_desde)).all()
    out: dict[int, m.OutletPosition] = {}
    for r in rows:
        if r.vigente_hasta is None or r.vigente_hasta >= at.date():
            out[r.outlet_id] = r  # latest in force wins
    return out


def pole_members(s: Session, cleavage: m.Cleavage, at: datetime) -> list[PoleMembers]:
    poles = sorted(cleavage.poles, key=lambda p: p.orden)
    if len(poles) != 2:
        raise NotImplementedError("Phase 1 supports binary axes for coverage; see docs/decisiones.md")
    pos = positions_in_force(s, cleavage.id, at)
    official = {o.id for o in s.scalars(select(m.Outlet).where(m.Outlet.es_fuente_oficial.is_(True)))}
    left, right = set(), set()
    for oid, p in pos.items():
        if oid in official:
            continue
        if p.ic_superior < 0:
            left.add(oid)
        elif p.ic_inferior > 0:
            right.add(oid)
    return [PoleMembers(poles[0], left), PoleMembers(poles[1], right)]


def active_outlets(s: Session, edition: m.Edition) -> set[int]:
    """Outlets that published at least one article in the edition week."""
    return set(s.scalars(select(m.Article.outlet_id).where(
        m.Article.fecha_pub >= edition.semana_inicio, m.Article.fecha_pub <= edition.corte_ingesta)).all())


def _event_articles(s: Session, event_id: int, edition: m.Edition) -> list[m.Article]:
    return s.scalars(select(m.Article).join(m.ArticleEvent, m.ArticleEvent.article_id == m.Article.id).where(
        m.ArticleEvent.event_id == event_id,
        m.Article.fecha_pub >= edition.semana_inicio, m.Article.fecha_pub <= edition.corte_ingesta)).all()


def _audience(s: Session) -> dict[int, int]:
    return {o.id: (o.audiencia_estimada or 0) for o in s.scalars(select(m.Outlet))}


def _share(covering: set[int], members: set[int], aud: dict[int, int]) -> tuple[int, int, float, float | None]:
    num, den = len(covering & members), len(members)
    pct = num / den if den else 0.0
    a_den = sum(aud.get(o, 0) for o in members)
    a_num = sum(aud.get(o, 0) for o in covering & members)
    return num, den, pct, (a_num / a_den if a_den else None)


def apply_selection(s: Session, event_id: int, edition: m.Edition, cleavage: m.Cleavage) -> None:
    """Set claim.modo from supports, using the principal axis."""
    members = pole_members(s, cleavage, edition.corte_ingesta)
    pole_of = {}
    for pm in members:
        for oid in pm.outlet_ids:
            pole_of[oid] = pm.pole.slug
    claims = s.scalars(select(m.Claim).where(m.Claim.event_id == event_id)).all()
    # Disputed figures: same measure, different values -> always attributed by source.
    values_by_measure = defaultdict(set)
    for c in claims:
        if c.medida and c.valor is not None:
            values_by_measure[c.medida].add(c.valor)
    for c in claims:
        view = ClaimView(
            codigo=c.codigo,
            supports=[SupportView(pole_of.get(sp.article.outlet_id), sp.postura) for sp in c.supports],
            fuente_primaria_verificada=bool(c.fuente_primaria and c.fuente_primaria.get("verificada_en")),
        )
        d = decide(view)
        modo = d.modo
        if c.medida and len(values_by_measure[c.medida]) > 1 and modo != "excluido":
            modo = "atribuido"
        c.modo = modo


def compute_coverage(s: Session, edition: m.Edition, event: m.Event, cleavages: list[m.Cleavage],
                     principal: m.Cleavage) -> None:
    """One closing snapshot per edition: the event itself and each claim
    (derived fact), per pole of every active axis. Flags only on the principal axis."""
    s.query(m.CoverageSnapshot).filter_by(edition_id=edition.id, event_id=event.id).delete()
    s.query(m.BlindspotFlag).filter_by(edition_id=edition.id, event_id=event.id).delete()
    active = active_outlets(s, edition)
    aud = _audience(s)
    arts = _event_articles(s, event.id, edition)
    covering_event = {a.outlet_id for a in arts}
    art_ids = {a.id for a in arts}
    claims = s.scalars(select(m.Claim).where(m.Claim.event_id == event.id)).all()
    covering_claim = {c.codigo: {sp.article.outlet_id for sp in c.supports if sp.article_id in art_ids} for c in claims}
    ts = edition.corte_ingesta
    for cl in cleavages:
        for pm in pole_members(s, cl, ts):
            members = pm.outlet_ids & active
            subjects = [("evento", covering_event)] + [(f"claim:{k}", v) for k, v in covering_claim.items()]
            for subject, cov in subjects:
                num, den, pct, pa = _share(cov, members, aud)
                s.add(m.CoverageSnapshot(edition_id=edition.id, event_id=event.id, pole_id=pm.pole.id,
                                         subject=subject, timestamp=ts, medios_que_cubren=num,
                                         medios_activos_del_polo=den, pct=pct, pct_ponderado_audiencia=pa))
        if cl.id != principal.id or event.impacto < BLINDSPOT_MIN_IMPACT:
            continue
        a, b = pole_members(s, cl, ts)
        ma, mb = a.outlet_ids & active, b.outlet_ids & active
        # Flags only for the event itself and for established (plain-fact) claims:
        # an attributed single-pole statement is covered by one pole by definition.
        established = {c.codigo for c in claims if c.modo == "llano"}
        flag_subjects = [("evento", covering_event)] + [
            (f"claim:{k}", v) for k, v in covering_claim.items() if k in established]
        for subject, cov in flag_subjects:
            pa_, pb_ = _share(cov, ma, aud)[2], _share(cov, mb, aud)[2]
            gap = abs(pa_ - pb_)
            if gap >= BLINDSPOT_GAP_THRESHOLD:
                low = a.pole if pa_ < pb_ else b.pole
                s.add(m.BlindspotFlag(edition_id=edition.id, event_id=event.id, pole_id=low.id, subject=subject,
                                      diferencia_cobertura=round(gap, 4), umbral_usado=BLINDSPOT_GAP_THRESHOLD,
                                      impacto_estimado=event.impacto, estado="provisional"))
    # Daily curve for timelines (principal axis).
    s.query(m.CoverageDaily).filter_by(event_id=event.id).delete()
    pole_of = {}
    for pm in pole_members(s, principal, ts):
        for oid in pm.outlet_ids:
            pole_of[oid] = pm.pole.id
    counts = defaultdict(int)
    for a in arts:
        if a.outlet_id in pole_of:
            counts[(pole_of[a.outlet_id], a.fecha_pub.date())] += 1
    for (pid, day), n in sorted(counts.items()):
        s.add(m.CoverageDaily(event_id=event.id, pole_id=pid, dia=day, articulos=n))


def compute_framing(s: Session, edition: m.Edition, event: m.Event, cleavages: list[m.Cleavage]) -> None:
    """Triptych columns: headlines per pole and the claims with broad support
    that the pole barely mentions ('o que este enfoque não menciona')."""
    s.query(m.FramingSummary).filter_by(event_id=event.id).delete()
    active = active_outlets(s, edition)
    arts = _event_articles(s, event.id, edition)
    art_ids = {a.id for a in arts}
    claims = s.scalars(select(m.Claim).where(m.Claim.event_id == event.id)).all()
    ts = edition.corte_ingesta
    for cl in cleavages:
        members = pole_members(s, cl, ts)
        pole_of = {oid: pm.pole.id for pm in members for oid in pm.outlet_ids}
        # Broad = plain fact, or a disputed-figure group reported by >= 2 poles.
        groups: dict[str, list[m.Claim]] = defaultdict(list)
        for c in claims:
            if c.medida:
                groups["medida:" + c.medida].append(c)
            elif c.modo == "llano":
                groups[c.codigo].append(c)
        for pm in members:
            mem = pm.outlet_ids & active
            heads = [a for a in arts if a.outlet_id in mem]
            heads.sort(key=lambda a: -(s.get(m.Outlet, a.outlet_id).audiencia_estimada or 0))
            omitted = []
            for key, group in groups.items():
                cov_all = {sp.article.outlet_id for c in group for sp in c.supports if sp.article_id in art_ids}
                poles_reporting = {pole_of[o] for o in cov_all if o in pole_of}
                if key.startswith("medida:") and len(poles_reporting) < 2:
                    continue
                share = len(cov_all & mem) / len(mem) if mem else 0
                if share <= OMISSION_MAX_SHARE:
                    omitted.append(key)
            s.add(m.FramingSummary(event_id=event.id, pole_id=pm.pole.id,
                                   article_ids=[a.id for a in heads[:3]], no_menciona=omitted))


def run_event(s: Session, edition: m.Edition, event: m.Event) -> None:
    cleavages = s.scalars(select(m.Cleavage).where(
        m.Cleavage.country_id == event.country_id, m.Cleavage.activo.is_(True)).order_by(m.Cleavage.orden)).all()
    principal = next(c for c in cleavages if c.tipo == "principal")
    apply_selection(s, event.id, edition, principal)
    s.flush()
    compute_coverage(s, edition, event, cleavages, principal)
    compute_framing(s, edition, event, cleavages)
    s.flush()
