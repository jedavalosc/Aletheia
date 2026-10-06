"""Web app: static site + chat API + dispute channel + editorial panel."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import models as m
from .admin import router as admin_router
from .chat.service import handle
from .chat.store import limiter, purge_expired
from .config import LANGS, get_settings
from .db import session
from .i18n import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("aletheia")


def rebuild_site() -> None:
    from .site.build import build_site
    with session() as s:
        build_site(s)


_built_marker: dict = {"v": None}


def _publication_marker():
    from sqlalchemy import func, select
    with session() as s:
        return s.scalar(select(func.max(m.Edition.publicada_en)).where(m.Edition.estado == "publicada"))


async def _site_sync():
    """Each web Machine rebuilds its static copy when a newer edition is published
    (approval may have happened on another Machine)."""
    while True:
        await asyncio.sleep(120)
        try:
            marker = await run_in_threadpool(_publication_marker)
            if marker != _built_marker["v"]:
                await run_in_threadpool(rebuild_site)
                from .chat.service import invalidate_corpus
                invalidate_corpus()
                _built_marker["v"] = marker
                log.info("site rebuilt for publication marker %s", marker)
        except Exception:  # noqa: BLE001
            log.exception("site sync failed")


async def _daily_purge():
    while True:
        try:
            with session() as s:
                n = purge_expired(s)
            if n:
                log.info("purged %d expired chat sessions", n)
        except Exception:  # noqa: BLE001
            log.exception("purge failed")
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _built_marker["v"] = await run_in_threadpool(_publication_marker)
        await run_in_threadpool(rebuild_site)
    except Exception:  # noqa: BLE001
        log.exception("site build at startup failed; serving the previous build if any")
    tasks = [asyncio.create_task(_daily_purge()), asyncio.create_task(_site_sync())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Aletheia News Brasil", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(admin_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Content-Security-Policy",
                            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                            "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; frame-ancestors 'none'")
    return resp


def client_key(request: Request) -> str:
    # Fly sets Fly-Client-IP. The value is used only in memory for rate limiting.
    return request.headers.get("fly-client-ip") or (request.client.host if request.client else "?")


class ChatIn(BaseModel):
    pergunta: str = Field(min_length=1, max_length=800)
    idioma: str = "pt"
    edicao: int | None = None
    evento: str | None = None
    modo_factual: bool = False
    sessao: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    lang = body.idioma if body.idioma in LANGS else "pt"
    if not limiter.allow(client_key(request), get_settings().chat_rate_per_ip_per_hour):
        return JSONResponse({"mensagem": t("chat_rate", lang)}, status_code=429)

    def work():
        with session() as s:
            return handle(s, body.pergunta, lang, body.edicao, body.evento, body.modo_factual, body.sessao)

    async def stream():
        yield _sse("status", {"estado": "verificando"})
        try:
            sid, ans = await run_in_threadpool(work)
        except Exception:  # noqa: BLE001
            log.exception("chat failed")
            yield _sse("error", {"mensagem": t("chat_unavailable", lang)})
            return
        if ans is None:
            yield _sse("error", {"mensagem": t("no_edition", lang)})
            return
        yield _sse("session", {"sessao": sid})
        # Segments are streamed only after the whole answer passed verification.
        for seg in ans.segments:
            yield _sse("segment", seg)
            await asyncio.sleep(0)
        yield _sse("done", {"modo": ans.mode, "verificado": ans.check.get("ok", False)})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


class DisputeIn(BaseModel):
    target_tipo: str = Field(max_length=30)
    target_ref: str = Field(min_length=1, max_length=80)
    texto: str = Field(min_length=1, max_length=4000)
    evidencia: str = Field(default="", max_length=4000)
    contacto: str | None = Field(default=None, max_length=200)
    idioma: str = "pt"


@app.post("/api/disputa")
async def dispute(body: DisputeIn, request: Request):
    if not limiter.allow("disputa:" + client_key(request), 20):
        raise HTTPException(429)
    allowed = {"brief_sentence", "claim", "visual", "commentary_statement", "outlet_position", "theme"}
    if body.target_tipo not in allowed:
        raise HTTPException(422, "target_tipo")
    with session() as s:
        s.add(m.Dispute(target_tipo=body.target_tipo, target_ref=body.target_ref, texto=body.texto,
                        evidencia=body.evidencia, contacto=(body.contacto or None)))
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


site_dir = get_settings().site_dir
site_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(site_dir), html=True, check_dir=False), name="site")
