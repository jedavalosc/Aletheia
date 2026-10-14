"""Sentence-by-sentence verifier for the chronicle and its translations.

Rejects:
  * any sentence without claim_ids;
  * any claim_id that does not exist (or belongs to another event);
  * any loaded term without attribution or quotation;
  * a sentence that cites an attributed claim without an attribution marker;
  * a sentence citing several sources of one disputed figure but not giving
    each source's value (i.e. averaging or collapsing them);
  * a sentence citing an excluded claim;
  * a sentence citing a claim the agents did not accept (step 3);
  * a number that appears in none of the cited claims (step 4);
  * a certainty formula ("sem dúvida", "é evidente que");
  * an attributive verb the style guide rules out (alegou, revelou, rebateu...).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .language import certainty_hits, discouraged_verbs, has_attribution, numbers_in
from .loaded_terms import Term, violations


@dataclass
class ClaimRef:
    codigo: str
    event_id: int
    modo: str | None
    medida: str | None = None
    valor: float | None = None
    estado: str = "aceptada"
    numeros: frozenset = frozenset()  # numbers in the claim text (pt convention) and its value


def number_supported(n: float, allowed: set[float]) -> bool:
    """A number is supported if it equals an allowed one, or differs by a factor of 1,000
    (2,3 bilhões = 2.300 millones = 2.3 billion)."""
    return any(abs(n - a) < 1e-6 or abs(n - a * 1000) < 1e-6 or abs(n * 1000 - a) < 1e-6 for a in allowed)


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
        if ref.estado != "aceptada":
            issues.append(SentenceIssue(orden, "claim_no_aceptado", f"{cid} no fue aceptado por los agentes ({ref.estado})"))
        refs.append(ref)
    attributed = has_attribution(texto, lang)
    if any(r.modo == "atribuido" for r in refs) and not attributed:
        issues.append(SentenceIssue(orden, "falta_atribucion",
                                    "Cita una afirmación de un solo polo sin atribuirla"))
    for h in violations(texto, terms, lang):
        issues.append(SentenceIssue(orden, "termino_cargado", f"'{h.termino}' sin atribución ({h.motivo})"))
    for p in certainty_hits(texto, lang):
        issues.append(SentenceIssue(orden, "formula_certeza", f"Fórmula de certeza: '{p}'"))
    for vb in discouraged_verbs(texto, lang):
        issues.append(SentenceIssue(orden, "verbo_desaconsejado", f"Verbo atributivo desaconsejado: '{vb}' (usar disse/afirmou)"))
    if refs:
        allowed: set[float] = set()
        for r in refs:
            allowed |= set(r.numeros)
        loose = sorted(n for n in numbers_in(texto, lang) if not number_supported(n, allowed))
        if loose:
            issues.append(SentenceIssue(orden, "numero_sin_respaldo",
                                        f"Número(s) {', '.join(f'{n:g}' for n in loose)} ausente(s) de los claims citados"))
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
