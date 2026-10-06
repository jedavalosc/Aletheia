"""Chat orchestration: retrieval -> model (or offline responder) -> verifier ->
one repair attempt -> fallback. Nothing unverified is returned."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import LANGS, get_settings
from ..editorial import load_terms
from ..i18n import t
from .corpus import Corpus, Doc, build_corpus
from .prompt import SYSTEM, render_context, repair_message
from .store import budget_left, history, new_session, record_usage, save_turn
from .verify import verify_answer

log = logging.getLogger("aletheia.chat")

_CORPUS: dict[tuple[int, str], Corpus] = {}

INTENTS = {
    "opinion": r"quem (tem|est[aá] com) (a )?raz|o que (voc[eê]|vc) acha|sua opini|qui[eé]n tiene (la )?raz|qu[eé] opina|tu opini|su opini|who('s| is) right|what do you think|your (own )?opinion|[eé] (justo|certo)|es justo|is it (fair|right)|deveria|deber[ií]a|should (the|they)",
    "prediction": r"vai acontecer|o que acontecer[aá]|vai (ganhar|perder|ser)|will happen|what will|will (they|the)|qu[eé] pasar[aá]|va a pasar|prev(ê|e)|predic|previs",
    "injection": r"ignor[ea]|disregard|system prompt|prompt do sistema|instru[cç]|instruction|finja|pretend|act as|act[uú]a como|jailbreak|\bDAN\b|reveal|revele|revela tus",
    "method": r"metodolog|como (voc[eê]s|se) (mede|calcul|decid)|c[oó]mo (se )?(calcul|decid)|how (do you|is) (measure|calculat|decide)|denominador|denominator|regra de sele|selection rule|como funciona|how does .* work|fato estabelecido|hecho establecido|established fact",
    "academic": r"acad[eê]mic|academic|comentador|commentator|n[aã]o sabemos|no sabemos|don.t know",
}
NO_ANSWER_THRESHOLD = 3.0
FRAMED = r"escond|ocult|esconde|hiding|hide|cover(ing)? up|m[ií]dia|imprensa|prensa|press|ataque|attack|gan[aâ]ncia|codicia|greed|farra|despilfarro|spree|invas|ocupa|occup|despej|desalojo|evict"


def corpus_for(s: Session, numero: int | None, country: str) -> Corpus | None:
    q = select(m.Edition).where(m.Edition.country_id == country, m.Edition.estado == "publicada")
    if numero is not None:
        q = q.where(m.Edition.numero == numero)
    ed = s.scalars(q.order_by(m.Edition.numero.desc())).first()
    if ed is None:
        return None
    key = (ed.id, str(ed.publicada_en))
    if key not in _CORPUS:
        _CORPUS.clear()
        _CORPUS[key] = build_corpus(s, ed)
    return _CORPUS[key]


def invalidate_corpus() -> None:
    _CORPUS.clear()


@dataclass
class Answer:
    segments: list[dict]
    check: dict
    mode: str  # modelo / offline / fallback
    tokens_in: int = 0
    tokens_out: int = 0
    rejections: int = 0
    suggestion: str | None = None
    negative: bool = False
    raw_attempts: list = field(default_factory=list)


def retrieve(corpus: Corpus, question: str, event: str | None, factual: bool) -> list[Doc]:
    allow = None
    if factual:
        allow = {"claim", "frase", "cobertura", "ponto_cego", "visual", "edicao", "metodo"}
    hits = [d for _, d in corpus.index.search(question, k=14, event=event, allow=allow)]
    ids = {d.id for d in hits}
    extra = [corpus.docs["edicao"]] if "edicao" not in ids else []
    # Disputed figures travel together: if one source is retrieved, all are.
    for d in list(hits):
        for c in d.claim_ids:
            med = corpus.claims.get(c, {}).get("medida")
            if med:
                for k, v in corpus.claims.items():
                    if v["medida"] == med and f"claim:{k}" not in ids:
                        extra.append(corpus.docs[f"claim:{k}"])
                        ids.add(f"claim:{k}")
    if hits and hits[0].event in corpus.events:  # facts that each pole's framing leaves out
        for c in corpus.events[hits[0].event].get("omitted", []):
            if f"claim:{c}" not in ids:
                extra.append(corpus.docs[f"claim:{c}"])
                ids.add(f"claim:{c}")
    for d in list(hits):  # coverage of an event always travels with its blind-spot flags
        if d.tipo == "cobertura":
            for k, doc in corpus.docs.items():
                if doc.tipo == "ponto_cego" and doc.event == d.event and k not in ids:
                    extra.append(doc)
                    ids.add(k)
    for d in hits:  # claims cited by retrieved sentences/statements
        for c in d.claim_ids:
            if f"claim:{c}" not in ids and f"claim:{c}" in corpus.docs:
                extra.append(corpus.docs[f"claim:{c}"])
                ids.add(f"claim:{c}")
    return hits + extra


def _decorate(s: Session, corpus: Corpus, segs: list[dict], lang: str) -> list[dict]:
    out = []
    for sg in segs:
        sg = {k: sg.get(k) for k in ("tipo", "texto", "claim_ids", "refs")}
        sg["claim_ids"] = sg.get("claim_ids") or []
        sg["refs"] = sg.get("refs") or []
        if sg["tipo"] == "interpretacao":
            metas = []
            for r in sg["refs"]:
                d = corpus.docs.get(r)
                if d and d.meta.get("scholar"):
                    status = t("status_" + d.meta["estatus"], lang) if d.meta.get("estatus") else t("what_we_dont_know", lang)
                    metas.append(f"{d.meta['scholar']} · {status}")
            sg["meta"] = "; ".join(dict.fromkeys(metas))
        if sg["tipo"] == "sem_informacao":
            sg["texto"] = f"{sg['texto']} {t('chat_cutoff_suffix', lang, d=corpus.corte[lang])}"
        out.append(sg)
    return out


def _parse(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def offline_answer(corpus: Corpus, question: str, lang: str, event: str | None, factual: bool) -> list[dict]:
    """Deterministic extractive responder: returns verified chronicle material only."""
    q = question.lower()
    segs: list[dict] = []
    if re.search(INTENTS["injection"], q, re.I):
        return [{"tipo": "esclarecimento", "texto": t("chat_injection", lang)}]
    if re.search(INTENTS["method"], q, re.I):
        hits = [d for _, d in corpus.index.search(question, k=3, allow={"metodo", "edicao"})]
        if hits:
            return [{"tipo": "metodologia", "texto": d.text[lang], "refs": [d.id]} for d in hits[:2]]
    if re.search(INTENTS["academic"], q, re.I) and not factual:
        hits = corpus.index.search(question, k=4, event=event, allow={"academico", "pergunta_aberta"})
        if hits:
            out = []
            for _, d in hits[:3]:
                body = d.text[lang].split(" — ")[0]
                if d.tipo == "academico":
                    body = body.split(" (")[0].split(" [")[0]
                out.append({"tipo": "interpretacao", "texto": body, "refs": [d.id], "claim_ids": d.claim_ids})
            return out
    scored = corpus.index.search(question, k=10, event=event,
                                 allow={"claim", "frase", "academico", "pergunta_aberta", "cobertura", "ponto_cego"}
                                 if not factual else {"claim", "frase", "cobertura", "ponto_cego"})
    if re.search(INTENTS["opinion"], q, re.I):
        segs.append({"tipo": "esclarecimento", "texto": t("chat_no_opinion", lang)})
    elif re.search(INTENTS["prediction"], q, re.I):
        segs.append({"tipo": "esclarecimento", "texto": t("chat_no_prediction", lang)})
    if not scored or scored[0][0] < NO_ANSWER_THRESHOLD:
        return segs + [{"tipo": "sem_informacao", "texto": t("chat_no_info", lang)}]
    seen: set[str] = set()
    framed = bool(re.search(FRAMED, q, re.I))
    for score, d in scored:
        if len([s_ for s_ in segs if s_["tipo"] != "esclarecimento"]) >= 4 or score < NO_ANSWER_THRESHOLD * 0.6:
            break
        if d.tipo in ("claim", "frase"):
            for c in d.claim_ids:
                if c in seen:
                    continue
                group = [c]
                med = corpus.claims[c]["medida"]
                if med:
                    group = [k for k, v in corpus.claims.items() if v["medida"] == med]
                for g in group:
                    if g not in seen:
                        seen.add(g)
                        segs.append({"tipo": "fato", "texto": corpus.claims[g]["texts"][lang], "claim_ids": [g]})
        elif d.tipo in ("cobertura", "ponto_cego"):
            segs.append({"tipo": "cobertura", "texto": d.text[lang], "refs": [d.id]})
        elif d.tipo in ("academico", "pergunta_aberta") and not factual and not framed:
            body = d.text[lang].split(" — ")[0]
            if d.tipo == "academico":
                body = body.split(" (")[0].split(" [")[0]
            segs.append({"tipo": "interpretacao", "texto": body,
                         "refs": [d.id], "claim_ids": d.claim_ids})
    if framed and scored:
        # A question framed from one pole also gets the established facts the other framing leaves out.
        ev = scored[0][1].event
        for c in (corpus.events.get(ev, {}).get("omitted") or []):
            if c not in seen and len([x for x in segs if x["tipo"] == "fato"]) < 6:
                seen.add(c)
                segs.append({"tipo": "fato", "texto": corpus.claims[c]["texts"][lang], "claim_ids": [c]})
    return segs


def answer(s: Session, corpus: Corpus, question: str, lang: str, event: str | None, factual: bool,
           hist: list[dict]) -> Answer:
    settings = get_settings()
    lang = lang if lang in LANGS else "pt"
    terms = load_terms(s, "BR", lang)
    use_model = bool(settings.chat_key) and budget_left(s)
    if not use_model:
        segs = offline_answer(corpus, question, lang, event, factual)
        chk = verify_answer(corpus, segs, terms, lang, factual)
        if not chk.ok:
            log.warning("offline answer failed verification: %s", chk.issues)
            segs = _fallback(corpus, question, lang, event, factual)
            chk = verify_answer(corpus, segs, terms, lang, factual)
        return Answer(_decorate(s, corpus, segs, lang), {"ok": chk.ok, "issues": chk.issues, **chk.stats}, "offline",
                      negative=any(sg["tipo"] == "sem_informacao" for sg in segs))
    hits = retrieve(corpus, question, event, factual)
    context = render_context(corpus, hits, lang, factual, hist, question)
    messages = [{"role": "user", "content": context}]
    tin = tout = rejections = 0
    issues: list[str] = []
    attempts = []
    for attempt in range(2):
        raw, i_tok, o_tok = call_model(settings, messages)
        tin += i_tok
        tout += o_tok
        attempts.append(raw)
        try:
            data = _parse(raw)
            segs = data.get("segmentos") or []
            suggestion = data.get("sugestao_para_extracao")
        except (ValueError, json.JSONDecodeError):
            segs, suggestion = [], None
            issues = ["saída não é JSON válido"]
        else:
            chk = verify_answer(corpus, segs, terms, lang, factual)
            if chk.ok:
                return Answer(_decorate(s, corpus, segs, lang), {"ok": True, "issues": [], **chk.stats}, "modelo",
                              tin, tout, rejections, suggestion if isinstance(suggestion, str) else None,
                              negative=any(sg.get("tipo") == "sem_informacao" for sg in segs), raw_attempts=attempts)
            issues = chk.issues
        rejections += 1
        messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": repair_message(issues)}]
    log.warning("model answer rejected twice: %s", issues)
    segs = _fallback(corpus, question, lang, event, factual)
    chk = verify_answer(corpus, segs, terms, lang, factual)
    return Answer(_decorate(s, corpus, segs, lang), {"ok": chk.ok, "issues": chk.issues, "rejected": issues, **chk.stats},
                  "fallback", tin, tout, rejections, raw_attempts=attempts)


def call_model(settings, messages: list[dict]) -> tuple[str, int, int]:
    """One completion from the configured provider. Returns (text, input tokens, output tokens)."""
    if settings.chat_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.chat_key)
        resp = client.messages.create(model=settings.chat_model, max_tokens=settings.chat_max_tokens,
                                      system=SYSTEM, messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, resp.usage.input_tokens, resp.usage.output_tokens
    import httpx
    payload = {"model": settings.chat_model, "max_tokens": settings.chat_max_tokens,
               "messages": [{"role": "system", "content": SYSTEM}] + messages,
               "response_format": {"type": "json_object"}}
    import time
    for attempt in range(4):
        r = httpx.post(settings.chat_base_url.rstrip("/") + "/chat/completions", json=payload, timeout=180,
                       headers={"Authorization": f"Bearer {settings.chat_key}"})
        if r.status_code == 200:
            break
        log.warning("provider returned %s: %s", r.status_code, r.text[:300])
        if attempt == 3:
            r.raise_for_status()
        time.sleep(2 * (attempt + 1))
    data = r.json()
    usage = data.get("usage") or {}
    return (data["choices"][0]["message"].get("content") or "", usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0))


def _fallback(corpus: Corpus, question: str, lang: str, event: str | None, factual: bool) -> list[dict]:
    segs = [{"tipo": "esclarecimento", "texto": t("chat_fallback", lang)}]
    hits = corpus.index.search(question, k=6, event=event, allow={"claim"})
    if not hits:
        return [{"tipo": "sem_informacao", "texto": t("chat_no_info", lang)}]
    for _, d in hits[:3]:
        c = d.claim_ids[0]
        segs.append({"tipo": "fato", "texto": corpus.claims[c]["texts"][lang], "claim_ids": [c]})
    return segs


def handle(s: Session, question: str, lang: str, numero: int | None, event: str | None, factual: bool,
           session_id: str | None) -> tuple[str | None, Answer | None]:
    corpus = corpus_for(s, numero, get_settings().country_code)
    if corpus is None:
        return None, None
    if session_id:
        row = s.get(m.ChatSession, session_id)
        if row is None or row.edition_id != corpus.edition_id:
            session_id = None
    if not session_id:
        session_id = new_session(s, corpus.edition_id, lang, factual)
    hist = history(s, session_id)
    ans = answer(s, corpus, question[:800], lang, event if event in corpus.events else None, factual, hist)
    save_turn(s, session_id, question[:800], ans.segments, ans.check, ans.tokens_in, ans.tokens_out)
    record_usage(s, ans.tokens_in, ans.tokens_out, ans.rejections, ans.negative)
    if ans.suggestion:
        s.add(m.ChatSuggestion(edition_id=corpus.edition_id, texto=ans.suggestion[:1000]))
    return session_id, ans
