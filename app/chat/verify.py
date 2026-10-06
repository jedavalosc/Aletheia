"""Verifier for chat answers. An answer reaches the reader only if every
segment passes. Segment types:

  fato            facts from the chronicle; must cite existing claim_ids of the
                  edition; every number in the text must appear in a cited claim;
                  same sentence rules as the chronicle (loaded terms, attribution,
                  disputed figures by source).
  cobertura       coverage/blind-spot data; must cite cobertura:/ponto_cego:/visual:
                  documents; every number must appear in a cited document.
  interpretacao   academic statement; must cite academico:/pergunta_aberta:
                  documents; forbidden in Pure Factual Mode. The scholar's name and
                  epistemic status are attached by the server from the database.
  metodologia     must cite metodo:/edicao documents.
  sem_informacao  "the edition does not contain this"; the server appends the cutoff.
  esclarecimento  short connective text: no digits, at most two sentences, no
                  loaded terms. It cannot carry facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..rules.language import numbers_in
from ..rules.loaded_terms import Term, violations
from ..rules.verifier import ClaimRef, verify_sentence
from .corpus import Corpus

TYPES = {"fato", "cobertura", "interpretacao", "metodologia", "sem_informacao", "esclarecimento"}
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý“\"(])")


@dataclass
class ChatCheck:
    ok: bool
    issues: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def sentences(text: str) -> list[str]:
    return [p for p in _SENT_SPLIT.split(text.strip()) if p]


def _doc_numbers(corpus: Corpus, ids: list[str]) -> set[float]:
    nums: set[float] = set()
    for i in ids:
        d = corpus.docs.get(i)
        if d:
            for lang, txt in d.text.items():
                nums |= numbers_in(txt, lang)
    return nums


def _claim_numbers(corpus: Corpus, cids: list[str]) -> set[float]:
    nums: set[float] = set()
    for c in cids:
        info = corpus.claims.get(c)
        if info:
            for lang, txt in info["texts"].items():
                nums |= numbers_in(txt, lang)
            if info["valor"] is not None:
                nums.add(float(info["valor"]))
    return nums


def verify_answer(corpus: Corpus, segments: list[dict], terms: list[Term], lang: str, factual_mode: bool) -> ChatCheck:
    issues: list[str] = []
    refs = {k: ClaimRef(k, v["event_id"], v["modo"], v["medida"], v["valor"]) for k, v in corpus.claims.items()}
    n_fact_sent = n_fact_cited = 0
    if not segments:
        issues.append("resposta vazia")
    for i, seg in enumerate(segments):
        tipo, text = seg.get("tipo"), (seg.get("texto") or "").strip()
        cids = [c for c in (seg.get("claim_ids") or []) if isinstance(c, str)]
        drefs = [r for r in (seg.get("refs") or []) if isinstance(r, str)]
        if tipo not in TYPES:
            issues.append(f"[{i}] tipo desconhecido: {tipo}")
            continue
        if not text:
            issues.append(f"[{i}] segmento vazio")
            continue
        for h in violations(text, terms, lang):
            issues.append(f"[{i}] termo carregado sem atribuição: {h.termino}")
        if tipo == "fato":
            sents = sentences(text)
            n_fact_sent += len(sents)
            if not cids:
                issues.append(f"[{i}] fato sem claim_ids")
                continue
            bad = [c for c in cids if c not in corpus.claims]
            if bad:
                issues.append(f"[{i}] claim_ids inexistentes na edição: {bad}")
                continue
            n_fact_cited += len(sents)
            allowed = _claim_numbers(corpus, cids)
            for n in numbers_in(text, lang):
                if not any(abs(n - a) < 1e-6 for a in allowed):
                    issues.append(f"[{i}] cifra {n:g} não aparece nas afirmações citadas")
            for st in sents:
                for iss in verify_sentence(i, st, cids, None, refs, terms, lang):
                    if iss.codigo == "cifra_colapsada" and len(sents) > 1:
                        continue  # checked on the whole segment below
                    issues.append(f"[{i}] {iss.detalle}")
            if len(sents) > 1:
                for iss in verify_sentence(i, text, cids, None, refs, terms, lang):
                    if iss.codigo == "cifra_colapsada":
                        issues.append(f"[{i}] {iss.detalle}")
        elif tipo == "cobertura":
            ok_refs = [r for r in drefs if r in corpus.docs and corpus.docs[r].tipo in ("cobertura", "ponto_cego", "visual")]
            if not ok_refs:
                issues.append(f"[{i}] cobertura sem documento de cobertura citado")
                continue
            allowed = _doc_numbers(corpus, ok_refs)
            for n in numbers_in(text, lang):
                if not any(abs(n - a) < 1e-6 for a in allowed):
                    issues.append(f"[{i}] cifra {n:g} não aparece nos dados de cobertura citados")
        elif tipo == "interpretacao":
            if factual_mode:
                issues.append(f"[{i}] interpretação acadêmica no Modo Factual Puro")
            ok_refs = [r for r in drefs if r in corpus.docs and corpus.docs[r].tipo in ("academico", "pergunta_aberta")]
            if not ok_refs:
                issues.append(f"[{i}] interpretação sem enunciado acadêmico citado")
            bad = [c for c in cids if c not in corpus.claims]
            if bad:
                issues.append(f"[{i}] claim_ids inexistentes: {bad}")
            allowed = _doc_numbers(corpus, ok_refs) | _claim_numbers(corpus, cids)
            for n in numbers_in(text, lang):
                if not any(abs(n - a) < 1e-6 for a in allowed):
                    issues.append(f"[{i}] cifra {n:g} não aparece no enunciado citado")
        elif tipo == "metodologia":
            ok_refs = [r for r in drefs if r in corpus.docs and corpus.docs[r].tipo in ("metodo", "edicao")]
            if not ok_refs:
                issues.append(f"[{i}] metodologia sem documento citado")
            allowed = _doc_numbers(corpus, ok_refs)
            for n in numbers_in(text, lang):
                if not any(abs(n - a) < 1e-6 for a in allowed):
                    issues.append(f"[{i}] cifra {n:g} não aparece na metodologia citada")
        elif tipo == "esclarecimento":
            if re.search(r"\d", text):
                issues.append(f"[{i}] esclarecimento com cifras (fatos exigem segmento 'fato')")
            if len(sentences(text)) > 2 or len(text) > 320:
                issues.append(f"[{i}] esclarecimento longo demais")
            if cids:
                issues.append(f"[{i}] esclarecimento não cita claims; use 'fato'")
        elif tipo == "sem_informacao":
            if len(text) > 400:
                issues.append(f"[{i}] sem_informacao longo demais")
            if re.search(r"\d", text) and not cids:
                issues.append(f"[{i}] sem_informacao com cifras")
    return ChatCheck(ok=not issues, issues=issues,
                     stats={"factual_sentences": n_fact_sent, "factual_sentences_cited": n_fact_cited})
