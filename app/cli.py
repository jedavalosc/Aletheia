"""Command line: python -m app.cli <command>"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .config import ROOT
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
    sub.add_parser("purge-chats", help="Apaga conversas com retenção vencida")
    sub.add_parser("status", help="Resumo das edições, verificação e bandeiras")
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
    elif a.cmd == "eval-chat":
        from evals.run_eval import run
        sys.exit(run(a.out))


if __name__ == "__main__":
    main()
