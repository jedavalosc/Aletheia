"""Sentence-by-sentence verifier for the chronicle and its translations.

Rejects:
  * any sentence without claim_ids;
  * any claim_id that does not exist (or belongs to another event);
  * any loaded term without attribution or quotation;
  * a sentence that cites an attributed claim without an attribution marker;
  * a sentence citing several sources of one disputed figure but not giving
    each source's value (i.e. averaging or collapsing them);
  * a sentence citing an excluded claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .language import has_attribution, numbers_in
from .loaded_terms import Term, violations


@dataclass
class ClaimRef:
    codigo: str
    event_id: int
    modo: str | None
    medida: str | None = None
    valor: float | None = None


@dataclass
class SentenceIssue:
    orden: int
    codigo: str
    detalle: str


@dataclass
class VerificationResult:
    ok: bool
    issues: list[SentenceIssue] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "issues": [i.__dict__ for i in self.issues]}


def verify_sentence(orden: int, texto: str, claim_ids: list[str], event_id: int | None,
                    claims: dict[str, ClaimRef], terms: list[Term], lang: str) -> list[SentenceIssue]:
    issues: list[SentenceIssue] = []
    if not claim_ids:
        issues.append(SentenceIssue(orden, "sin_claim", "Oración sin claim_id enlazado"))
        return issues
    refs = []
    for cid in claim_ids:
        ref = claims.get(cid)
        if ref is None:
            issues.append(SentenceIssue(orden, "claim_inexistente", f"claim_id {cid} no existe"))
            continue
        if event_id is not None and ref.event_id != event_id:
            issues.append(SentenceIssue(orden, "claim_de_otro_evento", f"{cid} pertenece a otro evento"))
        if ref.modo == "excluido":
            issues.append(SentenceIssue(orden, "claim_excluido", f"{cid} fue excluido por la regla de selección"))
        refs.append(ref)
    attributed = has_attribution(texto, lang)
    if any(r.modo == "atribuido" for r in refs) and not attributed:
        issues.append(SentenceIssue(orden, "falta_atribucion",
                                    "Cita una afirmación de un solo polo sin atribuirla"))
    for h in violations(texto, terms, lang):
        issues.append(SentenceIssue(orden, "termino_cargado", f"'{h.termino}' sin atribución ({h.motivo})"))
    # Disputed figures: same measure, different values -> each value must appear.
    by_measure: dict[str, list[ClaimRef]] = {}
    for r in refs:
        if r.medida and r.valor is not None:
            by_measure.setdefault(r.medida, []).append(r)
    nums = numbers_in(texto, lang)
    for medida, group in by_measure.items():
        values = {g.valor for g in group}
        if len(values) > 1:
            missing = [v for v in values if not any(abs(v - n) < 1e-6 for n in nums)]
            if missing:
                issues.append(SentenceIssue(orden, "cifra_colapsada",
                                            f"Cifra en disputa '{medida}': faltan valores {sorted(missing)}"))
            if not attributed:
                issues.append(SentenceIssue(orden, "cifra_sin_fuente",
                                            f"Cifra en disputa '{medida}' sin atribución por fuente"))
    return issues


def verify_brief(sentences: list[dict], event_id: int, claims: dict[str, ClaimRef],
                 terms: list[Term], lang: str) -> VerificationResult:
    """sentences: [{orden, texto, claim_ids}]"""
    issues: list[SentenceIssue] = []
    for s in sentences:
        issues += verify_sentence(s["orden"], s["texto"], s.get("claim_ids") or [], event_id, claims, terms, lang)
    return VerificationResult(ok=not issues, issues=issues)
