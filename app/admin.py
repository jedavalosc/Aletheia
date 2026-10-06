"""Editorial panel (protected). Server-rendered, minimal, Portuguese.

Every approval records the editor's name. Publication is refused while any
gate fails (app/editorial.edition_gates)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from . import models as m
from .config import get_settings
from .db import session
from .editorial import approve_brief, approve_edition, edition_gates, mark_translation_reviewed, verify_brief_all_languages

router = APIRouter(prefix="/admin")
security = HTTPBasic()
env = Environment(loader=FileSystemLoader(Path(__file__).parent / "admin_templates"), autoescape=select_autoescape(["html"]))


def editor(creds: HTTPBasicCredentials = Depends(security)) -> str:
    st = get_settings()
    if not st.admin_password:
        raise HTTPException(503, "Painel desativado: defina ADMIN_PASSWORD.")
    ok_user = secrets.compare_digest(creds.username.encode(), st.admin_user.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), st.admin_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    return creds.username


def csrf_token(user: str) -> str:
    key = (get_settings().admin_password or "").encode()
    return hmac.new(key, f"csrf:{user}".encode(), hashlib.sha256).hexdigest()


def check_csrf(user: str, token: str) -> None:
    if not hmac.compare_digest(csrf_token(user), token or ""):
        raise HTTPException(403, "CSRF")


def page(name: str, user: str, **kw) -> HTMLResponse:
    return HTMLResponse(env.get_template(name).render(user=user, csrf=csrf_token(user), **kw))


def _back(url: str, msg: str = "") -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(f"{url}?msg={quote(msg)}" if msg else url, status_code=303)


@router.get("", response_class=HTMLResponse)
def home(request: Request, user: str = Depends(editor)):
    with session() as s:
        eds = s.scalars(select(m.Edition).order_by(m.Edition.numero.desc())).all()
        rows = [{"ed": e, "gates": edition_gates(s, e) if e.estado != "publicada" else []} for e in eds]
        disputes = s.scalars(select(m.Dispute).where(m.Dispute.estado == "recibida")).all()
        sugs = s.scalars(select(m.ChatSuggestion).where(m.ChatSuggestion.estado == "pendiente")).all()
        return page("home.html", user, rows=rows, n_disputes=len(disputes), n_sugs=len(sugs), msg=request.query_params.get("msg"))


@router.get("/edicao/{ed_id}", response_class=HTMLResponse)
def edition_page(ed_id: int, request: Request, user: str = Depends(editor)):
    with session() as s:
        ed = s.get(m.Edition, ed_id) or _404()
        events = []
        for ee in ed.events:
            ev = ee.event
            brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id, m.NeutralBrief.edition_id == ed.id)
                              .order_by(m.NeutralBrief.version.desc())).first()
            trs = []
            if brief:
                for st in brief.sentences:
                    for tr in s.scalars(select(m.Translation).where(m.Translation.source_tipo == "brief_sentence",
                                                                    m.Translation.source_id == st.id)):
                        trs.append({"tr": tr, "orig": st.texto})
            events.append({
                "ev": ev, "brief": brief, "translations": trs,
                "claims": s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id)).all(),
                "flags": [(f, s.get(m.Pole, f.pole_id)) for f in s.scalars(select(m.BlindspotFlag).where(m.BlindspotFlag.event_id == ev.id))],
                "visuals": s.scalars(select(m.Visual).where(m.Visual.event_id == ev.id, m.Visual.edition_id == ed.id)).all(),
                "articles": [(a, s.get(m.Outlet, a.outlet_id)) for a in s.scalars(
                    select(m.Article).join(m.ArticleEvent, m.ArticleEvent.article_id == m.Article.id).where(m.ArticleEvent.event_id == ev.id))],
            })
        all_events = s.scalars(select(m.Event).order_by(m.Event.id)).all()
        return page("edition.html", user, ed=ed, events=events, gates=edition_gates(s, ed), all_events=all_events,
                    msg=request.query_params.get("msg"))


def _404():
    raise HTTPException(404)


@router.post("/cronica/{brief_id}/aprovar")
def approve_brief_route(brief_id: int, nome: str = Form(...), comentarios: str = Form(""), csrf: str = Form(...),
                        user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        b = s.get(m.NeutralBrief, brief_id) or _404()
        try:
            approve_brief(s, b, nome.strip(), comentarios)
            msg = "Crônica aprovada."
        except ValueError as e:
            msg = str(e)
        return _back(f"/admin/edicao/{b.edition_id}", msg)


@router.post("/cronica/{brief_id}/verificar")
def reverify(brief_id: int, csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        b = s.get(m.NeutralBrief, brief_id) or _404()
        b.verificacion = verify_brief_all_languages(s, b)
        if b.estado != "aprobada":
            b.estado = "verificada" if all(r["ok"] for r in b.verificacion.values()) else "rechazada"
        return _back(f"/admin/edicao/{b.edition_id}", "Verificação refeita.")


@router.post("/cronica/{brief_id}/rejeitar")
def reject_brief(brief_id: int, nome: str = Form(...), comentarios: str = Form(...), csrf: str = Form(...),
                 user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        b = s.get(m.NeutralBrief, brief_id) or _404()
        b.estado = "rechazada"
        s.add(m.HumanReview(target_tipo="brief", target_id=b.id, revisor=nome.strip(), decision="rechazada", comentarios=comentarios))
        return _back(f"/admin/edicao/{b.edition_id}", "Crônica devolvida.")


@router.post("/evento/{ev_id}/confirmar-inclusao")
def confirm_inclusion(ev_id: int, ed_id: int = Form(...), nome: str = Form(...), csrf: str = Form(...),
                      user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        ev = s.get(m.Event, ev_id) or _404()
        ev.razon_inclusion_confirmada_por = nome.strip()
        s.add(m.HumanReview(target_tipo="event", target_id=ev.id, revisor=nome.strip(), decision="aprobada",
                            comentarios="Inclusão excepcional confirmada: " + (ev.razon_inclusion or "")))
        return _back(f"/admin/edicao/{ed_id}", "Inclusão confirmada.")


@router.post("/traducao/{tr_id}/revisada")
def translation_reviewed(tr_id: int, ed_id: int = Form(...), nome: str = Form(...), texto: str = Form(...),
                         csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        tr = s.get(m.Translation, tr_id) or _404()
        tr.texto = texto.strip()
        mark_translation_reviewed(s, tr, nome.strip())
        # A changed translation invalidates the brief approval until re-verified and re-approved.
        st = s.get(m.BriefSentence, tr.source_id)
        b = s.get(m.NeutralBrief, st.brief_id)
        b.verificacion = verify_brief_all_languages(s, b)
        if not all(r["ok"] for r in b.verificacion.values()):
            b.estado = "rechazada"
        return _back(f"/admin/edicao/{ed_id}", "Tradução marcada como revisada.")


@router.post("/bandeira/{flag_id}")
def flag_state(flag_id: int, ed_id: int = Form(...), estado: str = Form(...), csrf: str = Form(...),
               user: str = Depends(editor)):
    check_csrf(user, csrf)
    if estado not in ("provisional", "confirmada", "descartada"):
        raise HTTPException(422)
    with session() as s:
        f = s.get(m.BlindspotFlag, flag_id) or _404()
        f.estado = estado
        return _back(f"/admin/edicao/{ed_id}", "Bandeira atualizada.")


@router.post("/artigo/reatribuir")
def reassign_article(ed_id: int = Form(...), article_id: int = Form(...), from_event: int = Form(...),
                     to_event: int = Form(...), csrf: str = Form(...), user: str = Depends(editor)):
    """Manual merge/split primitive for clusters: move an article between events,
    then recompute coverage, framing and selection for both events."""
    check_csrf(user, csrf)
    from .analytics.core import run_event
    with session() as s:
        ae = s.get(m.ArticleEvent, (article_id, from_event)) or _404()
        s.delete(ae)
        s.flush()
        if s.get(m.ArticleEvent, (article_id, to_event)) is None:
            s.add(m.ArticleEvent(article_id=article_id, event_id=to_event, score_similitud=1.0, asignacion="manual"))
        s.flush()
        ed = s.get(m.Edition, ed_id)
        for eid in (from_event, to_event):
            ev = s.get(m.Event, eid)
            if ev and any(ee.event_id == eid for ee in ed.events):
                run_event(s, ed, ev)
        return _back(f"/admin/edicao/{ed_id}", "Artigo reatribuído; cobertura recalculada.")


@router.post("/edicao/{ed_id}/aprovar")
async def approve_edition_route(ed_id: int, nome: str = Form(...), csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        ed = s.get(m.Edition, ed_id) or _404()
        problems = approve_edition(s, ed, nome.strip())
    if problems:
        return _back(f"/admin/edicao/{ed_id}", "Não aprovada: " + " | ".join(problems))
    from .chat.service import invalidate_corpus
    from .main import rebuild_site
    await run_in_threadpool(rebuild_site)
    invalidate_corpus()
    return _back("/admin", f"Edição publicada e site regenerado.")


# ---- configuration: loaded terms, axes, exclusions

@router.get("/termos", response_class=HTMLResponse)
def terms(request: Request, user: str = Depends(editor)):
    with session() as s:
        rows = s.scalars(select(m.LoadedTerm).order_by(m.LoadedTerm.idioma, m.LoadedTerm.termino)).all()
        return page("terms.html", user, rows=rows, today=date.today(), msg=request.query_params.get("msg"))


@router.post("/termos")
def add_term(idioma: str = Form(...), termino: str = Form(...), patron: str = Form(...), permitido_si: str = Form(...),
             alternativa: str = Form(""), nota: str = Form(""), csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    import re
    try:
        re.compile(patron)
    except re.error as e:
        return _back("/admin/termos", f"Padrão inválido: {e}")
    with session() as s:
        s.add(m.LoadedTerm(country_id=get_settings().country_code, idioma=idioma, termino=termino.strip(),
                           patron=patron.strip(), permitido_si=permitido_si, alternativa=alternativa or None,
                           nota=nota, vigente_desde=date.today()))
    return _back("/admin/termos", "Termo adicionado.")


@router.post("/termos/{term_id}/encerrar")
def end_term(term_id: int, csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        t_ = s.get(m.LoadedTerm, term_id) or _404()
        t_.vigente_hasta = date.today()
    return _back("/admin/termos", "Vigência encerrada (o histórico é mantido).")


@router.get("/eixos", response_class=HTMLResponse)
def axes(request: Request, user: str = Depends(editor)):
    with session() as s:
        rows = s.scalars(select(m.Cleavage).order_by(m.Cleavage.orden)).all()
        excl = s.scalars(select(m.ExclusionList)).all()
        return page("axes.html", user, rows=rows, excl=excl, msg=request.query_params.get("msg"))


@router.post("/eixos/{axis_id}")
def update_axis(axis_id: int, activo: str = Form("0"), descripcion: str = Form(...), es_hipotesis: str = Form("0"),
                csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        a = s.get(m.Cleavage, axis_id) or _404()
        a.activo, a.es_hipotesis, a.descripcion = activo == "1", es_hipotesis == "1", descripcion
    return _back("/admin/eixos", "Eixo atualizado. Recalcule as edições em revisão para refletir a mudança.")


@router.post("/eixos/novo")
def new_axis(slug: str = Form(...), nombre: str = Form(...), tipo: str = Form(...), polo_a: str = Form(...),
             polo_b: str = Form(...), descripcion: str = Form(""), csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        n = len(s.scalars(select(m.Cleavage)).all())
        c = m.Cleavage(country_id=get_settings().country_code, slug=slug, nombre=nombre, tipo=tipo, activo=False,
                       es_hipotesis=True, orden=n, descripcion=descripcion, vigente_desde=date.today())
        s.add(c)
        s.flush()
        s.add_all([m.Pole(cleavage_id=c.id, slug=slug + "-a", etiqueta=polo_a, orden=0),
                   m.Pole(cleavage_id=c.id, slug=slug + "-b", etiqueta=polo_b, orden=1)])
    return _back("/admin/eixos", "Eixo criado inativo; ative-o quando houver posições estimadas.")


@router.post("/exclusoes")
def add_exclusion(elemento: str = Form(...), motivo: str = Form(...), colores: str = Form(""), csrf: str = Form(...),
                  user: str = Depends(editor)):
    check_csrf(user, csrf)
    cols = [c.strip() for c in colores.split(",") if c.strip()]
    with session() as s:
        s.add(m.ExclusionList(country_id=get_settings().country_code, elemento=elemento, colores=cols, motivo=motivo,
                              confirmado=True, vigente_desde=date.today()))
    return _back("/admin/eixos", "Exclusão adicionada.")


@router.post("/exclusoes/{ex_id}/confirmar")
def confirm_exclusion(ex_id: int, csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        x = s.get(m.ExclusionList, ex_id) or _404()
        x.confirmado = True
    return _back("/admin/eixos", "Exclusão confirmada.")


@router.get("/entradas", response_class=HTMLResponse)
def inbox(request: Request, user: str = Depends(editor)):
    with session() as s:
        return page("inbox.html", user, disputes=s.scalars(select(m.Dispute).order_by(m.Dispute.id.desc())).all(),
                    sugs=s.scalars(select(m.ChatSuggestion).order_by(m.ChatSuggestion.id.desc())).all(),
                    msg=request.query_params.get("msg"))


@router.post("/entradas/disputa/{d_id}")
def dispute_state(d_id: int, estado: str = Form(...), resolucion: str = Form(""), csrf: str = Form(...),
                  user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        d = s.get(m.Dispute, d_id) or _404()
        d.estado, d.resolucion = estado, resolucion or d.resolucion
    return _back("/admin/entradas", "Contestação atualizada.")


@router.post("/entradas/sugestao/{s_id}")
def suggestion_state(s_id: int, estado: str = Form(...), csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    with session() as s:
        x = s.get(m.ChatSuggestion, s_id) or _404()
        x.estado = estado
    return _back("/admin/entradas", "Sugestão atualizada.")
