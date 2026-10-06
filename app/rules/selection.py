"""Claim selection rule (architecture doc, section 2):

A claim enters the chronicle as a plain fact if it is affirmed by outlets of
at least two poles of the active axis, or comes from a verifiable primary
source. Otherwise it enters attributed ("segundo X"). Claims whose support is
only contradicted are excluded. Disputed figures are never averaged: each
source keeps its own claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SupportView:
    pole_slug: str | None  # None for official sources / outlets without a position on the axis
    postura: str  # afirma / contradice / matiza


@dataclass
class ClaimView:
    codigo: str
    supports: list[SupportView] = field(default_factory=list)
    fuente_primaria_verificada: bool = False


@dataclass
class Decision:
    modo: str  # llano / atribuido / excluido
    razon: str
    polos_que_afirman: list[str]


def decide(claim: ClaimView) -> Decision:
    affirming = sorted({s.pole_slug for s in claim.supports if s.postura == "afirma" and s.pole_slug})
    contradicting = {s.pole_slug for s in claim.supports if s.postura == "contradice" and s.pole_slug}
    if claim.fuente_primaria_verificada:
        return Decision("llano", "fuente primaria verificable", affirming)
    if len(affirming) >= 2:
        return Decision("llano", f"respaldo en {len(affirming)} polos del eje activo", affirming)
    if not affirming and not any(s.postura == "afirma" for s in claim.supports):
        return Decision("excluido", "sin respaldo afirmativo", affirming)
    why = "respaldo en un solo polo" if affirming else "respaldo sin polo asignado"
    if contradicting:
        why += "; contradicha por otro polo"
    return Decision("atribuido", why, affirming)
