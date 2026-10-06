"""Loaded-term detector. The list lives in the database (table loaded_term)
and is editable from the editorial panel; this module only applies it."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .language import has_attribution, quoted_spans


@dataclass(frozen=True)
class Term:
    termino: str
    patron: str
    idioma: str
    permitido_si: str = "atribuido_o_cita"  # or "cita" (quote only) or "tipificacion_legal_atribuida"
    alternativa: str | None = None


@dataclass
class TermHit:
    termino: str
    start: int
    end: int
    permitido: bool
    motivo: str


def _compiled(term: Term):
    return re.compile(r"(?<!\w)(?:" + term.patron + r")(?!\w)", re.IGNORECASE)


def scan(text: str, terms: list[Term], lang: str) -> list[TermHit]:
    """Return every loaded-term occurrence and whether its context allows it."""
    hits: list[TermHit] = []
    quotes = quoted_spans(text)
    attributed = has_attribution(text, lang)
    for t in terms:
        if t.idioma != lang:
            continue
        for m in _compiled(t).finditer(text):
            in_quote = any(a <= m.start() and m.end() <= b for a, b in quotes)
            if in_quote:
                hits.append(TermHit(t.termino, m.start(), m.end(), True, "cita_textual"))
            elif t.permitido_si == "cita":
                hits.append(TermHit(t.termino, m.start(), m.end(), False, "solo_en_cita"))
            elif attributed:
                hits.append(TermHit(t.termino, m.start(), m.end(), True, "atribuido"))
            else:
                hits.append(TermHit(t.termino, m.start(), m.end(), False, "sin_atribucion"))
    return hits


def violations(text: str, terms: list[Term], lang: str) -> list[TermHit]:
    return [h for h in scan(text, terms, lang) if not h.permitido]


def highlight(text: str, terms: list[Term], lang: str) -> list[tuple[str, bool]]:
    """Split a headline into (chunk, is_loaded) for the triptych view."""
    spans = sorted({(h.start, h.end) for h in scan(text, terms, lang)})
    out, pos = [], 0
    for a, b in spans:
        if a < pos:
            continue
        if a > pos:
            out.append((text[pos:a], False))
        out.append((text[a:b], True))
        pos = b
    if pos < len(text):
        out.append((text[pos:], False))
    return out
