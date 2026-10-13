"""Collection and grouping agents: parsing, canonical URLs, scope filter,
clustering behaviour, run log and exception queue (no network, no model)."""
from datetime import datetime, timedelta, timezone

from app.agents.cluster import average_linkage, in_scope_prefilter, is_opinion, pairwise, tfidf, tokens
from app.agents.collect import canonical_url, clean_text, parse_news_sitemap, parse_rss

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>STF decide sobre &lt;b&gt;tema&lt;/b&gt;</title><link>https://ex.com/a?utm_source=x&amp;id=3</link>
<pubDate>Mon, 12 Oct 2026 10:00:00 -0300</pubDate><description>&lt;p&gt;Resumo   curto&lt;/p&gt;</description></item>
<item><title></title><link>https://ex.com/b</link></item></channel></rss>"""

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://ex.com/n1</loc><news:news><news:publication_date>2026-10-12T09:00:00-03:00</news:publication_date>
<news:title>Senado vota PEC</news:title></news:news></url></urlset>"""


def test_canonical_url_strips_tracking_and_unwraps_redirects():
    assert canonical_url("http://Ex.com/a/?utm_source=x&id=3") == "https://ex.com/a?id=3"
    assert canonical_url("https://redir.folha.com.br/redir/online/poder/rss091/*https://www1.folha.uol.com.br/x.shtml") \
        == "https://www1.folha.uol.com.br/x.shtml"


def test_parse_rss_and_sitemap_keep_only_headline_and_summary():
    items = parse_rss(RSS)
    assert len(items) == 1 and items[0]["titular"] == "STF decide sobre tema"
    assert items[0]["resumen"] == "Resumo curto"
    assert items[0]["fecha"] == datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)
    sm = parse_news_sitemap(SITEMAP)
    assert sm[0]["titular"] == "Senado vota PEC" and sm[0]["resumen"] is None
    assert clean_text("x" * 1000).endswith("…")


class A:  # minimal article stand-in for the prefilter
    def __init__(self, url, titular):
        self.url, self.titular = url, titular


def test_scope_and_opinion_prefilter():
    assert not in_scope_prefilter(A("https://ex.com/esporte/futebol/x", "Time vence"))
    assert not in_scope_prefilter(A("https://ex.com/x", "Ex-BBB anuncia namoro"))
    assert is_opinion(A("https://www1.folha.uol.com.br/colunas/fulano/2026/10/x.shtml", "Opinião"))
    assert in_scope_prefilter(A("https://ex.com/politica/x", "Senado aprova PEC da escala 6x1"))


def test_clustering_separates_events_sharing_a_name():
    heads = [
        "Senado aprova PEC que acaba com a escala 6x1",
        "PEC do fim da escala 6x1 é aprovada no Senado em dois turnos",
        "Escala 6x1: Senado aprova fim da jornada em votação da PEC",
        "Flávio Bolsonaro visita arcebispo de Brasília",
        "Flávio Bolsonaro faz visita ao arcebispo de Brasília neste domingo",
        "IPCA sobe 0,82% em setembro e supera teto da meta",
        "Inflação: IPCA de setembro sobe 0,82% e estoura meta",
    ]
    vecs = tfidf([tokens(h) for h in heads])
    groups = average_linkage(len(heads), pairwise(vecs, list(range(len(heads)))))
    as_sets = [set(g) for g in groups]
    assert {0, 1, 2} in as_sets
    assert {3, 4} in as_sets
    assert {5, 6} in as_sets


def test_collect_and_cluster_end_to_end_without_network(demo_db, monkeypatch):
    """Feeds are served from memory; grouping runs without the model."""
    import httpx
    from sqlalchemy import select
    from app import models as m
    from app.agents import collect as C
    from app.agents.cluster import cluster_week, current_monday
    from app.db import session

    now = datetime.now(timezone.utc) - timedelta(hours=1)
    stamp = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    stories = ["Senado aprova PEC que acaba com a escala 6x1",
               "PEC do fim da escala 6x1 é aprovada no Senado",
               "Escala 6x1: Senado aprova fim da jornada na PEC"]

    def feed_for(url):
        i = abs(hash(url)) % 3
        body = "".join(f"<item><title>{stories[i]}</title><link>{url}/n{i}</link><pubDate>{stamp}</pubDate>"
                       f"<description>Votação no Senado</description></item>" for _ in range(1))
        return f"<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>{body}</channel></rss>".encode()

    class FakeResp:
        def __init__(self, url):
            self.status_code, self.url = 200, url
            self.text = "" if url.endswith("robots.txt") else ""
            self.content = feed_for(url)
        def raise_for_status(self):
            pass

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **k: FakeResp(url))
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    with session() as s:
        from app.seed.brasil import seed_brasil
        seed_brasil(s)
        res = C.collect(s, "BR", only=["Folha de S.Paulo", "g1", "O Globo", "UOL", "Poder360", "CNN Brasil"])
        assert res["fuentes_ok"] == res["fuentes"] and res["nuevos"] >= 6
        again = C.collect(s, "BR", only=["Folha de S.Paulo"])
        assert again["nuevos"] == 0  # idempotent
        out = cluster_week(s, "BR", current_monday(), use_model=False)
        assert out["eventos_creados"] >= 1
        ev = s.scalars(select(m.Event).where(m.Event.origen == "agente")).first()
        assert ev.estado == "candidato" and ev.semana_inicio is not None
        runs = s.scalars(select(m.AgentRun)).all()
        assert {r.tipo for r in runs} >= {"recoleccion", "agrupacion"} and all(r.estado == "ok" for r in runs)
        steps = s.scalars(select(m.AgentStep).where(m.AgentStep.agente == "recolector")).all()
        assert steps and all(st.estado == "ok" for st in steps)


def test_review_queue_dedupes(demo_db):
    from sqlalchemy import select
    from app import models as m
    from app.agents.base import agent_run
    from app.db import session
    with session() as s:
        with agent_run(s, "prueba", "BR", budget_cents=0) as run:
            run.review("fuente_fallando", "outlet", 1, "falhou")
            run.review("fuente_fallando", "outlet", 1, "falhou de novo")
        n = s.scalars(select(m.ReviewItem).where(m.ReviewItem.tipo == "fuente_fallando")).all()
        assert len(n) == 1
