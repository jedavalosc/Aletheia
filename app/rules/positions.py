"""Outlet positions from headline annotations (step 5). Pure functions, no database.

Unit: an article (headline + feed summary) about an event several outlets covered.
Annotation: -2..+2 on an axis (negative = towards the axis's first pole), or None when the
text does not bear on the axis. Two independent model annotators; the editor codes a sample.

Position of an outlet = mean deviation of its articles from the other outlets' framing of the
SAME event (event fixed effects), rescaled to [-1, 1]. This separates framing from agenda: an
outlet is not placed on a side because the week's news favoured that side. Zero is therefore
the average of the monitored outlets, not an absolute neutral point (D57).

Interval: cluster bootstrap over events; in each replicate every article takes one annotator's
value at random, so disagreement between annotators widens the interval.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field

MIN_ARTICLES = 15   # outlets with fewer annotated articles get no estimate
MIN_EVENT_OUTLETS = 3  # an event contributes only if at least 3 outlets framed it
ALPHA_GATE = 0.667  # Krippendorff: below this, model coding is not reliable enough to publish


def krippendorff_alpha_interval(units: list[list[float | None]]) -> float | None:
    """Krippendorff's alpha, interval metric. units: one list of codes per unit (None = missing).
    Units with fewer than two codes are ignored. Returns None when it cannot be computed."""
    vals = [[v for v in u if v is not None] for u in units]
    vals = [u for u in vals if len(u) >= 2]
    if not vals:
        return None
    n = sum(len(u) for u in vals)
    do_num = 0.0
    for u in vals:
        m_u = len(u)
        do_num += sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j) / (m_u - 1)
    do = do_num / n
    pooled = [v for u in vals for v in u]
    de = sum((a - b) ** 2 for i, a in enumerate(pooled) for j, b in enumerate(pooled) if i != j) / (n * (n - 1))
    if de == 0:
        return 1.0 if do == 0 else None
    return 1 - do / de


@dataclass
class Item:
    article_id: int
    outlet_id: int
    event_id: int
    codes: list[float] = field(default_factory=list)  # one per annotator that gave a value


@dataclass
class Estimate:
    outlet_id: int
    score: float
    lo: float
    hi: float
    n_articles: int
    n_events: int


def _scores(items: list[Item], pick) -> dict[int, list[float]]:
    by_event: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for it in items:
        v = pick(it)
        if v is not None:
            by_event[it.event_id].append((it.outlet_id, v))
    dev: dict[int, list[float]] = defaultdict(list)
    for rows in by_event.values():
        if len({o for o, _ in rows}) < MIN_EVENT_OUTLETS:
            continue
        for k, (o, v) in enumerate(rows):
            others = [w for j, (o2, w) in enumerate(rows) if j != k and o2 != o]
            if others:
                dev[o].append(v - sum(others) / len(others))
    return dev


def _rescale(x: float) -> float:
    return max(-1.0, min(1.0, x / 2.0))  # deviations live in [-4, 4]; ±2 is already extreme


def estimate(items: list[Item], reps: int = 1000, seed: int = 7) -> list[Estimate]:
    """Point estimate from the annotators' mean; 95% percentile interval from the bootstrap."""
    items = [it for it in items if it.codes]
    point = _scores(items, lambda it: sum(it.codes) / len(it.codes))
    rng = random.Random(seed)
    events = sorted({it.event_id for it in items})
    by_event = defaultdict(list)
    for it in items:
        by_event[it.event_id].append(it)
    boots: dict[int, list[float]] = defaultdict(list)
    for _ in range(reps):
        sample = []
        for k, e in enumerate(rng.choice(events) for _ in events):
            # A resampled event keeps its own identity per draw so duplicates stay separate events.
            sample += [Item(it.article_id, it.outlet_id, e * 10_000 + k, it.codes) for it in by_event[e]]
        for o, d in _scores(sample, lambda it: rng.choice(it.codes)).items():
            boots[o].append(sum(d) / len(d))
    out = []
    for o, d in point.items():
        if len(d) < MIN_ARTICLES or len(boots[o]) < reps * 0.5:
            continue
        b = sorted(boots[o])
        lo, hi = b[int(0.025 * len(b))], b[min(len(b) - 1, int(0.975 * len(b)))]
        sc = _rescale(sum(d) / len(d))
        lo, hi = min(_rescale(lo), sc), max(_rescale(hi), sc)
        n_ev = len({it.event_id for it in items if it.outlet_id == o})
        out.append(Estimate(o, round(sc, 3), round(lo, 3), round(hi, 3), len(d), n_ev))
    return sorted(out, key=lambda e: e.score)
