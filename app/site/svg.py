"""Static SVG templates for the four standard pieces. Each SVG embeds its
title, finding (desc), source, cutoff date and denominator, so a screenshot
shared outside the site stays verifiable. Bars start at zero. Color is never
the only channel: every bar carries its written label."""
from __future__ import annotations

from html import escape

W = 640
FONT = "Inter, 'IBM Plex Sans', system-ui, sans-serif"
INK, MUTED, TRACK, BG = "#1E1D1A", "#55524B", "#E6E2DA", "#FBFAF7"


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _text_lines(x: int, y: int, lines: list[str], size: int, color: str, weight: int = 400, lh: float = 1.35) -> tuple[str, int]:
    out = []
    for ln in lines:
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(ln)}</text>')
        y += int(size * lh)
    return "".join(out), y


def _frame(body: str, height: int, title: str, alt: str, uid: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="100%" role="img" '
            f'aria-labelledby="{uid}-t {uid}-d" font-family="{FONT}">'
            f'<title id="{uid}-t">{escape(title)}</title><desc id="{uid}-d">{escape(alt)}</desc>'
            f'<rect width="{W}" height="{height}" fill="{BG}"/>{body}</svg>')


def _header(texts: dict) -> tuple[str, int]:
    parts, y = [], 30
    t, y = _text_lines(16, y, _wrap(texts["title"], 62), 17, INK, 600)
    parts.append(t)
    if texts.get("note"):
        t, y = _text_lines(16, y + 2, _wrap(texts["note"], 84), 12, MUTED)
        parts.append(t)
    return "".join(parts), y + 8


def _footer(texts: dict, y: int) -> tuple[str, int]:
    y += 10
    parts = [f'<line x1="16" x2="{W - 16}" y1="{y - 12}" y2="{y - 12}" stroke="{TRACK}"/>']
    for ln in texts["footer"]:
        t, y = _text_lines(16, y, _wrap(ln, 96), 11, MUTED)
        parts.append(t)
    return "".join(parts), y + 6


def bars(texts: dict, rows: list[dict], uid: str) -> str:
    """rows: [{label, value(0-1), right_text, color}] — horizontal bars from zero."""
    head, y = _header(texts)
    body = [head]
    x0, bw = 16, W - 32
    for r in rows:
        t, y = _text_lines(x0, y + 4, [r["label"]], 13, INK, 600)
        body.append(t)
        body.append(f'<rect x="{x0}" y="{y - 6}" width="{bw}" height="18" fill="{TRACK}" rx="2"/>')
        fill_w = max(0.0, min(1.0, r["value"])) * bw
        body.append(f'<rect x="{x0}" y="{y - 6}" width="{fill_w:.1f}" height="18" fill="{r["color"]}" rx="2"/>')
        body.append(f'<text x="{x0}" y="{y + 30}" font-size="13" fill="{INK}">{escape(r["right_text"])}</text>')
        y += 54
    # zero and 100% ticks
    body.append(f'<text x="{x0}" y="{y}" font-size="10" fill="{MUTED}">0%</text>')
    body.append(f'<text x="{x0 + bw}" y="{y}" font-size="10" fill="{MUTED}" text-anchor="end">100%</text>')
    foot, y = _footer(texts, y + 26)
    body.append(foot)
    return _frame("".join(body), y, texts["title"], texts["alt"], uid)


def points(texts: dict, pts: list[dict], max_value: float, uid: str, color: str = "#3F3D38") -> str:
    """pts: [{label, value, value_text}] — one dot per source on a common axis from zero."""
    head, y = _header(texts)
    body = [head]
    x0, bw = 16, W - 32
    top = max_value * 1.15 or 1
    for p in pts:
        t, y = _text_lines(x0, y + 4, _wrap(p["label"], 80), 12, INK, 600)
        body.append(t)
        cy = y - 2
        body.append(f'<line x1="{x0}" x2="{x0 + bw}" y1="{cy}" y2="{cy}" stroke="{TRACK}" stroke-width="2"/>')
        cx = x0 + p["value"] / top * bw
        body.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="7" fill="{color}"/>')
        anchor = "end" if cx > W - 120 else "start"
        dx = -12 if anchor == "end" else 12
        body.append(f'<text x="{cx + dx:.1f}" y="{cy + 4}" font-size="13" fill="{INK}" text-anchor="{anchor}" font-weight="600">{escape(p["value_text"])}</text>')
        y += 30
    body.append(f'<text x="{x0}" y="{y}" font-size="10" fill="{MUTED}">0</text>')
    foot, y = _footer(texts, y + 26)
    body.append(foot)
    return _frame("".join(body), y, texts["title"], texts["alt"], uid)


def series(texts: dict, data: list[dict], current: int, uid: str, current_label: str = "") -> str:
    """data: [{ano, decretos}] — vertical bars from zero; the current year outlined and labelled."""
    head, y = _header(texts)
    body = [head]
    x0, bw = 40, W - 56
    h = 120
    top = max(d["decretos"] for d in data) or 1
    n = len(data)
    slot = bw / n
    base = y + h + 10
    body.append(f'<line x1="{x0}" x2="{x0 + bw}" y1="{base}" y2="{base}" stroke="{MUTED}"/>')
    body.append(f'<text x="{x0 - 8}" y="{base + 4}" font-size="10" fill="{MUTED}" text-anchor="end">0</text>')
    body.append(f'<text x="{x0 - 8}" y="{base - h + 4}" font-size="10" fill="{MUTED}" text-anchor="end">{top}</text>')
    for i, d in enumerate(data):
        bh = d["decretos"] / top * h
        x = x0 + i * slot + slot * 0.2
        w = slot * 0.6
        if d["ano"] == current:
            body.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{w:.1f}" height="{bh:.1f}" fill="none" stroke="{INK}" stroke-width="2"/>')
        else:
            body.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{w:.1f}" height="{bh:.1f}" fill="#6F6A60"/>')
        body.append(f'<text x="{x + w / 2:.1f}" y="{base + 16}" font-size="10" fill="{INK}" text-anchor="middle">{d["ano"]}</text>')
        if d["ano"] == current and current_label:
            body.append(f'<text x="{x + w / 2:.1f}" y="{base + 29}" font-size="10" fill="{INK}" text-anchor="middle" font-weight="600">({escape(current_label)})</text>')
    foot, y = _footer(texts, base + 52)
    body.append(foot)
    return _frame("".join(body), y, texts["title"], texts["alt"], uid)
