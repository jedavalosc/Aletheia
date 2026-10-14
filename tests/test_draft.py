"""Step 4: constrained drafting. Pure checks without a database, then an end-to-end run with fake agents."""
from datetime import timedelta

from app.agents.draft import code_issues, faithful_issues, flatten
from app.rules.verifier import ClaimRef

REFS = {"c1-1": ClaimRef("c1-1", 1, "atribuido", numeros=frozenset({0.82})),
        "c1-2": ClaimRef("c1-2", 1, "llano"),
        "c1-3": ClaimRef("c1-3", 1, "llano", estado="en_revision")}


def test_flatten_numbers_sentences_across_paragraphs():
    t, tc, sents = flatten({"titulo": "T", "titulo_claim_ids": ["c1-2"],
                            "paragrafos": [[{"texto": "A.", "claim_ids": ["c1-2"]}], [{"texto": "B.", "claim_ids": ["c1-1"]},
                                                                                        {"texto": " ", "claim_ids": []}]]})
    assert [(x["n"], x["parrafo"]) for x in sents] == [(0, 0), (1, 1)]


def test_code_issues_catch_numbers_attribution_unaccepted_and_title_form():
    sents = [{"n": 0, "texto": "O IPCA subiu 0,82% em setembro, segundo o IBGE.", "claim_ids": ["c1-1"]},
             {"n": 1, "texto": "O IPCA subiu 0,9% em setembro, segundo o IBGE.", "claim_ids": ["c1-1"]},
             {"n": 2, "texto": "O IPCA subiu 0,82% em setembro.", "claim_ids": ["c1-1"]},
             {"n": 3, "texto": "O governo comemorou.", "claim_ids": ["c1-3"]}]
    t_iss, by_n = code_issues("O IPCA sobe?", ["c1-2"], sents, 1, REFS, [])
    assert t_iss and 0 not in by_n
    assert any("0.9" in p or "0,9" in p for p in by_n[1])
    assert any("atribu" in p for p in by_n[2])
    assert any("no fue aceptado" in p for p in by_n[3])


def test_last_checker_verdict_wins():
    sents = [{"n": 0}, {"n": 1}]
    _, by_n = faithful_issues({"oracoes": [{"n": 0, "ok": False, "problema": "x"}, {"n": 0, "ok": True},
                                           {"n": 1, "ok": False, "problema": "adds a date"}]}, sents)
    assert list(by_n) == [1]


def _setup(s):
    from sqlalchemy import select
    from app import models as m
    from app.agents.cluster import current_monday, week_bounds
    from app.pipeline.weekly import ensure_edition, window_for_monday
    from app.seed.brasil import seed_brasil
    seed_brasil(s)
    start, _ = week_bounds(current_monday())
    outs = s.scalars(select(m.Outlet).where(m.Outlet.es_ficticio.is_(False), m.Outlet.es_fuente_oficial.is_(False))).all()[:3]
    ev = m.Event(country_id="BR", slug="t-draft", titulo_provisional="Senado marca votação da PEC", seccion="politica",
                 fecha_inicio=start, estado="candidato", impacto=98, origen="agente", semana_inicio=start)
    s.add(ev)
    s.flush()
    arts = []
    for i, o in enumerate(outs):
        a = m.Article(outlet_id=o.id, url=f"https://ex.com/pec{i}", titular=f"Senado marca votação da PEC {i}",
                      fecha_pub=start + timedelta(hours=5), hash_texto=f"pec-test-{i}", es_ficticio=False)
        s.add(a)
        s.flush()
        s.add(m.ArticleEvent(article_id=a.id, event_id=ev.id, score_similitud=1.0))
        arts.append(a)
    texts = ["O presidente do Senado marcou para quarta-feira (14) a votação da PEC.",
             "A PEC prevê o fim da escala 6x1.",
             "Senadores governistas dizem ter votos para aprovar a PEC."]
    for k, t in enumerate(texts, 1):
        c = m.Claim(event_id=ev.id, codigo=f"c{ev.id}-{k}", texto_normalizado=t, tipo="que", estado="aceptada",
                    origen="agente")
        s.add(c)
        s.flush()
        for a in arts:
            s.add(m.ClaimSupport(claim_id=c.id, article_id=a.id, fragmento_fuente=t, postura="afirma"))
    s.flush()
    ed = ensure_edition(s, "BR", window_for_monday(current_monday()))
    return ev, ed


