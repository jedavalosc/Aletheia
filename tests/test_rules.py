from app.rules.language import has_attribution, numbers_in
from app.rules.loaded_terms import Term, scan, violations
from app.rules.selection import ClaimView, SupportView, decide
from app.rules.verifier import ClaimRef, verify_brief
from app.rules.commentary import verify_commentary
from app.rules.visual import contrast, delta_e

TERMS = [Term("invasão", r"invas(?:ão|ões|or|ores)|invadi(?:u|do|da)", "pt"),
         Term("petralha", r"petralha(?:s)?", "pt", "cita")]
CLAIMS = {
    "c-1": ClaimRef("c-1", 1, "llano"),
    "c-2": ClaimRef("c-2", 1, "atribuido"),
    "c-3": ClaimRef("c-3", 1, "atribuido", "famílias", 210),
    "c-4": ClaimRef("c-4", 1, "atribuido", "famílias", 140),
    "c-9": ClaimRef("c-9", 2, "llano"),
}


def v(text, cids, lang="pt"):
    return verify_brief([{"orden": 0, "texto": text, "claim_ids": cids}], 1, CLAIMS, TERMS, lang)


def codes(r):
    return {i.codigo for i in r.issues}


def test_sentence_without_claim_rejected():
    assert "sin_claim" in codes(v("O governo decretou emergência.", []))


def test_nonexistent_and_foreign_claims_rejected():
    assert "claim_inexistente" in codes(v("Texto.", ["c-404"]))
    assert "claim_de_otro_evento" in codes(v("Texto.", ["c-9"]))


def test_loaded_term_needs_attribution_or_quote():
    assert "termino_cargado" in codes(v("A invasão começou em agosto.", ["c-1"]))
    assert v("A invasão começou em agosto, segundo a secretaria.", ["c-1"]).ok
    assert v('O deputado chamou o ato de "invasão".', ["c-1"]).ok


def test_quote_only_terms():
    assert violations("Os petralhas protestaram, disse o deputado.", TERMS, "pt")
    assert not violations('O deputado disse "petralhas".', TERMS, "pt")


def test_single_pole_claim_needs_attribution():
    assert "falta_atribucion" in codes(v("A medida custará caro.", ["c-2"]))
    assert v("A medida custará caro, segundo a Fazenda.", ["c-2"]).ok


def test_disputed_figures_never_collapsed():
    r = v("Cerca de 175 famílias vivem no prédio, segundo as fontes.", ["c-3", "c-4"])
    assert "cifra_colapsada" in codes(r)
    assert v("O movimento informou 210 famílias; a prefeitura registrou 140.", ["c-3", "c-4"]).ok


def test_number_parsing_by_language():
    assert numbers_in("21.500 famílias e 3,5%", "pt") == {21500.0, 3.5}
    assert numbers_in("21,500 families and 3.5%", "en") == {21500.0, 3.5}


def test_selection_rule():
    two_poles = ClaimView("c", [SupportView("a", "afirma"), SupportView("b", "afirma")])
    one_pole = ClaimView("c", [SupportView("a", "afirma"), SupportView("a", "afirma")])
    primary = ClaimView("c", [SupportView("a", "afirma")], fuente_primaria_verificada=True)
    only_contra = ClaimView("c", [SupportView("b", "contradice")])
    assert decide(two_poles).modo == "llano"
    assert decide(one_pole).modo == "atribuido"
    assert decide(primary).modo == "llano"
    assert decide(only_contra).modo == "excluido"


def test_commentary_structure_rules():
    st = lambda **k: {"orden": 0, "texto": "x", "plano": "descriptivo", "estatus_epistemico": "consenso",
                      "escala_temporal": "coyuntura", "claim_ids": [], "reference_ids": [1], "autoria": "humano", **k}
    dm = [{"disciplina": d, "familia": f} for d, f in (("H", "historia"), ("E", "ciencias_sociales"), ("D", "derecho"))]
    oq = [{}, {}]
    bad = verify_commentary([st(estatus_epistemico="hipotesis", plano="normativo"), st(plano="explicativo", autoria="modelo"),
                             st(texto="É evidente que sim.", estatus_epistemico="mayoritaria")], [{}], dm, set(), {1})
    joined = " ".join(bad)
    assert "Hipótesis fuera del plano explicativo" in joined
    assert "no redactado por persona" in joined
    assert "certeza" in joined
    assert "2-5" in joined
    ok = verify_commentary([st(escala_temporal="acontecimiento"), st(), st(escala_temporal="larga_duracion")], oq, dm, set(), {1})
    assert ok == []


def test_palette_rules():
    assert contrast("#4C6A8B", "#FBFAF7") >= 3 and contrast("#7F5E7C", "#FBFAF7") >= 3
    assert delta_e("#5E5546", "#CC0000") > 20 and delta_e("#5E5546", "#009C3B") > 20
