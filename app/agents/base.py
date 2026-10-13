"""Run log, provenance and spending cap shared by every agent."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..llm import Completion, complete, parse_json

log = logging.getLogger("aletheia.agents")


class BudgetExceeded(Exception):
    pass


class Run:
    def __init__(self, s: Session, row: m.AgentRun):
        self.s, self.row, self.settings = s, row, get_settings()

    @property
    def id(self) -> int:
        return self.row.id

    @contextmanager
    def step(self, agente: str, objetivo: str = "", entrada: dict | None = None):
        st = m.AgentStep(run_id=self.row.id, agente=agente, objetivo=objetivo[:300], entrada=entrada or {})
        self.s.add(st)
        self.s.flush()
        t0 = time.monotonic()
        try:
            yield st
            if st.estado not in ("fallo", "omitido"):
                st.estado = "ok"
        except BudgetExceeded:
            st.estado, st.error = "omitido", "tope de gasto alcanzado"
            raise
        except Exception as e:  # noqa: BLE001 - recorded, run continues
            st.estado, st.error = "fallo", f"{type(e).__name__}: {e}"[:2000]
            log.warning("step %s %s failed: %s", agente, objetivo, e)
        finally:
            st.duracion_ms = int((time.monotonic() - t0) * 1000)
            self.s.flush()

    def llm(self, st: m.AgentStep, system: str, user: str, prompt_version: str, json_mode: bool = True,
            max_tokens: int | None = None) -> dict | str:
        cfg = self.settings
        if self.row.costo_centavos >= self.row.tope_centavos:
            raise BudgetExceeded()
        c: Completion = complete(cfg, system, user, json_mode=json_mode, max_tokens=max_tokens)
        cost = c.tokens_in / 1e6 * cfg.agent_price_in_cents_per_mtok + c.tokens_out / 1e6 * cfg.agent_price_out_cents_per_mtok
        st.modelo, st.prompt_version = c.model, prompt_version
        st.tokens_in += c.tokens_in
        st.tokens_out += c.tokens_out
        st.costo_centavos += cost
        self.row.costo_centavos += cost
        self.s.flush()
        return parse_json(c.text) if json_mode else c.text

    def review(self, tipo: str, target_tipo: str, target_id, motivo: str, datos: dict | None = None,
               prioridad: int = 2, dedupe: bool = True) -> m.ReviewItem | None:
        if dedupe:
            existing = self.s.scalars(select(m.ReviewItem).where(
                m.ReviewItem.tipo == tipo, m.ReviewItem.target_tipo == target_tipo,
                m.ReviewItem.target_id == str(target_id), m.ReviewItem.estado == "pendiente")).first()
            if existing:
                existing.datos = {**existing.datos, **(datos or {}), "visto_de_nuevo": datetime.now(timezone.utc).isoformat()}
                return existing
        it = m.ReviewItem(country_id=self.row.country_id, run_id=self.row.id, tipo=tipo, target_tipo=target_tipo,
                          target_id=str(target_id), motivo=motivo, datos=datos or {}, prioridad=prioridad)
        self.s.add(it)
        self.s.flush()
        return it


@contextmanager
def agent_run(s: Session, tipo: str, country_id: str, edition_id: int | None = None, disparado_por: str = "cli",
              budget_cents: float | None = None):
    country = s.get(m.Country, country_id)
    if country is None:
        raise SystemExit(f"País {country_id} não configurado: rode seed-brasil.")
    cfg = get_settings()
    row = m.AgentRun(country_id=country_id, tipo=tipo, edition_id=edition_id, autonomy_level=country.autonomy_level,
                     estado="corriendo", tope_centavos=budget_cents if budget_cents is not None else cfg.agent_budget_cents_per_run,
                     disparado_por=disparado_por, resumen={})
    s.add(row)
    s.flush()
    s.commit()  # make the run visible while it executes
    run = Run(s, row)
    try:
        yield run
        row.estado = "ok"
    except BudgetExceeded:
        row.estado = "tope_gasto"
        log.warning("run %s stopped at spending cap (%.2f cents)", row.id, row.costo_centavos)
    except Exception as e:
        row.estado = "fallo"
        row.resumen = {**(row.resumen or {}), "error": f"{type(e).__name__}: {e}"[:2000]}
        raise
    finally:
        row.terminado_en = datetime.now(timezone.utc)
        s.commit()
