"""Language helpers shared by the verifiers: attribution markers, quotes,
certainty formulas and figure extraction, for PT, ES and EN."""
from __future__ import annotations

import re

ATTRIBUTION = {
    "pt": [r"segundo", r"de acordo com", r"conforme", r"disse", r"disseram", r"afirmou", r"afirmaram",
           r"informou", r"informaram", r"relatou", r"relataram", r"registrou", r"estimou", r"declarou",
           r"declararam", r"argumentou", r"argumentam", r"sustentou", r"sustentam", r"reportou", r"reportaram",
           r"denunciou", r"acusou", r"admitiu", r"na avaliação de", r"contabilizou", r"indicou", r"apontou", r"calculou"],
    "es": [r"según", r"de acuerdo con", r"conforme a", r"dijo", r"dijeron", r"afirmó", r"afirmaron",
           r"informó", r"informaron", r"relató", r"registró", r"estimó", r"declaró", r"declararon",
           r"argumentó", r"sostuvo", r"sostienen", r"reportó", r"reportaron", r"denunció", r"acusó", r"admitió",
           r"contabilizó", r"indicó", r"señaló", r"calculó"],
    "en": [r"according to", r"said", r"says", r"stated", r"reported", r"estimated", r"declared",
           r"argued", r"argue", r"contended", r"maintain", r"recorded", r"denounced", r"accused", r"admitted",
           r"found", r"counted", r"calculated"],
}

# Verbs that carry meaning: allowed only when they describe the act exactly.
CHARGED_ATTRIBUTIVE = {"pt": ["denunciou", "acusou", "admitiu"], "es": ["denunció", "acusó", "admitió"],
                       "en": ["denounced", "accused", "admitted"]}

CERTAINTY_FORMULAS = {
    "pt": [r"é evidente que", r"sem dúvida", r"tudo indica", r"está claro que", r"obviamente", r"certamente"],
    "es": [r"es evidente que", r"sin duda", r"todo indica", r"está claro que", r"obviamente", r"ciertamente"],
    "en": [r"it is evident that", r"without (?:a )?doubt", r"everything indicates", r"clearly", r"obviously", r"certainly"],
}

_QUOTE_RE = re.compile(r"[\"“”«»]([^\"“”«»]{1,400})[\"“”«»]")
# pt/es: 21.500 / 21 500 thousands, 3,5 decimal. en: 21,500 thousands, 3.5 decimal.
_NUM_RE = {
    "latin": re.compile(r"(?<![\w.,])(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,(\d+))?(?![\w])"),
    "en": re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\w])"),
}


def has_attribution(text: str, lang: str) -> bool:
    low = text.lower()
    return any(re.search(r"(?<!\w)" + p + r"(?!\w)", low) for p in ATTRIBUTION.get(lang, []) + ATTRIBUTION["pt"])


def quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTE_RE.finditer(text)]


def certainty_hits(text: str, lang: str) -> list[str]:
    low = text.lower()
    return [p for p in CERTAINTY_FORMULAS.get(lang, []) if re.search(r"(?<!\w)" + p + r"(?!\w)", low)]


def numbers_in(text: str, lang: str = "pt") -> set[float]:
    """Extract numeric values using the number conventions of the language."""
    out: set[float] = set()
    style = "en" if lang == "en" else "latin"
    for mt in _NUM_RE[style].finditer(text):
        whole, dec = mt.group(1), mt.group(2)
        digits = re.sub(r"[.,\s]", "", whole)
        try:
            out.add(float(digits + ("." + dec if dec else "")))
        except ValueError:
            continue
    return out
