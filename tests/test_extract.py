"""Step 3: code gates, merge policy, and an end-to-end run with fake agents."""
from app.agents.extract import gate, merge
from app.rules.claims import fragment_in_source, unsupported_numbers
from app.rules.loaded_terms import Term


class Art:
    def __init__(self, titular, resumen=None):
        self.titular, self.resumen = titular, resumen


ARTS = [(Art("IPCA sobe 0,82% em setembro e supera o teto da meta", "Inflação acelerou após deflação em agosto."), None),
        (Art("Inflação de setembro é de 0,82%, diz IBGE"), None)]
TERMS = [Term("invasão", r"invas(?:ão|ões)", "pt")]


def test_fragment_must_be_verbatim():
    assert fragment_in_source("“IPCA sobe 0,82% em setembro”", ARTS[0][0].titular)
    assert not fragment_in_source("IPCA dispara em setembro", ARTS[0][0].titular)
    assert not fragment_in_source("IPCA", ARTS[0][0].titular)  # too short to be evidence


def test_numbers_must_come_from_fragments():
    assert unsupported_numbers("IPCA subiu 0,82% em setembro", ["IPCA sobe 0,82% em setembro"]) == []
    assert unsupported_numbers("IPCA subiu 0,9% em setembro", ["IPCA sobe 0,82% em setembro"]) == [0.9]


