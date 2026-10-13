"""Code gates for agent-extracted claims (step 3). The model proposes; these
functions decide what can enter the claim table at all."""
from __future__ import annotations

import re
import unicodedata

from .language import numbers_in
from .loaded_terms import Term, violations

TIPOS = {"quien", "que", "cuando", "donde", "cifra", "cita"}
POSTURAS = {"afirma", "contradice", "matiza"}
MIN_FRAGMENT_CHARS = 15
MAX_CLAIM_CHARS = 260

_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"', "»": '"', "‘": "'", "’": "'", "´": "'", "`": "'",
                         "–": "-", "—": "-", " ": " "})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").translate(_QUOTES)).casefold()
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(" .;:,!?\"'")


def fragment_in_source(fragment: str, *sources: str | None) -> bool:
    """The support fragment must be a verbatim passage of the outlet's own
    headline or feed summary (after normalising quotes, case and spacing)."""
    f = norm(fragment)
    if len(f) < MIN_FRAGMENT_CHARS:
        return False
    return any(src and f in norm(src) for src in sources)


def unsupported_numbers(text: str, fragments: list[str], lang: str = "pt") -> list[float]:
    """Numbers in the claim that appear in none of its supporting fragments."""
    allowed: set[float] = set()
    for f in fragments:
        allowed |= numbers_in(f, lang)
    return sorted(n for n in numbers_in(text, lang) if not any(abs(n - a) < 1e-9 for a in allowed))


def claim_problems(c: dict, terms: list[Term], lang: str = "pt") -> list[str]:
    """Structural problems that reject the whole claim."""
    out = []
    texto = (c.get("texto") or "").strip()
    if not texto:
        out.append("texto vazio")
    elif len(texto) > MAX_CLAIM_CHARS:
        out.append("texto longo demais para uma afirmação atômica")
    if c.get("tipo") not in TIPOS:
        out.append(f"tipo inválido: {c.get('tipo')}")
    if c.get("tipo") == "cifra" and (c.get("valor") is None or not c.get("medida")):
        out.append("cifra sem valor ou medida")
    for h in violations(texto, terms, lang):
        out.append(f"termo carregado sem atribuição: {h.termino}")
    return out
