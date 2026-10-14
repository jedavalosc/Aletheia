"""Editorial panel (protected). Server-rendered, minimal, Portuguese.

Every approval records the editor's name. Publication is refused while any
gate fails (app/editorial.edition_gates)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
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
        country = s.get(m.Country, get_settings().country_code)
        n_queue = len(s.scalars(select(m.ReviewItem.id).where(m.ReviewItem.estado == "pendiente")).all())
        last_runs = s.scalars(select(m.AgentRun).order_by(m.AgentRun.id.desc()).limit(5)).all()
        return page("home.html", user, rows=rows, n_disputes=len(disputes), n_sugs=len(sugs), country=country,
                    n_queue=n_queue, last_runs=last_runs, msg=request.query_params.get("msg"))


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


def _redraft_job(ed_id: int, ev_id: int, instruction: str | None, user: str) -> None:
    from .agents.draft import draft_edition
    with session() as s:
        draft_edition(s, s.get(m.Edition, ed_id), [ev_id], redo=True, instruction=instruction or None,
                      disparado_por=f"editor:{user}")


@router.post("/evento/{ev_id}/redigir")
def redraft(ev_id: int, background: BackgroundTasks, ed_id: int = Form(...), instrucao: str = Form(""),
            csrf: str = Form(...), user: str = Depends(editor)):
    """Draft the chronicle again (new version), optionally with an editor instruction. Runs in the background:
    the drafter, checker and translator take one to two minutes."""
    check_csrf(user, csrf)
    if not get_settings().agent_api_key:
        return _back(f"/admin/edicao/{ed_id}", "Sem chave de modelo configurada (AGENT_API_KEY ou CHAT_API_KEY).")
    background.add_task(_redraft_job, ed_id, ev_id, instrucao.strip()[:1000], user)
    return _back(f"/admin/edicao/{ed_id}", "Redação iniciada: recarregue a página em dois minutos (ver Corridas).")


def _retranslate_job(brief_id: int, orden: int, user: str) -> None:
    from .agents.draft import retranslate_sentence
    with session() as s:
        b = s.get(m.NeutralBrief, brief_id)
        retranslate_sentence(s, b, orden, disparado_por=f"editor:{user}")
        b.verificacion = verify_brief_all_languages(s, b)
        b.estado = "verificada" if all(r["ok"] for r in b.verificacion.values()) else "rechazada"


@router.post("/oracao/{sent_id}/editar")
def edit_sentence(sent_id: int, background: BackgroundTasks, texto: str = Form(...), claim_ids: str = Form(...),
                  nome: str = Form(...), csrf: str = Form(...), user: str = Depends(editor)):
    """The editor rewrites one Portuguese sentence. Its machine translations are discarded and redone; the
    chronicle is verified again and needs a new approval."""
    check_csrf(user, csrf)
    with session() as s:
        st = s.get(m.BriefSentence, sent_id) or _404()
        b = s.get(m.NeutralBrief, st.brief_id)
        if b.estado == "aprobada":
            return _back(f"/admin/edicao/{b.edition_id}", "Crônica aprovada: redija uma nova versão para alterá-la.")
        old = st.texto
        st.texto = texto.strip()
        st.claim_ids = [c.strip() for c in claim_ids.replace(";", ",").split(",") if c.strip()]
        for tr in s.scalars(select(m.Translation).where(m.Translation.source_tipo == "brief_sentence",
                                                        m.Translation.source_id == st.id)):
            s.delete(tr)
        s.add(m.HumanReview(target_tipo="brief", target_id=b.id, revisor=nome.strip(), decision="cambios",
                            comentarios=f"Oração {st.orden} editada. Antes: {old}"))
        s.flush()
        b.verificacion = verify_brief_all_languages(s, b)
        b.estado = "rechazada"  # until translations are redone and verified
        ed_id, orden, bid = b.edition_id, st.orden, b.id
    if get_settings().agent_api_key:
        background.add_task(_retranslate_job, bid, orden, user)
        return _back(f"/admin/edicao/{ed_id}", "Oração editada; tradução em andamento (recarregue em um minuto).")
    return _back(f"/admin/edicao/{ed_id}", "Oração editada. Sem chave de modelo: traduza no bloco Traduções.")


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


# ---- agentic process: exception queue, run log, candidate events, autonomy (docs/agentes.md)

@router.get("/fila", response_class=HTMLResponse)
def queue(request: Request, estado: str = "pendiente", user: str = Depends(editor)):
    with session() as s:
        items = s.scalars(select(m.ReviewItem).where(m.ReviewItem.estado == estado)
                          .order_by(m.ReviewItem.prioridad, m.ReviewItem.id.desc()).limit(300)).all()
        events = {int(i.target_id): s.get(m.Event, int(i.target_id)) for i in items
                  if i.target_tipo == "event" and i.target_id.isdigit()}
        claims = {}
        for i in items:
            if i.target_tipo == "claim" and i.target_id.isdigit():
                c = s.get(m.Claim, int(i.target_id))
                if c is not None:
                    claims[int(i.target_id)] = {"c": c, "ev": s.get(m.Event, c.event_id),
                                                "sups": [(sp, s.get(m.Outlet, sp.article.outlet_id)) for sp in c.supports]}
        return page("queue.html", user, items=items, events=events, claims=claims, estado=estado,
                    msg=request.query_params.get("msg"))


@router.post("/fila/{item_id}")
def resolve_item(item_id: int, estado: str = Form(...), nome: str = Form(...), resolucion: str = Form(""),
                 afirmacao: str = Form(""), csrf: str = Form(...), user: str = Depends(editor)):
    check_csrf(user, csrf)
    if estado not in ("resuelto", "descartado", "pendiente"):
        raise HTTPException(422)
    from datetime import datetime, timezone
    msg = "Item atualizado."
    with session() as s:
        it = s.get(m.ReviewItem, item_id) or _404()
        it.estado, it.resuelto_por, it.resolucion = estado, nome.strip(), resolucion or None
        it.resuelto_en = datetime.now(timezone.utc) if estado != "pendiente" else None
        if it.target_tipo == "claim" and afirmacao in ("aceptada", "rechazada") and it.target_id.isdigit():
            c = s.get(m.Claim, int(it.target_id))
            if c is not None:
                c.estado = afirmacao
                c.verificacion = {**(c.verificacion or {}), "editor": {"nome": nome.strip(), "decisao": afirmacao,
                                                                       "nota": resolucion,
                                                                       "em": datetime.now(timezone.utc).isoformat()}}
                s.add(m.HumanReview(target_tipo="claim", target_id=c.id, revisor=nome.strip(), decision=afirmacao,
                                    comentarios=resolucion))
                s.flush()
                ev = s.get(m.Event, c.event_id)
                principal = s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == ev.country_id,
                                                               m.Cleavage.tipo == "principal")).first()
                if principal is not None:
                    from types import SimpleNamespace
                    from .analytics.core import apply_selection
                    apply_selection(s, c.event_id, SimpleNamespace(corte_ingesta=datetime.now(timezone.utc)), principal)
                msg = f"Afirmação {c.codigo}: {afirmacao}."
    return _back("/admin/fila", msg)


@router.get("/corridas", response_class=HTMLResponse)
def runs(request: Request, user: str = Depends(editor)):
    with session() as s:
        rows = s.scalars(select(m.AgentRun).order_by(m.AgentRun.id.desc()).limit(60)).all()
        return page("runs.html", user, rows=rows, msg=request.query_params.get("msg"))


@router.get("/corridas/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: int, request: Request, user: str = Depends(editor)):
    with session() as s:
        r = s.get(m.AgentRun, run_id) or _404()
        steps = s.scalars(select(m.AgentStep).where(m.AgentStep.run_id == run_id).order_by(m.AgentStep.id)).all()
        return page("run.html", user, r=r, steps=steps, msg=request.query_params.get("msg"))


def _week_start(semana: str | None):
    from .agents.cluster import current_monday, week_bounds
    wk = date.fromisoformat(semana) if semana else current_monday()
    return wk, week_bounds(wk)[0]


@router.get("/eventos", response_class=HTMLResponse)
def week_events(request: Request, semana: str | None = None, user: str = Depends(editor)):
    from datetime import timedelta
    wk, start = _week_start(semana)
    with session() as s:
        evs = s.scalars(select(m.Event).where(m.Event.semana_inicio == start, m.Event.es_ficticio.is_(False))
                        .order_by(m.Event.fuera_de_alcance, m.Event.impacto.desc())).all()
        rows = []
        for ev in evs:
            arts = s.execute(select(m.Article, m.Outlet).join(m.ArticleEvent, m.ArticleEvent.article_id == m.Article.id)
                             .join(m.Outlet, m.Outlet.id == m.Article.outlet_id)
                             .where(m.ArticleEvent.event_id == ev.id).order_by(m.Article.fecha_pub)).all()
            claims = s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id).order_by(m.Claim.id)).all()
            rows.append({"ev": ev, "arts": arts, "n_outlets": len({o.id for _, o in arts}), "claims": claims})
        return page("events.html", user, rows=rows, wk=wk, prev=(wk - timedelta(days=7)).isoformat(),
                    next=(wk + timedelta(days=7)).isoformat(), msg=request.query_params.get("msg"))


@router.post("/eventos/{ev_id}")
def edit_event(ev_id: int, accion: str = Form(...), nome: str = Form(...), titulo: str = Form(""),
               seccion: str = Form(""), destino: str = Form(""), razon: str = Form(""), csrf: str = Form(...),
               user: str = Depends(editor)):
    """Editor decisions on a candidate event. Confirmed events survive later regroupings."""
    check_csrf(user, csrf)
    from sqlalchemy import delete as sqldelete
    from .editorial import load_terms
    from .rules.loaded_terms import violations
    with session() as s:
        ev = s.get(m.Event, ev_id) or _404()
        wk = ev.semana_inicio.astimezone(__import__("zoneinfo").ZoneInfo("America/Sao_Paulo")).date().isoformat() if ev.semana_inicio else ""
        if accion == "confirmar":
            if titulo.strip():
                bad = violations(titulo, load_terms(s, ev.country_id, "pt"), "pt")
                if bad:
                    return _back(f"/admin/eventos?semana={wk}", "Título com termo carregado: " + ", ".join(h.termino for h in bad))
                ev.titulo_provisional = titulo.strip()
            if seccion:
                ev.seccion, ev.secciones_tocadas = seccion, [seccion]
            ev.estado, ev.fuera_de_alcance = "confirmado", False
        elif accion == "fora":
            ev.fuera_de_alcance, ev.estado = True, "confirmado"
        elif accion == "fundir":
            dest = s.get(m.Event, int(destino)) if destino.isdigit() else None
            if dest is None or dest.id == ev.id:
                return _back(f"/admin/eventos?semana={wk}", "Evento de destino inválido.")
            for ae in s.scalars(select(m.ArticleEvent).where(m.ArticleEvent.event_id == ev.id)).all():
                if s.get(m.ArticleEvent, (ae.article_id, dest.id)) is None:
                    s.add(m.ArticleEvent(article_id=ae.article_id, event_id=dest.id, score_similitud=ae.score_similitud,
                                         asignacion="manual"))
            s.execute(sqldelete(m.ArticleEvent).where(m.ArticleEvent.event_id == ev.id))
            s.flush()
            dest.estado = "confirmado"
            s.delete(ev)
        elif accion == "quitar_articulo":
            if destino.isdigit():
                s.execute(sqldelete(m.ArticleEvent).where(m.ArticleEvent.event_id == ev.id,
                                                          m.ArticleEvent.article_id == int(destino)))
            ev.estado = "confirmado"
        else:
            raise HTTPException(422)
        s.add(m.HumanReview(target_tipo="event", target_id=ev_id, revisor=nome.strip(), decision=accion,
                            comentarios=razon or titulo))
    return _back(f"/admin/eventos?semana={wk}", "Evento atualizado.")


@router.post("/autonomia")
def set_autonomy(nivel: int = Form(...), nome: str = Form(...), razon: str = Form(...), csrf: str = Form(...),
                 user: str = Depends(editor)):
    check_csrf(user, csrf)
    if nivel not in (0, 1, 2, 3):
        raise HTTPException(422)
    with session() as s:
        c = s.get(m.Country, get_settings().country_code) or _404()
        old = c.autonomy_level
        c.autonomy_level = nivel
        s.add(m.HumanReview(target_tipo="autonomia", target_id=0, revisor=nome.strip(), decision=f"{old}->{nivel}",
                            comentarios=razon))
    return _back("/admin", f"Nível de autonomia: {old} → {nivel}.")