def test_gate_drops_invented_supports_and_numbers_and_loaded_terms():
    raw = [
        {"texto": "O IPCA subiu 0,82% em setembro.", "tipo": "cifra", "medida": "IPCA de setembro", "valor": 0.82,
         "apoios": [{"n": 1, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro"},
                    {"n": 2, "postura": "afirma", "fragmento": "Inflação de setembro é de 0,82%"},
                    {"n": 2, "postura": "afirma", "fragmento": "texto que não existe no artigo"}]},
        {"texto": "O IPCA subiu 1,2% em setembro.", "tipo": "cifra", "medida": "x", "valor": 1.2,
         "apoios": [{"n": 1, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro"}]},
        {"texto": "Houve invasão de prédio.", "tipo": "que",
         "apoios": [{"n": 1, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro"}]},
        {"texto": "Inflação acelerou.", "tipo": "que", "apoios": [{"n": 9, "postura": "afirma", "fragmento": "x"}]},
    ]
    kept, rejected = gate(raw, ARTS, TERMS)
    assert len(kept) == 1 and len(kept[0]["apoios"]) == 2
    assert len(rejected) == 3
    reasons = " ".join(" ".join(r["problemas"]) for r in rejected)
    assert "números ausentes" in reasons and "termo carregado" in reasons and "nenhum apoio" in reasons


def test_merge_requires_checker_confirmation():
    claims = [{"texto": "a", "tipo": "que", "apoios": [{"n": 1, "postura": "afirma", "fragmento": "f"}]},
              {"texto": "b", "tipo": "que", "apoios": [{"n": 1, "postura": "afirma", "fragmento": "f"}]},
              {"texto": "c", "tipo": "que", "apoios": [{"n": 1, "postura": "afirma", "fragmento": "f"}]},
              {"texto": "d", "tipo": "que", "apoios": [{"n": 1, "postura": "afirma", "fragmento": "f"}]}]
    verdicts = [{"id": 1, "veredito": "confirmada", "apoios": [{"n": 1, "postura_correta": "afirma"}]},
                {"id": 2, "veredito": "confirmada", "apoios": [{"n": 1, "postura_correta": "matiza"}]},
                {"id": 3, "veredito": "rejeitada"}]
    out = merge(claims, verdicts)
    assert [c["estado"] for c in out] == ["aceptada", "en_revision", "rechazada", "en_revision"]
    assert all(c["estado"] == "en_revision" for c in merge(claims, None))


def test_merge_softens_affirms_vs_qualifies_but_flags_contradiction():
    two = lambda t: {"texto": t, "tipo": "que", "apoios": [{"n": 1, "postura": "afirma", "fragmento": "f"},
                                                          {"n": 2, "postura": "afirma", "fragmento": "g"}]}
    verdicts = [{"id": 1, "veredito": "confirmada", "apoios": [{"n": 1, "postura_correta": "afirma"},
                                                              {"n": 2, "postura_correta": "matiza"}]},
                {"id": 2, "veredito": "confirmada", "apoios": [{"n": 1, "postura_correta": "afirma"},
                                                              {"n": 2, "postura_correta": "contradice"}]}]
    a, b = merge([two("a"), two("b")], verdicts)
    assert a["estado"] == "aceptada" and [x["postura"] for x in a["apoios"]] == ["afirma", "matiza"]
    assert a["posturas_suavizadas"] and not a["divergencias_postura"]
    assert b["estado"] == "en_revision" and b["divergencias_postura"] == ["[2] afirma→contradice"]


def test_thinking_defaults_off_for_kimi_agents(monkeypatch):
    from app.config import Settings
    for k in ("AGENT_THINKING", "VERIFIER_THINKING", "AGENT_MODEL", "VERIFIER_MODEL", "AGENT_PROVIDER", "VERIFIER_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("CHAT_MODEL", "kimi-k3")
    s = Settings()
    assert (s.agent_model, s.verifier_model) == ("kimi-k3", "kimi-k2.6")
    assert s.agent_thinking == "disabled" and s.verifier_thinking == "disabled"
    monkeypatch.setenv("AGENT_THINKING", "enabled")
    assert Settings().agent_thinking == "enabled"
    monkeypatch.setenv("CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("CHAT_MODEL", "claude-sonnet-5-5")
    monkeypatch.delenv("AGENT_THINKING")
    assert Settings().agent_thinking is None


def test_extract_end_to_end_with_fake_agents(demo_db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from app import models as m
    from app.agents import base
    from app.agents.cluster import current_monday, week_bounds
    from app.agents.extract import extract_week
    from app.db import session

    with session() as s:
        from app.seed.brasil import seed_brasil
        seed_brasil(s)
        start, _ = week_bounds(current_monday())
        outs = s.scalars(select(m.Outlet).where(m.Outlet.es_ficticio.is_(False), m.Outlet.es_fuente_oficial.is_(False))).all()[:3]
        ev = m.Event(country_id="BR", slug="t-ipca", titulo_provisional="IPCA sobe em setembro", seccion="economia",
                     fecha_inicio=start, estado="candidato", impacto=99, origen="agente", semana_inicio=start)
        s.add(ev)
        s.flush()
        heads = ["IPCA sobe 0,82% em setembro, informa IBGE", "Inflação: IPCA sobe 0,82% em setembro",
                 "IPCA sobe 0,82% em setembro e supera meta"]
        for i, (o, h) in enumerate(zip(outs, heads)):
            a = m.Article(outlet_id=o.id, url=f"https://ex.com/ipca{i}", titular=h, fecha_pub=start + timedelta(hours=5),
                          hash_texto=f"ipca-test-{i}", es_ficticio=False)
            s.add(a)
            s.flush()
            s.add(m.ArticleEvent(article_id=a.id, event_id=ev.id, score_similitud=1.0))
        s.flush()

        def fake_llm(self, st, system, user, prompt_version, json_mode=True, max_tokens=None, role="agent"):
            st.modelo, st.prompt_version = ("fake-checker" if role == "verifier" else "fake-extractor"), prompt_version
            if role == "verifier":
                return {"verificacoes": [{"id": 1, "veredito": "confirmada", "motivo": "ok",
                                          "apoios": [{"n": n, "postura_correta": "afirma"} for n in (1, 2, 3)]},
                                         {"id": 2, "veredito": "parcial", "motivo": "atribuição incerta"}]}
            return {"afirmacoes": [
                {"texto": "O IPCA subiu 0,82% em setembro.", "tipo": "cifra", "medida": "IPCA de setembro", "valor": 0.82,
                 "apoios": [{"n": n, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro"} for n in (1, 2, 3)]},
                {"texto": "Segundo o IBGE, o IPCA subiu em setembro.", "tipo": "cita", "atribucion": "IBGE",
                 "apoios": [{"n": 1, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro, informa IBGE"}]},
                {"texto": "O IPCA subiu 5% em setembro.", "tipo": "cifra", "medida": "IPCA", "valor": 5,
                 "apoios": [{"n": 1, "postura": "afirma", "fragmento": "IPCA sobe 0,82% em setembro"}]}]}

        monkeypatch.setattr(base.Run, "llm", fake_llm)
        out = extract_week(s, "BR", current_monday(), max_events=3)
        claims = {c.codigo: c for c in s.scalars(select(m.Claim).where(m.Claim.event_id == ev.id))}
        assert out["eventos_procesados"] >= 1
        assert len(claims) == 2  # the invented 5% figure never reached the table
        assert sorted(c.estado for c in claims.values()) == ["aceptada", "en_revision"]
        assert claims[f"c{ev.id}-1"].estado == "aceptada" and len(claims[f"c{ev.id}-1"].supports) == 3
        assert claims[f"c{ev.id}-1"].modo == "atribuido"  # no outlet positions yet -> never a plain fact
        q = s.scalars(select(m.ReviewItem).where(m.ReviewItem.tipo == "afirmacion_en_revision",
                                                 m.ReviewItem.target_id == str(claims[f"c{ev.id}-2"].id))).all()
        assert len(q) == 1
        again = extract_week(s, "BR", current_monday(), max_events=3)
        assert again.get("eventos_ya_procesados", 0) >= 1
