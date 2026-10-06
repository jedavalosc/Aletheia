"""Automatic checks for visual pieces (design doc, s.6) and for the country
theme (visual style guide). Checks structure; humans review meaning."""
from __future__ import annotations

import math
import re

from .loaded_terms import Term, violations


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(hex_: str) -> float:
    r, g, b = (_srgb_to_linear(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lab(hex_: str) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in _rgb(hex_))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """CIE76 distance. Simple and conservative enough for an exclusion gate."""
    return math.dist(lab(a), lab(b))


def chroma(hex_: str) -> float:
    _, a, b = lab(hex_)
    return math.hypot(a, b)


MIN_DELTA_E_EXCLUSION = 20.0
MIN_NONTEXT_CONTRAST = 3.0  # WCAG 2.1 SC 1.4.11
MAX_STATIC_BYTES = 150 * 1024
MAX_WORDS = 40


def verify_visual(spec: dict, marks: list[dict], texts: dict[str, dict], palette: dict[str, str],
                  background: str, terms_by_lang: dict[str, list[Term]], static_bytes: dict[str, int] | None = None) -> list[str]:
    """texts: {lang: {title, alt, footer}}; marks: [{claim_ids, dataset_id, coverage_snapshot_id, denominador}]"""
    issues: list[str] = []
    for i, mk in enumerate(marks):
        if not (mk.get("claim_ids") or mk.get("dataset_id") or mk.get("coverage_snapshot_id")):
            issues.append(f"marca {i} sem claim, dataset ou snapshot")
        if spec.get("tipo") in ("cobertura", "puntociego") and not mk.get("denominador"):
            issues.append(f"marca {i} sem denominador escrito")
    if spec.get("forma") in ("barras", "barras_espejo") and spec.get("origen", 0) != 0:
        issues.append("barras devem começar em zero")
    for pole, col in palette.items():
        if contrast(col, background) < MIN_NONTEXT_CONTRAST:
            issues.append(f"cor do polo {pole} com contraste < 3:1")
    cols = list(palette.values())
    if len(cols) == 2:
        la, lb = lab(cols[0])[0], lab(cols[1])[0]
        if abs(la - lb) > 6 or abs(chroma(cols[0]) - chroma(cols[1])) > 8:
            issues.append("cores dos polos sem luminosidade e saturação equivalentes")
    for lang, tx in texts.items():
        alt = tx.get("alt", "")
        if not alt or re.match(r"(?i)^(gráfico|gráfica|chart|graph|imagem|image)\b", alt):
            issues.append(f"[{lang}] texto alternativo deve dizer o achado, não a forma")
        for field in ("title", "alt"):
            for h in violations(tx.get(field, ""), terms_by_lang.get(lang, []), lang):
                issues.append(f"[{lang}] termo carregado em {field}: {h.termino}")
        if not tx.get("footer"):
            issues.append(f"[{lang}] rodapé com fonte, data de corte e denominador ausente")
        # Fixed notes and labels do not count (design doc: "sin contar etiquetas").
        if len(re.findall(r"\w+", tx.get("title", ""))) > MAX_WORDS:
            issues.append(f"[{lang}] mais de {MAX_WORDS} palavras na peça")
    for lang, n in (static_bytes or {}).items():
        if n > MAX_STATIC_BYTES:
            issues.append(f"[{lang}] versão estática com {n} bytes > 150 KB")
    return issues


def verify_theme_colors(brand: str, derived: list[str], excluded: list[str], poles: list[str], background: str) -> list[str]:
    issues = []
    for c in [brand] + derived:
        for x in excluded:
            if delta_e(c, x) < MIN_DELTA_E_EXCLUSION:
                issues.append(f"{c} muito próximo da cor excluída {x} (ΔE {delta_e(c, x):.1f})")
        for p in poles:
            if delta_e(c, p) < MIN_DELTA_E_EXCLUSION:
                issues.append(f"{c} muito próximo da cor de polo {p}")
        if contrast(c, background) < 4.5:
            issues.append(f"{c} sem contraste 4.5:1 sobre o fundo para texto")
    return issues
