"""Automatic checks for the academic layer (academic commentator doc, s.4),
run before peer review. They check structure, never the substance."""
from __future__ import annotations

from .language import certainty_hits

SCALES = {"acontecimiento", "coyuntura", "larga_duracion"}


def verify_commentary(statements: list[dict], open_questions: list[dict], discipline_map: list[dict],
                      known_claims: set[str], verified_refs: set[int], lang: str = "pt") -> list[str]:
    issues: list[str] = []
    if not 2 <= len(open_questions) <= 5:
        issues.append(f"'O que não sabemos' debe tener 2-5 preguntas (tiene {len(open_questions)})")
    disciplines = {d["disciplina"] for d in discipline_map}
    families = {d["familia"] for d in discipline_map}
    if len(disciplines) < 3 or len(families) < 2:
        issues.append("Mapa disciplinar: mínimo 3 disciplinas de 2 familias")
    present_scales = {s["escala_temporal"] for s in statements} & SCALES
    for missing in sorted(SCALES - present_scales):
        issues.append(f"Falta al menos un enunciado en la escala '{missing}'")
    n = len(statements)
    n_hyp = sum(1 for s in statements if s["estatus_epistemico"] == "hipotesis")
    if n and n_hyp * 5 > n:
        issues.append(f"Tope de hipótesis superado: {n_hyp} de {n} (máximo 1 de cada 5)")
    for s in statements:
        o = s.get("orden")
        if s["estatus_epistemico"] == "hipotesis":
            if s["plano"] != "explicativo":
                issues.append(f"[{o}] Hipótesis fuera del plano explicativo")
            if not s.get("mecanismo") or not s.get("evidencia_que_refutaria"):
                issues.append(f"[{o}] Hipótesis sin mecanismo o condición de refutación")
        if s["plano"] in ("explicativo", "normativo") and s.get("autoria") != "humano":
            issues.append(f"[{o}] Enunciado {s['plano']} no redactado por persona")
        if s["estatus_epistemico"] != "sin_evidencia" and not (s.get("claim_ids") or s.get("reference_ids")):
            issues.append(f"[{o}] Enunciado sin cita")
        for c in s.get("claim_ids") or []:
            if c not in known_claims:
                issues.append(f"[{o}] claim_id inexistente: {c}")
        for r in s.get("reference_ids") or []:
            if r not in verified_refs:
                issues.append(f"[{o}] Referencia sin verificar: {r}")
        if s["estatus_epistemico"] != "consenso":
            for hit in certainty_hits(s["texto"], lang):
                issues.append(f"[{o}] Fórmula de certeza injustificada: '{hit}'")
    return issues
