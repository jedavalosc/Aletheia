"""Step 1 — collection. Deterministic agent (no model calls).

Reads each outlet's RSS feeds and Google News sitemaps, checks robots.txt,
stores headline, link, date and the feed's short summary. Never fetches or
stores article bodies (copyright: brief §6). Idempotent: an article is keyed
by its canonical URL.

Gates and exceptions:
  * robots.txt disallows a source  -> source skipped, recorded.
  * a source fails 3 runs in a row  -> exception 'fuente_fallando'.
  * an outlet with sources returns nothing new for 48 h -> exception 'fuente_sin_novedades'.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

import feedparser
import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from .base import Run, agent_run

FEEDS_FILE = Path(__file__).resolve().parent.parent / "seed" / "feeds_br.json"
SUMMARY_MAX = 400
FAIL_STREAK_ALERT = 3
STALE_HOURS = 48
TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|origin$|cmpid$)", re.I)
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "news": "http://www.google.com/schemas/sitemap-news/0.9"}


def canonical_url(url: str) -> str:
    url = url.strip()
    # Redirect wrappers (e.g. Folha's redir.folha.com.br/.../*https://www1.folha...): keep the target.
    star = url.find("*http")
    if star != -1:
        url = url[star + 1:]
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if not TRACKING.match(k)]
    host = p.netloc.lower()
    return urlunparse(("https", host, p.path.rstrip("/") or "/", "", urlencode(q), ""))


def clean_text(raw: str | None, limit: int = SUMMARY_MAX) -> str | None:
    if not raw:
        return None
    t = re.sub(r"<[^>]+>", " ", raw)
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    if not t:
        return None
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + "…"


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc)
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def sync_feeds(s: Session, country_id: str = "BR") -> int:
    """Copy the verified source list into outlet.feeds (idempotent)."""
    conf = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    n = 0
    for name, feeds in conf.items():
        if name.startswith("_"):
            continue
        o = s.scalars(select(m.Outlet).where(m.Outlet.country_id == country_id, m.Outlet.nombre == name,
                                             m.Outlet.es_ficticio.is_(False))).first()
        if o is None:
            continue
        old = {f["url"]: f for f in (o.feeds or [])}
        merged = []
        for f in feeds:
            prev = old.get(f["url"], {})
            merged.append({**f, **{k: prev[k] for k in ("fallos_seguidos", "ultimo_ok", "ultimo_error") if k in prev}})
        o.feeds = merged
        n += 1
    s.flush()
    return n


class Fetcher:
    def __init__(self, user_agent: str):
        self.ua = user_agent
        self.client = httpx.Client(headers={"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"},
                                   timeout=25, follow_redirects=True)
        self.robots: dict[str, RobotFileParser] = {}
        self.last_hit: dict[str, float] = {}

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self.robots:
            rp = RobotFileParser()
            try:
                r = self.client.get(host + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])  # unreachable robots.txt: treat as no rules, as crawlers conventionally do
            self.robots[host] = rp
        return self.robots[host].can_fetch(self.ua, url)

    def get(self, url: str) -> httpx.Response:
        host = urlparse(url).netloc
        wait = 1.0 - (time.monotonic() - self.last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)  # at most one request per second per host
        r = self.client.get(url)
        self.last_hit[host] = time.monotonic()
        r.raise_for_status()
        return r


def parse_rss(content: bytes) -> list[dict]:
    f = feedparser.parse(content)
    out = []
    for e in f.entries:
        link = e.get("link")
        title = clean_text(e.get("title"), 500)
        if not link or not title:
            continue
        out.append({"url": link, "titular": title,
                    "fecha": _parse_date(e.get("published_parsed") or e.get("updated_parsed") or e.get("published")),
                    "resumen": clean_text(e.get("summary") or e.get("description")),
                    "autor": clean_text(e.get("author"), 200)})
    return out


def parse_news_sitemap(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    out = []
    for u in root.findall("sm:url", NS):
        loc = u.findtext("sm:loc", default="", namespaces=NS).strip()
        title = clean_text(u.findtext("news:news/news:title", default="", namespaces=NS), 500)
        date = _parse_date(u.findtext("news:news/news:publication_date", default="", namespaces=NS)
                           or u.findtext("sm:lastmod", default="", namespaces=NS))
        if loc and title:
            out.append({"url": loc, "titular": title, "fecha": date, "resumen": None, "autor": None})
    return out


def store(s: Session, outlet: m.Outlet, items: list[dict], tipo: str, now: datetime) -> tuple[int, int]:
    new = enriched = 0
    for it in items:
        cu = canonical_url(it["url"])
        h = hashlib.sha256(cu.encode()).hexdigest()
        row = s.scalars(select(m.Article).where(m.Article.hash_texto == h)).first()
        if row is not None:
            # A sitemap entry may arrive before the RSS one: keep the richer record.
            if not row.resumen and it.get("resumen"):
                row.resumen = it["resumen"]
                row.fuente_ingesta = tipo
                enriched += 1
            continue
        fecha = it["fecha"] or now
        if fecha > now + timedelta(hours=2):
            fecha = now  # wrong future dates in some feeds
        s.add(m.Article(outlet_id=outlet.id, url=cu, titular=it["titular"], resumen=it.get("resumen"), cuerpo=None,
                        cuerpo_permitido=False, fecha_pub=fecha, autor=it.get("autor"), idioma=outlet.idioma or "pt",
                        hash_texto=h, es_ficticio=False, fuente_ingesta=tipo, recolectado_en=now))
        new += 1
    s.flush()
    return new, enriched


def collect(s: Session, country_id: str = "BR", disparado_por: str = "cli", only: list[str] | None = None) -> dict:
    cfg = get_settings()
    totals = {"fuentes": 0, "fuentes_ok": 0, "bloqueadas_robots": 0, "nuevos": 0, "enriquecidos": 0, "fallos": 0}
    with agent_run(s, "recoleccion", country_id, disparado_por=disparado_por, budget_cents=0) as run:
        with run.step("sincronizar_fuentes") as st:
            st.salida = {"medios": sync_feeds(s, country_id)}
        with run.step("normalizar_urls") as st:
            fixed = 0
            for a in s.scalars(select(m.Article).where(m.Article.url.like("%*http%"), m.Article.es_ficticio.is_(False))):
                cu = canonical_url(a.url)
                h = hashlib.sha256(cu.encode()).hexdigest()
                if s.scalars(select(m.Article.id).where(m.Article.hash_texto == h)).first():
                    # Same article already stored under its real URL: drop the wrapped duplicate.
                    s.execute(delete(m.ArticleEvent).where(m.ArticleEvent.article_id == a.id))
                    s.execute(delete(m.ClaimSupport).where(m.ClaimSupport.article_id == a.id))
                    s.delete(a)
                    fixed += 1
                    continue
                a.url, a.hash_texto = cu, h
                fixed += 1
            st.salida = {"corregidos": fixed}
        fetcher = Fetcher(cfg.collector_user_agent)
        now = datetime.now(timezone.utc)
        outlets = s.scalars(select(m.Outlet).where(m.Outlet.country_id == country_id, m.Outlet.activo.is_(True),
                                                   m.Outlet.es_ficticio.is_(False))).all()
        for o in outlets:
            if only and o.nombre not in only:
                continue
            feeds = list(o.feeds or [])
            for i, f in enumerate(feeds):
                totals["fuentes"] += 1
                with run.step("recolector", f"{o.nombre} · {f['url']}", {"tipo": f["tipo"]}) as st:
                    if not fetcher.allowed(f["url"]):
                        st.estado, st.salida = "omitido", {"motivo": "robots.txt no permite"}
                        totals["bloqueadas_robots"] += 1
                        continue
                    try:
                        r = fetcher.get(f["url"])
                        items = parse_rss(r.content) if f["tipo"] == "rss" else parse_news_sitemap(r.content)
                    except Exception as e:  # noqa: BLE001
                        f["fallos_seguidos"] = f.get("fallos_seguidos", 0) + 1
                        f["ultimo_error"] = f"{type(e).__name__}: {e}"[:300]
                        totals["fallos"] += 1
                        if f["fallos_seguidos"] >= FAIL_STREAK_ALERT:
                            run.review("fuente_fallando", "outlet", o.id,
                                       f"A fonte {f['url']} falhou {f['fallos_seguidos']} vezes seguidas: {f['ultimo_error']}",
                                       {"url": f["url"], "medio": o.nombre}, prioridad=2)
                        raise
                    new, enr = store(s, o, items, f["tipo"], now)
                    f["fallos_seguidos"], f["ultimo_ok"] = 0, now.isoformat()
                    st.salida = {"entradas": len(items), "nuevos": new, "enriquecidos": enr}
                    totals["fuentes_ok"] += 1
                    totals["nuevos"] += new
                    totals["enriquecidos"] += enr
                feeds[i] = f
            o.feeds = feeds  # reassign so the JSON change is persisted
        with run.step("vigilancia_ingesta") as st:
            stale = []
            cutoff = now - timedelta(hours=STALE_HOURS)
            for o in outlets:
                if not o.feeds:
                    continue
                last = s.scalar(select(func.max(m.Article.recolectado_en)).where(m.Article.outlet_id == o.id))
                if last is None or last < cutoff:
                    stale.append(o.nombre)
                    run.review("fuente_sin_novedades", "outlet", o.id,
                               f"{o.nombre} não trouxe artigos novos nas últimas {STALE_HOURS} horas. "
                               "Pode ser falha técnica, não ponto cego.", {"ultimo": last.isoformat() if last else None})
            st.salida = {"medios_sin_novedades": stale}
        run.row.resumen = totals
    return totals
