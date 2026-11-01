"""Step 5: outlet positions."""
import random
from datetime import timedelta

from app.rules.positions import Item, estimate, krippendorff_alpha_interval


def test_alpha_matches_known_cases():
    assert krippendorff_alpha_interval([[1, 1], [2, 2], [-1, -1]]) == 1.0
    assert krippendorff_alpha_interval([[1, None], [None, 2]]) is None
    # value checked against the reference implementation (krippendorff package, interval metric)
    units = [[-2, -2, None], [0, 1, 0], [1, 1, 1], [2, 0, None], [-1, -1, -1], [0, 0, 1]]
    assert abs(krippendorff_alpha_interval(units) - 0.71875) < 1e-9


def test_estimate_recovers_order_and_removes_agenda_effects():
    rng = random.Random(3)
    true = {0: -0.8, 1: -0.3, 2: 0.0, 3: 0.3, 4: 0.8}
    items, aid = [], 0
    for e in range(80):
        effect = rng.choice([-1.5, 0, 1.5])  # some weeks the news itself favours a side
        for o in true:
            lat = effect + 2 * true[o] + rng.gauss(0, 0.5)
            items.append(Item(aid, o, e, [max(-2, min(2, round(lat + rng.gauss(0, 0.4)))) for _ in range(2)]))
            aid += 1
    est = {x.outlet_id: x for x in estimate(items, reps=300)}
    assert [o for o, _ in sorted(est.items(), key=lambda kv: kv[1].score)] == [0, 1, 2, 3, 4]
    assert est[0].hi < 0 < est[4].lo and est[2].lo < 0 < est[2].hi


def _world(s, n_events=24):
    from sqlalchemy import select
    from app import models as m
    from app.agents.cluster import current_monday, week_bounds
    from app.seed.brasil import seed_brasil
    seed_brasil(s)
    start, _ = week_bounds(current_monday())
    outs = s.scalars(select(m.Outlet).where(m.Outlet.es_ficticio.is_(False), m.Outlet.es_fuente_oficial.is_(False))
                     .order_by(m.Outlet.id)).all()[:9]
    lean = {o.id: ("AA" if k < 3 else "BB" if k < 6 else "NN") for k, o in enumerate(outs)}
    for e in range(n_events):
        ev = m.Event(country_id="BR", slug=f"t-pos-{e}", titulo_provisional=f"Evento político {e}", seccion="politica",
                     fecha_inicio=start, estado="candidato", impacto=10, origen="agente", semana_inicio=start)
        s.add(ev)
        s.flush()
        for o in outs:
            a = m.Article(outlet_id=o.id, url=f"https://ex.com/pos/{e}/{o.id}", titular=f"Fato {e} narrado {lean[o.id]}",
                          fecha_pub=start + timedelta(hours=3), hash_texto=f"pos-{e}-{o.id}", es_ficticio=False)
            s.add(a)
            s.flush()
            s.add(m.ArticleEvent(article_id=a.id, event_id=ev.id, score_similitud=1.0))
    s.flush()
    return outs, lean


def _fake(noisy_verifier=False):
    import re as _re
    rng = random.Random(5)

    def fake_llm(self, st, system, user, prompt_version, json_mode=True, max_tokens=None, role="agent"):
        st.modelo, st.prompt_version = role, prompt_version
        out = []
        for line in user.splitlines():
            mt = _re.match(r"\((\d+)\) .*?(AA|BB|NN|$)", line)
            if not mt:
                continue
            lab = {"AA": "campo-lulista_forte", "BB": "campo-bolsonarista_forte", "NN": "neutro"}.get(mt.group(2), "nao_se_aplica")
            if noisy_verifier and role == "verifier":
                lab = rng.choice(["campo-lulista_forte", "campo-lulista", "neutro", "campo-bolsonarista", "campo-bolsonarista_forte"])
            out.append({"n": int(mt.group(1)), "rotulo": lab})
        return {"codigos": out}
    return fake_llm


def test_positions_end_to_end_gate_then_publish(demo_db, monkeypatch):
    from sqlalchemy import select
    from app import models as m
    from app.agents import base
    from app.agents.cluster import current_monday
    from app.agents.positions import editor_agreement, estimate_positions
    from app.analytics.core import pole_members
    from app.db import session

    with session() as s:
        outs, lean = _world(s)
        axis = s.scalars(select(m.Cleavage).where(m.Cleavage.slug == "lulismo-bolsonarismo")).one()
        # 1. A verifier that codes at random: alpha too low, nothing published, queue says why.
        monkeypatch.setenv("VERIFIER_MODEL", "fake-noisy")
        monkeypatch.setattr(base.Run, "llm", _fake(noisy_verifier=True))
        r1 = estimate_positions(s, "BR", current_monday(), force=True)
        assert r1["alpha_modelos"] < 0.667 and "estimados" not in r1
        assert s.scalars(select(m.ReviewItem).where(m.ReviewItem.tipo == "posicoes_nao_publicadas")).first()
        assert not s.scalars(select(m.OutletPosition).where(m.OutletPosition.cleavage_id == axis.id,
                                                            m.OutletPosition.outlet_id.in_([o.id for o in outs]))).all()
        # 2. Consistent annotators: positions published, provisional, with interval and details.
        monkeypatch.setenv("VERIFIER_MODEL", "fake-consistent")
        monkeypatch.setattr(base.Run, "llm", _fake())
        r2 = estimate_positions(s, "BR", current_monday(), force=True)
        assert r2["alpha_modelos"] > 0.9 and r2["estimados"] >= 9
        from datetime import datetime, timezone
        members = {pm.pole.slug: pm.outlet_ids for pm in pole_members(s, axis, datetime.now(timezone.utc))}
        a_side = {o.id for o in outs if lean[o.id] == "AA"}
        b_side = {o.id for o in outs if lean[o.id] == "BB"}
        assert a_side <= members["campo-lulista"] and b_side <= members["campo-bolsonarista"]
        assert not ({o.id for o in outs if lean[o.id] == "NN"} & (members["campo-lulista"] | members["campo-bolsonarista"]))
        p = s.scalars(select(m.OutletPosition).where(m.OutletPosition.outlet_id == outs[0].id,
                                                     m.OutletPosition.cleavage_id == axis.id)
                      .order_by(m.OutletPosition.id.desc())).first()
        assert p.provisional and p.detalle["alpha_modelos"] > 0.9 and p.ic_inferior <= p.score <= p.ic_superior
        # 3. Renewal: within 28 days nothing happens unless forced.
        assert "omitido" in estimate_positions(s, "BR", current_monday())
        # 4. Territorial axis comes from the head-office region.
        terr = s.scalars(select(m.Cleavage).where(m.Cleavage.tipo == "territorial")).one()
        assert s.scalars(select(m.OutletPosition).where(m.OutletPosition.cleavage_id == terr.id)).first()
        # 5. Editor agreement.
        coders = sorted(set(s.scalars(select(m.PositionAnnotation.codificador).where(
            m.PositionAnnotation.codificador == "modelo:fake-consistent"))))
        arts = s.scalars(select(m.PositionAnnotation).where(m.PositionAnnotation.codificador == coders[0])).all()[:10]
        for x in arts:
            s.add(m.PositionAnnotation(article_id=x.article_id, event_id=x.event_id, cleavage_id=axis.id,
                                       codificador="editor:test", prompt_version="editor", valor=x.valor))
        s.flush()
        ag = editor_agreement(s, axis.id, coders)
        assert ag["n"] == 10 and ag["alpha"] == 1.0
