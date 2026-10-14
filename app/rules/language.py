"""Language helpers shared by the verifiers: attribution markers, quotes,
certainty formulas and figure extraction, for PT, ES and EN."""
from __future__ import annotations

import re

ATTRIBUTION = {
    "pt": [r"segundo", r"de acordo com", r"conforme", r"disse", r"disseram", r"afirmou", r"afirmaram",
           r"informou", r"informaram", r"relatou", r"relataram", r"registrou", r"estimou", r"declarou",
           r"declararam", r"argumentou", r"argumentam", r"sustentou", r"sustentam", r"reportou", r"reportaram",
           r"denunciou", r"acusou", r"admitiu", r"na avaliação de", r"contabilizou", r"indicou", r"apontou", r"calculou",
           # present tense, used in headlines and for ongoing statements
           r"diz", r"dizem", r"afirma", r"afirmam", r"informa", r"informam", r"declara", r"declaram", r"relata",
           r"relatam", r"registra", r"estima", r"estimam", r"aponta", r"apontam", r"indica", r"indicam", r"acusa",
           r"dizem veículos", r"segundo veículos", r"avalia", r"avaliou", r"avaliam", r"avaliaram",
           r"ouvido pelo", r"ouvida pelo", r"ouvidos pelo", r"ouvido pela", r"ouvida pela"],
    "es": [r"según", r"de acuerdo con", r"conforme a", r"dijo", r"dijeron", r"afirmó", r"afirmaron",
           r"informó", r"informaron", r"relató", r"registró", r"estimó", r"declaró", r"declararon",
           r"argumentó", r"sostuvo", r"sostienen", r"reportó", r"reportaron", r"denunció", r"acusó", r"admitió",
           r"contabilizó", r"indicó", r"señaló", r"calculó",
           r"dice", r"dicen", r"afirma", r"afirman", r"informa", r"informan", r"declara", r"estima", r"señala",
           r"indica", r"acusa", r"evalúa", r"evaluó", r"consultado por"],
    "en": [r"according to", r"said", r"says", r"stated", r"reported", r"estimated", r"declared",
           r"argued", r"argue", r"contended", r"maintain", r"recorded", r"denounced", r"accused", r"admitted",
           r"found", r"counted", r"calculated",
           r"reports", r"estimates", r"accuses", r"states", r"assessed", r"assesses",
           r"interviewed by"],
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


def allowed_numbers(text: str, lang: str = "pt") -> set[float]:
    """Numbers a translation or paraphrase of `text` may contain: the parsed values, plus digit runs
    glued to units or ordinals (6h, 1º, 3ª) and the 12-hour form of 24-hour times (22h -> 10 p.m.)."""
    out = set(numbers_in(text, lang))
    for mt in re.finditer(r"\d+", text):
        out.add(float(mt.group(0)))
    for mt in re.finditer(r"(?<!\d)(\d{1,2})\s?h", text):
        h = int(mt.group(1))
        if 13 <= h <= 23:
            out.add(float(h - 12))
    return out


# Attributive verbs the style guide rules out (they suggest falsehood, secrecy or aggression). Outside quotes only.
DISCOURAGED_VERBS = {
    "pt": ["alegou", "alegaram", "alega", "alegam", "revelou", "revelaram", "disparou", "rebateu", "rebateram",
           "atacou", "atacaram", "detonou", "confessou", "confessaram"],
    "es": ["alegó", "alegaron", "reveló", "revelaron", "disparó", "arremetió", "fustigó", "atacó", "confesó"],
    "en": ["claimed", "claims", "slammed", "blasted", "lashed out", "revealed", "confessed"],
}


def discouraged_verbs(text: str, lang: str) -> list[str]:
    spans = quoted_spans(text)
    low = text.lower()
    hits = []
    for v in DISCOURAGED_VERBS.get(lang, []):
        for mt in re.finditer(r"(?<!\w)" + re.escape(v) + r"(?!\w)", low):
            if not any(a <= mt.start() < b for a, b in spans):
                hits.append(v)
                break
    return hits
