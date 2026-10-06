"""Weekly pipeline entrypoint: python -m app.pipeline.weekly [--forcar]

Idempotent. Safe to trigger more often than weekly (Fly's --schedule cannot
pin an exact time): it acts only between Saturday 00:00 and Monday 06:00 BRT,
i.e. after the Friday 23:59 ingestion cutoff and before publication, and only
if the week's draft edition does not exist yet. The weekend is for human review.

Stages:  ingest -> normalise/dedupe -> embed+entities -> cluster (7-day window)
         -> atomic claims -> cross-article alignment -> framing | coverage |
         selection + constrained drafting -> sentence verifier -> human review
         -> translation -> static site on approval.
Phase 1 implements the stages that run on already-loaded events (selection,
coverage, blind spots, framing, verifier, standard visuals). Ingestion,
clustering, claim extraction and drafting are Phase 2 (see docs/decisiones.md).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .. import models as m
from ..analytics.core import run_event
from ..analytics.visuals import build_standard_visuals
from ..chat.store import purge_expired
from ..config import get_settings
from ..db import session
from ..editorial import verify_brief_all_languages

BRT = ZoneInfo("America/Sao_Paulo")
log = logging.getLogger("aletheia.pipeline")


def week_window(now: datetime) -> dict | None:
    """Return the edition window if the pipeline should run now, else None."""
    local = now.astimezone(BRT)
    wd = local.weekday()  # Monday = 0
    if wd in (5, 6):
        monday = (local - timedelta(days=wd)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif wd == 0 and local.hour < 6:
        monday = (local - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return None
    return {"semana_inicio": monday, "semana_fin": monday + timedelta(days=6, hours=23, minutes=59),
            "corte_ingesta": monday + timedelta(days=4, hours=23, minutes=59),
            "publicacion_prevista": monday + timedelta(days=7, hours=6)}


def ingest(window: dict) -> int:
    log.warning("Ingestão real é a fase 2: nenhum artigo novo coletado (janela %s – %s).",
                window["semana_inicio"], window["corte_ingesta"])
    return 0


def run(force: bool = False, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    country = get_settings().country_code
    with session() as s:
        purge_expired(s)
    win = week_window(now)
    if win is None and not force:
        log.info("Fora da janela de produção (sábado 00:00 a segunda 06:00 BRT). Nada a fazer.")
        return 0
    if win is None:
        local = now.astimezone(BRT)
        monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        win = week_window(monday + timedelta(days=5))
    with session() as s:
        ed = s.scalars(select(m.Edition).where(m.Edition.country_id == country,
                                               m.Edition.semana_inicio == win["semana_inicio"],
                                               m.Edition.es_demo.is_(False))).first()
        if ed is not None and ed.estado in ("aprobada", "publicada"):
            log.info("Edição n.º %s já aprovada; nada a recalcular.", ed.numero)
            return 0
        if ed is None:
            last = s.scalars(select(m.Edition).where(m.Edition.country_id == country, m.Edition.es_demo.is_(False))
                             .order_by(m.Edition.numero.desc())).first()
            ed = m.Edition(country_id=country, numero=(last.numero + 1) if last else 1, estado="borrador", **win)
            s.add(ed)
            s.flush()
            log.info("Edição n.º %s criada em rascunho.", ed.numero)
    ingest(win)
    with session() as s:
        ed = s.scalars(select(m.Edition).where(m.Edition.country_id == country,
                                               m.Edition.semana_inicio == win["semana_inicio"],
                                               m.Edition.es_demo.is_(False))).first()
        for ee in ed.events:
            run_event(s, ed, ee.event)
            for b in s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ee.event_id,
                                                            m.NeutralBrief.edition_id == ed.id)):
                b.verificacion = verify_brief_all_languages(s, b)
                if b.estado != "aprobada":
                    b.estado = "verificada" if all(r["ok"] for r in b.verificacion.values()) else "rechazada"
        build_standard_visuals(s, ed)
        n_art = len(set(s.scalars(select(m.Article.outlet_id).where(m.Article.fecha_pub >= ed.semana_inicio,
                                                                   m.Article.fecha_pub <= ed.corte_ingesta))))
        _ingestion_alerts(s, ed)
        ed.estado = "en_revision"
        log.info("Edição n.º %s em revisão: %d eventos, %d veículos ativos.", ed.numero, len(ed.events), n_art)
    return 0


def _ingestion_alerts(s, ed: m.Edition) -> None:
    """Alert when a pole's active outlets drop sharply versus the previous edition:
    it may be a technical failure, not a blind spot."""
    from ..analytics.core import active_outlets, pole_members
    prev = s.scalars(select(m.Edition).where(m.Edition.country_id == ed.country_id, m.Edition.numero == ed.numero - 1,
                                             m.Edition.es_demo.is_(False))).first()
    if prev is None:
        return
    axis = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ed.country_id, m.Cleavage.tipo == "principal")).first()
    now_a, prev_a = active_outlets(s, ed), active_outlets(s, prev)
    for pm in pole_members(s, axis, ed.corte_ingesta):
        a, b = len(pm.outlet_ids & now_a), len(pm.outlet_ids & prev_a)
        if b and a < 0.6 * b:
            log.error("ALERTA de ingestão: polo %s caiu de %d para %d veículos ativos. Verificar coletores antes de "
                      "interpretar cobertura.", pm.pole.slug, b, a)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true", help="Roda fora da janela (sábado a segunda 06:00 BRT)")
    sys.exit(run(ap.parse_args().forcar))
