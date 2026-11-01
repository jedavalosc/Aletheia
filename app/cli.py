"""Command line: python -m app.cli <command>"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .config import ROOT, get_settings
from .db import session


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Aplica as migrações (alembic upgrade head)")
    sub.add_parser("seed-brasil", help="Carrega a configuração do Brasil (eixos, veículos para ingestão, termos)")
    sd = sub.add_parser("seed-demo", help="Carrega a edição de demonstração fictícia")
    sd.add_argument("--aprovar-como", default=None,
                    help="Nome do editor que aprova explicitamente a demonstração (sem isso, fica em revisão)")
    sd.add_argument("--se-ausente", action="store_true", help="Não falha se a demonstração já existir")
    sub.add_parser("reset-demo", help="Remove a edição de demonstração e todo dado fictício")
    sub.add_parser("build-site", help="Gera o site estático a partir das edições publicadas")
    co = sub.add_parser("collect", help="Passo 1: recolhe artigos (RSS e sitemaps de notícias)")
    co.add_argument("--medios", nargs="*", default=None, help="Limitar a estes veículos (nomes exatos)")
    co.add_argument("--disparado-por", default="cli")
    cu = sub.add_parser("cluster", help="Passo 2: agrupa os artigos da semana em eventos")
    cu.add_argument("--semana", default=None, help="Segunda-feira da semana (AAAA-MM-DD); padrão: semana atual")
    cu.add_argument("--sem-modelo", action="store_true", help="Não usar o modelo para casos duvidosos")
    cu.add_argument("--disparado-por", default="cli")
    ex = sub.add_parser("extract", help="Passo 3: extrai afirmações dos eventos da semana, com verificação cruzada")
    ex.add_argument("--semana", default=None, help="Segunda-feira da semana (AAAA-MM-DD); padrão: semana atual")
    ex.add_argument("--max-eventos", type=int, default=15)
    ex.add_argument("--refazer", action="store_true", help="Refaz eventos já processados (sem decisões do editor)")
    ex.add_argument("--disparado-por", default="cli")
    dr = sub.add_parser("draft", help="Passo 4: monta a edição da semana e redige as crônicas (PT, ES, EN)")
    dr.add_argument("--semana", default=None, help="Segunda-feira da semana (AAAA-MM-DD); padrão: semana atual")
    dr.add_argument("--eventos", type=int, nargs="*", default=None, help="Só estes eventos (ids)")
    dr.add_argument("--refazer", action="store_true", help="Redige de novo mesmo com crônica existente")
    dr.add_argument("--instrucao", default=None, help="Instrução do editor para o redator")
    dr.add_argument("--disparado-por", default="cli")
    sub.add_parser("purge-chats", help="Apaga conversas com retenção vencida")
    sub.add_parser("status", help="Resumo das edições, verificação e bandeiras")
    bp = sub.add_parser("build-panel", help="Gera o painel didático (handoff) e verifica registro × código")
    bp.add_argument("--out", default=str(ROOT / "build" / "panel" / "index.html"))
    bp.add_argument("--check", action="store_true", help="Falha se registro, anotações e código divergirem")
    bp.add_argument("--sem-dados", action="store_true", help="Não consulta a base (só o repositório)")
    ev = sub.add_parser("eval-chat", help="Roda o conjunto de avaliação do chat")
    ev.add_argument("--out", default=str(ROOT / "build" / "eval"))
    a = ap.parse_args(argv)

    if a.cmd == "migrate":
        sys.exit(subprocess.call(["alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"], cwd=ROOT))
    if a.cmd == "seed-brasil":
        from .seed.brasil import seed_brasil
        with session() as s:
            seed_brasil(s)
        print("Configuração do Brasil carregada.")
    elif a.cmd == "seed-demo":
        from sqlalchemy import select
        from . import models as m
        from .seed.demo import seed_demo
        if a.se_ausente:
            with session() as s:
                if s.scalars(select(m.Edition).where(m.Edition.es_demo.is_(True))).first():
                    print("Demonstração já carregada.")
                    return
        with session() as s:
            ed = seed_demo(s, a.aprovar_como)
            print(f"Edição de demonstração n.º {ed.numero}: estado {ed.estado}")
    elif a.cmd == "reset-demo":
        from .seed.demo import reset_demo
        with session() as s:
            reset_demo(s)
        print("Demonstração removida.")
    elif a.cmd == "collect":
        from .agents.collect import collect
        with session() as s:
            print(json.dumps(collect(s, get_settings().country_code, a.disparado_por, a.medios), ensure_ascii=False))
    elif a.cmd == "cluster":
        from datetime import date
        from .agents.cluster import cluster_week
        with session() as s:
            wk = date.fromisoformat(a.semana) if a.semana else None
            print(json.dumps(cluster_week(s, get_settings().country_code, wk, use_model=not a.sem_modelo,
                                          disparado_por=a.disparado_por), ensure_ascii=False, default=str))
    elif a.cmd == "extract":
        from datetime import date
        from .agents.extract import extract_week
        with session() as s:
            wk = date.fromisoformat(a.semana) if a.semana else None
            print(json.dumps(extract_week(s, get_settings().country_code, wk, a.max_eventos, a.refazer, a.disparado_por),
                             ensure_ascii=False, default=str))
    elif a.cmd == "draft":
        from datetime import date
        from .agents.cluster import current_monday
        from .agents.draft import draft_edition
        from .pipeline.weekly import ensure_edition, window_for_monday
        with session() as s:
            wk = date.fromisoformat(a.semana) if a.semana else current_monday()
            ed = ensure_edition(s, get_settings().country_code, window_for_monday(wk))
            s.commit()
            print(json.dumps(draft_edition(s, ed, a.eventos, a.refazer, a.instrucao, a.disparado_por),
                             ensure_ascii=False, default=str))
    elif a.cmd == "build-site":
        from .site.build import build_site
        with session() as s:
            out = build_site(s)
        print(f"Site gerado em {out}")
    elif a.cmd == "purge-chats":
        from .chat.store import purge_expired
        with session() as s:
            n = purge_expired(s)
        print(f"{n} conversas apagadas.")
    elif a.cmd == "status":
        from .status import status
        with session() as s:
            print(json.dumps(status(s), ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "build-panel":
        from .panel.build import build_panel
        _, problems = build_panel(a.out, with_live=not a.sem_dados)
        print(f"Painel gerado em {a.out}")
        for p in problems:
            print("  ✕", p)
        if a.check and problems:
            sys.exit(1)
    elif a.cmd == "eval-chat":
        from evals.run_eval import run
        sys.exit(run(a.out))


if __name__ == "__main__":
    main()