def test_draft_end_to_end_with_fake_agents(demo_db, monkeypatch):
    from sqlalchemy import select
    from app import models as m
    from app.agents import base
    from app.agents.draft import draft_edition
    from app.db import session

    with session() as s:
        ev, ed = _setup(s)
        c = [f"c{ev.id}-{k}" for k in (1, 2, 3)]
        calls = {"draft": 0, "translate": 0}

        def fake_llm(self, st, system, user, prompt_version, json_mode=True, max_tokens=None, role="agent"):
            st.modelo, st.prompt_version = "fake", prompt_version
            if prompt_version.startswith("draft"):
                calls["draft"] += 1
                return {"titulo": "Senado marca votação da PEC do fim da escala 6x1, segundo veículos",
                        "titulo_claim_ids": c[:2],
                        "paragrafos": [
                            [{"texto": "O presidente do Senado marcou para quarta-feira (14) a votação da PEC que prevê o "
                                       "fim da escala 6x1, segundo o g1 e a Folha de S.Paulo.", "claim_ids": c[:2]}],
                            [{"texto": "Senadores governistas dizem ter votos para aprovar a PEC.", "claim_ids": [c[2]]},
                             {"texto": "A votação será em 2027, segundo o g1.", "claim_ids": [c[0]]},
                             {"texto": "Segundo o g1, a oposição tenta adiar a votação.", "claim_ids": [c[2]]}]]}
            if prompt_version.startswith("faithful"):
                return {"titulo": {"ok": True}, "oracoes": [{"n": 0, "ok": True}, {"n": 1, "ok": True}, {"n": 2, "ok": True},
                                                           {"n": 3, "ok": False, "problema": "acrescenta a oposição"}]}
            calls["translate"] += 1
            import json as _j
            p = _j.loads(user)
            return {"titulo": "T", "oracoes": {k: f"[tr] {v}" for k, v in p.get("oracoes", {}).items()},
                    "afirmacoes": {k: v for k, v in p.get("afirmacoes", {}).items()}}

        monkeypatch.setattr(base.Run, "llm", fake_llm)
        out = draft_edition(s, ed)
        assert out["descartadas"] == 2 and out["reparos"] == 2 and calls["draft"] == 3
        brief = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id)).one()
        assert [st.texto[:20] for st in brief.sentences] == ["O presidente do Sena", "Senadores governista"]
        assert {st.parrafo for st in brief.sentences} == {0, 1}
        for st in brief.sentences:  # claim_ids of translations are set by code, from the Portuguese sentence
            trs = s.scalars(select(m.Translation).where(m.Translation.source_tipo == "brief_sentence",
                                                        m.Translation.source_id == st.id)).all()
            assert {t.idioma for t in trs} == {"es", "en"} and all(t.claim_ids == st.claim_ids for t in trs)
            assert all(t.metodo == "maquina_sin_revisar" for t in trs)
        assert brief.estado == "verificada", brief.verificacion
        assert ev.id in {ee.event_id for ee in ed.events}
        q = s.scalars(select(m.ReviewItem).where(m.ReviewItem.tipo == "oracoes_descartadas",
                                                 m.ReviewItem.target_id == str(brief.id))).all()
        assert len(q) == 1 and len(q[0].datos["descartadas"]) == 2
        # A second run leaves the existing chronicle alone; an approved one is never replaced by the pipeline.
        again = draft_edition(s, ed)
        assert again.get("ya_redactadas", 0) >= 1 and calls["draft"] == 3
        brief.estado = "aprobada"
        s.flush()
        assert draft_edition(s, ed, redo=True).get("ya_aprobadas", 0) >= 1


def test_failing_title_rejects_and_queues(demo_db, monkeypatch):
    from sqlalchemy import select
    from app import models as m
    from app.agents import base
    from app.agents.draft import draft_edition
    from app.db import session

    with session() as s:
        ev = s.scalars(select(m.Event).where(m.Event.slug == "t-draft")).one()
        ed = s.scalars(select(m.Edition).join(m.EditionEvent).where(m.EditionEvent.event_id == ev.id)).first()
        c = [f"c{ev.id}-{k}" for k in (1, 2, 3)]

        def fake_llm(self, st, system, user, prompt_version, json_mode=True, max_tokens=None, role="agent"):
            st.modelo, st.prompt_version = "fake", prompt_version
            if prompt_version.startswith("draft"):
                return {"titulo": "Golpistas tentam barrar a PEC", "titulo_claim_ids": [c[2]],
                        "paragrafos": [[{"texto": "Senadores governistas dizem ter votos para aprovar a PEC.",
                                         "claim_ids": [c[2]]},
                                        {"texto": "A PEC prevê o fim da escala 6x1.", "claim_ids": [c[1]]}]]}
            return {"titulo": {"ok": True}, "oracoes": [{"n": 0, "ok": True}, {"n": 1, "ok": True}]}

        monkeypatch.setattr(base.Run, "llm", fake_llm)
        out = draft_edition(s, ed, [ev.id], redo=True)
        latest = s.scalars(select(m.NeutralBrief).where(m.NeutralBrief.event_id == ev.id)
                           .order_by(m.NeutralBrief.version.desc())).first()
        assert out.get("rechazada") == 1 and latest.estado == "rechazada" and latest.version == 2
        assert s.scalars(select(m.ReviewItem).where(m.ReviewItem.tipo == "cronica_rejeitada",
                                                    m.ReviewItem.target_id == str(latest.id))).first()


def test_literal_sentence_overrules_checker_but_not_changes_of_meaning():
    from app.agents.draft import literal_to_claims
    claim = ["Flávio Bolsonaro é o candidato do PL à Presidência da República."]
    assert literal_to_claims("Flávio Bolsonaro é candidato do PL à presidência, informou O Liberal.", claim, ["O Liberal"])
    assert not literal_to_claims("Flávio Bolsonaro não é candidato do PL à presidência.", claim, ["O Liberal"])
    assert not literal_to_claims("A Meta acusou a campanha de Lula, segundo o g1.", ["A campanha de Lula acusou a Meta."], ["g1"])
    assert not literal_to_claims("Lula acusou a Meta e o TSE.", ["A campanha de Lula acusou a Meta."], ["g1"])


def test_discouraged_verbs_outside_quotes():
    from app.rules.language import discouraged_verbs
    assert discouraged_verbs("A campanha alegou que a CUT usou o perfil.", "pt") == ["alegou"]
    assert not discouraged_verbs('O deputado disse que "a campanha alegou mentiras".', "pt")
    assert discouraged_verbs("The campaign claimed the union misused the account.", "en") == ["claimed"]
