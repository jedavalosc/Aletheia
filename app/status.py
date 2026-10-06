from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .editorial import edition_gates


def status(s: Session) -> list[dict]:
    out = []
    for ed in s.scalars(select(m.Edition).order_by(m.Edition.numero)):
        evs = []
        for ee in ed.events:
            ev = ee.event
            brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id)).first()
            flags = s.scalars(select(m.BlindspotFlag).where(m.BlindspotFlag.event_id == ev.id)).all()
            claims = s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id)).all()
            vis = s.scalars(select(m.Visual).where(m.Visual.event_id == ev.id)).all()
            evs.append({
                "slug": ev.slug, "impacto": ev.impacto,
                "cronica": brief.estado if brief else None,
                "verificacion": {k: (v["ok"], v["issues"]) for k, v in (brief.verificacion or {}).items()} if brief else None,
                "claims": {c.codigo: c.modo for c in claims},
                "banderas": [(s.get(m.Pole, f.pole_id).slug, f.subject, round(f.diferencia_cobertura, 2)) for f in flags],
                "visuales": [(v.tipo, v.nivel, v.estado) for v in vis],
            })
        out.append({"edicion": ed.numero, "estado": ed.estado, "demo": ed.es_demo, "eventos": evs,
                    "bloqueos_aprobacion": edition_gates(s, ed) if ed.estado != "publicada" else []})
    return out
