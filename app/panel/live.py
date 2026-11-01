"""Aggregates from the database for the panel, read-only. Never returns rows about readers
or the content of conversations; only counts, sums and the latest run summaries."""
from __future__ import annotations

from sqlalchemy import text

QUERIES = {
    "runs": """
        SELECT tipo, count(*) AS corridas, max(iniciado_en) AS ultima,
               sum(CASE WHEN estado = 'ok' THEN 1 ELSE 0 END) AS ok,
               sum(CASE WHEN estado = 'fallo' THEN 1 ELSE 0 END) AS fallo,
               sum(CASE WHEN estado = 'tope_gasto' THEN 1 ELSE 0 END) AS tope_gasto,
               round(sum(costo_centavos)::numeric, 2) AS costo_centavos
        FROM agent_run GROUP BY tipo ORDER BY tipo""",
    "steps": """
        SELECT agente, count(*) AS pasos, sum(tokens_in) AS tokens_in, sum(tokens_out) AS tokens_out,
               round(sum(costo_centavos)::numeric, 2) AS costo_centavos,
               sum(CASE WHEN estado = 'fallo' THEN 1 ELSE 0 END) AS fallos,
               string_agg(DISTINCT modelo, ', ') AS modelos, string_agg(DISTINCT prompt_version, ', ') AS prompts,
               round(avg(duracion_ms)) AS ms_medio
        FROM agent_step GROUP BY agente ORDER BY agente""",
    "queue": """
        SELECT tipo, sum(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS pendientes,
               sum(CASE WHEN estado = 'resuelto' THEN 1 ELSE 0 END) AS resueltos,
               sum(CASE WHEN estado = 'descartado' THEN 1 ELSE 0 END) AS descartados
        FROM review_item GROUP BY tipo ORDER BY tipo""",
    "claims": """
        SELECT c.estado, count(*) AS n FROM claim c JOIN event e ON e.id = c.event_id
        WHERE e.es_ficticio = false GROUP BY c.estado ORDER BY c.estado""",
    "editions": """
        SELECT ed.numero, ed.estado, ed.semana_inicio, ed.es_demo,
               (SELECT count(*) FROM edition_event ee WHERE ee.edition_id = ed.id) AS eventos
        FROM edition ed ORDER BY ed.numero DESC LIMIT 6""",
    "autonomy": "SELECT id, autonomy_level FROM country ORDER BY id",
    "last_claims_run": """
        SELECT id, iniciado_en, estado, round(costo_centavos::numeric, 2) AS costo_centavos, resumen
        FROM agent_run WHERE tipo = 'afirmaciones' ORDER BY id DESC LIMIT 4""",
    "chat_30d": """
        SELECT coalesce(sum(preguntas), 0) AS preguntas, coalesce(sum(rechazos_verificador), 0) AS rechazos,
               coalesce(sum(negativas), 0) AS negativas, round(coalesce(sum(costo_centavos), 0)::numeric, 2) AS costo_centavos
        FROM chat_usage_daily WHERE dia >= current_date - 30""",
    "articles_week": """
        SELECT count(*) AS articulos, count(DISTINCT outlet_id) AS medios FROM article
        WHERE es_ficticio = false AND fecha_pub >= now() - interval '7 days'""",
}

RESUMEN_KEYS = ("semana", "eventos_procesados", "propuestas", "rechazadas_compuertas", "aceptada", "en_revision",
                "rechazada", "tasa_desacuerdo", "costo_centavos", "verificador", "tope_gasto_alcanzado")


def _rows(result) -> list[dict]:
    return [dict(r._mapping) for r in result]


def gather() -> dict:
    """Returns {"ok": bool, "error": str | None, ...aggregates}. Never raises."""
    try:
        from ..db import session
        out: dict = {"ok": True, "error": None}
        with session() as s:
            s.execute(text("SET TRANSACTION READ ONLY"))
            for name, sql in QUERIES.items():
                out[name] = _rows(s.execute(text(sql)))
            for r in out["last_claims_run"]:
                r["resumen"] = {k: (r["resumen"] or {}).get(k) for k in RESUMEN_KEYS if (r["resumen"] or {}).get(k) is not None}
            s.rollback()
        try:
            from ..config import get_settings
            st = get_settings()
            # Model names and providers only; keys are never read here.
            out["effective_models"] = [
                {"role": "chat", "provider": st.chat_provider, "model": st.chat_model, "key": bool(st.chat_key)},
                {"role": "agentes", "provider": st.agent_provider, "model": st.agent_model, "key": bool(st.agent_api_key)},
                {"role": "verificador", "provider": st.verifier_provider, "model": st.verifier_model,
                 "key": bool(st.verifier_api_key)},
            ]
        except Exception:  # noqa: BLE001
            out["effective_models"] = []
        return out
    except Exception as e:  # noqa: BLE001 - the panel degrades to "no data"
        # Only the exception class: driver messages can contain host names.
        return {"ok": False, "error": type(e).__name__}
