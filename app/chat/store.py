"""Conversation storage under LGPD constraints: random session id that lives
only in the reader's tab, no IP, no account, short retention, aggregate metrics."""
from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings


def new_session(s: Session, edition_id: int, lang: str, factual: bool) -> str:
    sid = str(uuid.uuid4())
    days = get_settings().chat_retention_days
    s.add(m.ChatSession(id=sid, edition_id=edition_id, idioma=lang, modo_factual=factual,
                        expira_en=datetime.now(timezone.utc) + timedelta(days=days)))
    s.flush()
    return sid


def history(s: Session, sid: str) -> list[dict]:
    out = []
    for msg in s.scalars(select(m.ChatMessage).where(m.ChatMessage.session_id == sid).order_by(m.ChatMessage.id)):
        if msg.rol == "lector":
            out.append({"rol": "leitor", "texto": msg.contenido.get("texto", "")})
        else:
            out.append({"rol": "assistente", "texto": " ".join(sg.get("texto", "") for sg in msg.contenido.get("segmentos", []))})
    return out


def save_turn(s: Session, sid: str, question: str, segments: list[dict], check: dict, tin: int, tout: int) -> None:
    s.add(m.ChatMessage(session_id=sid, rol="lector", contenido={"texto": question}))
    s.add(m.ChatMessage(session_id=sid, rol="asistente", contenido={"segmentos": segments}, verificacion=check,
                        tokens_in=tin, tokens_out=tout))


def purge_expired(s: Session) -> int:
    now = datetime.now(timezone.utc)
    ids = list(s.scalars(select(m.ChatSession.id).where(m.ChatSession.expira_en < now)))
    if ids:
        s.execute(delete(m.ChatMessage).where(m.ChatMessage.session_id.in_(ids)))
        s.execute(delete(m.ChatSession).where(m.ChatSession.id.in_(ids)))
    return len(ids)


def usage_today(s: Session) -> m.ChatUsageDaily:
    row = s.get(m.ChatUsageDaily, date.today())
    if row is None:
        row = m.ChatUsageDaily(dia=date.today(), preguntas=0, tokens_in=0, tokens_out=0, costo_centavos=0,
                               rechazos_verificador=0, negativas=0)
        s.add(row)
        s.flush()
    return row


def record_usage(s: Session, tin: int, tout: int, rejections: int, negative: bool) -> None:
    st = get_settings()
    u = usage_today(s)
    u.preguntas += 1
    u.tokens_in += tin
    u.tokens_out += tout
    u.costo_centavos += tin / 1e6 * st.chat_price_in_cents_per_mtok + tout / 1e6 * st.chat_price_out_cents_per_mtok
    u.rechazos_verificador += rejections
    u.negativas += 1 if negative else 0


def budget_left(s: Session) -> bool:
    return usage_today(s).costo_centavos < get_settings().chat_daily_budget_usd_cents


class RateLimiter:
    """In-memory sliding window per client address. The address is never stored
    in the database or logs. With several machines, each enforces its own window
    (documented in docs/decisiones.md)."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key: str, per_hour: int) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= per_hour:
                return False
            q.append(now)
            if len(self.hits) > 50_000:
                self.hits = defaultdict(deque, {k: v for k, v in self.hits.items() if v and now - v[-1] < 3600})
            return True


limiter = RateLimiter()
