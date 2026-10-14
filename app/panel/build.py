"""Builds the didactic panel and checks that registry, annotations and code agree.

    python -m app.cli build-panel [--out build/panel/index.html] [--check] [--sem-dados]

The panel is one self-contained HTML page. Its content comes from:
  * the repository itself (app/panel/facts.py): tables, columns, constraints, agent runs, steps,
    queue types, prompt versions, workflows, environment variable names, CLI, routes, tests,
    decisions, stale references;
  * app/agents/registry.yaml: which code implements each stage, agent and gate;
  * docs/panel/anotaciones.yaml: purpose, known failures, runbook, glossary;
  * optionally, read-only aggregates from the database (app/panel/live.py).
"""
from __future__ import annotations

import html as _html
import math
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from ..config import ROOT
from . import facts as F
from .source import Source, is_path_ref

REGISTRY = "app/agents/registry.yaml"
ANNOTATIONS = "docs/panel/anotaciones.yaml"
GENERATOR = "app/panel/build.py"

UI = {
    "title": {"es": "Cómo funciona Aletheia News", "en": "How Aletheia News works"},
    "subtitle": {"es": "Panel didáctico para quien toma el proyecto. Generado desde el código; lo que no existe se muestra como falta.",
                 "en": "Teaching panel for whoever takes over the project. Generated from the code; what does not exist is shown as missing."},
    "vision": {"es": "Visión general", "en": "Overview"},
    "pipeline": {"es": "Mapa del pipeline", "en": "Pipeline map"},
    "agentes": {"es": "Agentes", "en": "Agents"},
    "compuertas": {"es": "Compuertas", "en": "Gates"},
    "cola": {"es": "Cola y autonomía", "en": "Queue and autonomy"},
    "datos": {"es": "Modelo de datos", "en": "Data model"},
    "chat": {"es": "Chat", "en": "Chat"},
    "infra": {"es": "Infraestructura", "en": "Infrastructure"},
    "runbook": {"es": "Operación semanal", "en": "Weekly operation"},
    "costos": {"es": "Costos y observabilidad", "en": "Costs and observability"},
    "extender": {"es": "Cómo extender", "en": "How to extend"},
    "deuda": {"es": "Discrepancias y deuda", "en": "Discrepancies and debt"},
    "glosario": {"es": "Glosario", "en": "Glossary"},
    "implementado": {"es": "implementado", "en": "implemented"},
    "parcial": {"es": "parcial", "en": "partial"},
    "especificado_no_implementado": {"es": "falta", "en": "missing"},
    "agente": {"es": "agente", "en": "agent"},
    "determinista": {"es": "código", "en": "code"},
    "humano": {"es": "editor", "en": "editor"},
    "search": {"es": "Buscar agente, tabla, compuerta, archivo…", "en": "Search agent, table, gate, file…"},
    "no_en": {"es": "", "en": "untranslated"},
}

VIEWS = ["vision", "pipeline", "agentes", "compuertas", "cola", "datos", "chat", "infra", "runbook", "costos",
         "extender", "deuda", "glosario"]


# ------------------------------------------------------------------------ loading
def load(src: Source) -> tuple[dict, dict]:
    reg = yaml.safe_load(src.text(REGISTRY) or "{}") or {}
    ann = yaml.safe_load(src.text(ANNOTATIONS) or "{}") or {}
    return reg, ann


def _refs_in(obj, trail=""):
    """Every value under a key named ref / refs / codigo / programacion / pruebas / prompt / ... in a tree."""
    keys = {"ref", "refs", "codigo", "programacion", "pruebas", "prompt", "prompt_version", "llamada", "spec"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{trail}.{k}" if trail else str(k)
            if k in keys:
                for r in (v if isinstance(v, list) else [v]):
                    if isinstance(r, str):
                        yield here, r
            else:
                yield from _refs_in(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _refs_in(v, f"{trail}[{i}]")


# ------------------------------------------------------------------------- check
def check(src: Source | None = None, f: dict | None = None, reg: dict | None = None, ann: dict | None = None) -> list[str]:
    src = src or Source()
    if reg is None or ann is None:
        reg, ann = load(src)
    f = f or F.collect(src)
    problems: list[str] = []
    if not reg:
        return [f"{REGISTRY} vacío o ilegible"]
    if not ann:
        return [f"{ANNOTATIONS} vacío o ilegible"]

    for origin, tree in ((REGISTRY, reg), (ANNOTATIONS, ann)):
        for where, ref in _refs_in(tree):
            if not is_path_ref(ref):
                continue
            r = src.resolve(ref)
            if not r.ok:
                problems.append(f"{origin} · {where}: '{ref}' — {r.why}")

    etapas = {e["id"]: e for e in reg.get("etapas", [])}
    agentes = {a["id"]: a for a in reg.get("agentes", [])}
    compuertas = {c["id"]: c for c in reg.get("compuertas", [])}
    run_tipos = {e.get("run_tipo") for e in etapas.values() if e.get("run_tipo")}
    pasos = {p for e in etapas.values() for p in e.get("pasos_registrados", [])}
    cola_reg = {c for x in list(etapas.values()) + list(agentes.values()) for c in x.get("cola", [])}
    versions = {a.get("prompt_version") for a in agentes.values()}

    for r in f["agent"]["runs"]:
        if r["tipo"] not in run_tipos:
            problems.append(f"Código: agent_run '{r['tipo']}' ({r['path']}:{r['line']}) sin etapa en {REGISTRY}")
    for st in f["agent"]["steps"]:
        if st["name"] not in pasos:
            problems.append(f"Código: paso '{st['name']}' ({st['path']}:{st['line']}) no figura en pasos_registrados")
    for rv in f["agent"]["reviews"]:
        if rv["tipo"] not in cola_reg:
            problems.append(f"Código: tipo de cola '{rv['tipo']}' ({rv['path']}:{rv['line']}) no figura en {REGISTRY}")
        if rv["tipo"] not in (ann.get("cola") or {}):
            problems.append(f"Código: tipo de cola '{rv['tipo']}' sin anotación en {ANNOTATIONS} (cola)")
    for pv in f["prompt_versions"]:
        if pv["ref"] not in versions:
            problems.append(f"Código: versión de prompt {pv['ref']} = '{pv['value']}' sin agente en {REGISTRY}")

    names = ann.get("nombres") or {}
    for e in etapas.values():
        for dep in e.get("sigue_a", []):
            if dep not in etapas:
                problems.append(f"{REGISTRY}: etapa {e['id']} sigue a '{dep}', que no existe")
        for g in e.get("compuertas", []):
            if g not in compuertas:
                problems.append(f"{REGISTRY}: etapa {e['id']} usa compuerta '{g}', que no existe")
        for a in e.get("agentes", []):
            if a not in agentes:
                problems.append(f"{REGISTRY}: etapa {e['id']} usa agente '{a}', que no existe")
        if e.get("estado") != "especificado_no_implementado" and not e.get("codigo"):
            problems.append(f"{REGISTRY}: etapa {e['id']} marcada {e.get('estado')} sin código")
        if not ((ann.get("etapas") or {}).get(e["id"]) or {}).get("proposito", {}).get("es"):
            problems.append(f"{ANNOTATIONS}: etapa {e['id']} sin propósito")
        if e["id"] not in names:
            problems.append(f"{ANNOTATIONS}: etapa {e['id']} sin nombre")
    for a in agentes.values():
        if a.get("etapa") not in etapas:
            problems.append(f"{REGISTRY}: agente {a['id']} en etapa inexistente '{a.get('etapa')}'")
        if not ((ann.get("agentes") or {}).get(a["id"]) or {}).get("tarea", {}).get("es"):
            problems.append(f"{ANNOTATIONS}: agente {a['id']} sin tarea")
        if a["id"] not in names:
            problems.append(f"{ANNOTATIONS}: agente {a['id']} sin nombre")
        for g in a.get("compuertas", []):
            if g not in compuertas:
                problems.append(f"{REGISTRY}: agente {a['id']} usa compuerta '{g}', que no existe")
        if a.get("estado") == "implementado" and not (a.get("prompt") and a.get("prompt_version")):
            problems.append(f"{REGISTRY}: agente implementado {a['id']} sin prompt o versión")
    for g in compuertas.values():
        if not ((ann.get("compuertas") or {}).get(g["id"]) or {}).get("regla", {}).get("es"):
            problems.append(f"{ANNOTATIONS}: compuerta {g['id']} sin regla")
        if g["id"] not in names:
            problems.append(f"{ANNOTATIONS}: compuerta {g['id']} sin nombre")
    for k in (ann.get("cola") or {}):
        if k not in cola_reg:
            problems.append(f"{ANNOTATIONS}: tipo de cola anotado '{k}' que ningún agente usa")
    for t in (ann.get("tablas") or {}):
        if t not in f["models"]["tables"]:
            problems.append(f"{ANNOTATIONS}: invariante de tabla inexistente '{t}'")
    for layer in f["models"]["layers"]:
        if layer["slug"] == "otros":
            problems.append(f"app/models.py: tablas sin capa ({', '.join(layer['tables'])})")
    return problems


# ----------------------------------------------------------------------- helpers
def _usage_for(f: dict, refs: list[str]) -> dict:
    w, r = set(), set()
    for ref in refs:
        for key, u in f["usage"].items():
            if key == ref or key.startswith(ref + "."):
                w |= u["writes"]
                r |= u["reads"]
    return {"writes": sorted(w), "reads": sorted(r - w)}


def _owner_stage(reg: dict, ref_key: str) -> str | None:
    path, _, fn = ref_key.partition("::")
    top = fn.split(".")[0]
    for e in reg.get("etapas", []):
        for c in e.get("codigo", []) + e.get("programacion", []):
            cp, _, cs = c.partition("::")
            if cp == path and (not cs or cs == top or cs == fn):
                return e["id"]
    return None


def _tests(src: Source, f: dict, refs: list[str]) -> list[dict]:
    out = []
    for ref in refs:
        if ref in f["tests"]:
            t = f["tests"][ref]
            out.append({"name": t["name"], "path": t["path"], "url": src.url(t["path"], t["line"], t["end"]),
                        "code": src.snippet(ref, 30), "pytest": True})
        else:
            out.append({"name": ref.split("::")[-1], "path": ref.split("::")[0], "url": src.link(ref)["url"], "code": "",
                        "pytest": False})
    return out


def _spec(src: Source, items: list[str]) -> list[dict]:
    return [src.link(s) | {"prose": False} if is_path_ref(s) else {"label": s, "prose": True} for s in items or []]


def _model_config(f: dict, role: str) -> list[dict]:
    """Where the model for a role is set: Render, workflows, code default."""
    chain = {"chat": ["CHAT_MODEL"], "agent": ["AGENT_MODEL", "CHAT_MODEL"],
             "verifier": ["VERIFIER_MODEL", "AGENT_MODEL", "CHAT_MODEL"]}[role]
    env = {r["name"]: r for r in f["env"]}
    out = []
    for var in chain:
        r = env.get(var)
        if not r:
            continue
        if r["render"] not in (None, "secret"):
            out.append({"var": var, "value": r["render"], "where": "render.yaml"})
        for wf, v in r["workflows"].items():
            if v != "secret":
                out.append({"var": var, "value": v, "where": wf.split("/")[-1]})
        if r["default"]:
            out.append({"var": var, "value": r["default"].strip('"'), "where": "app/config.py (por defecto)"})
    return out


# ------------------------------------------------------------------------ diagrams
def _esc(s: str) -> str:
    return _html.escape(str(s), quote=True)


def pipeline_svg(reg: dict, names: dict) -> str:
    W, H, DX, DY, PAD = 168, 54, 194, 82, 16
    etapas = reg.get("etapas", [])
    pos = {e["id"]: tuple(e.get("pos", [0, 0])) for e in etapas}
    cols = max(p[0] for p in pos.values()) + 1
    rows = max(p[1] for p in pos.values()) + 1
    width, height = PAD * 2 + (cols - 1) * DX + W, PAD * 2 + (rows - 1) * DY + H + 8
    xy = {k: (PAD + c * DX, PAD + r * DY) for k, (c, r) in pos.items()}
    parts = [f'<svg class="pipe" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
             f'aria-labelledby="pipe-t"><title id="pipe-t">Pipeline</title>'
             '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="6" class="hatch"/></pattern>'
             '<marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0,0 L8,4 L0,8 z" class="arrowhead"/></marker></defs>']
    for e in etapas:
        for dep in e.get("sigue_a", []):
            if dep not in xy:
                continue
            (x1, y1), (x2, y2) = xy[dep], xy[e["id"]]
            if x2 - x1 > DX and y2 < y1:
                # into a higher row: run along the source's row, then up into the target's bottom
                sx, sy, tx, ty = x1 + W, y1 + H / 2, x2 + W / 2, y2 + H
                d = f"M{sx},{sy} C{tx},{sy} {tx},{sy} {tx},{ty + 2}"
            elif x2 > x1:
                sx, sy, tx, ty = x1 + W, y1 + H / 2, x2, y2 + H / 2
                mx = (sx + tx) / 2
                d = f"M{sx},{sy} C{mx},{sy} {mx},{ty} {tx - 2},{ty}"
            else:
                sx, sy, tx, ty = x1 + W / 2, y1 + H, x2 + W / 2, y2
                d = f"M{sx},{sy} C{sx},{sy + 30} {tx},{ty - 30} {tx},{ty - 2}"
            dashed = " pending" if e.get("estado") == "especificado_no_implementado" else ""
            parts.append(f'<path d="{d}" class="edge{dashed}" marker-end="url(#arr)"/>')
    for e in etapas:
        x, y = xy[e["id"]]
        st = e.get("estado", "implementado")
        label = names.get(e["id"], {})
        parts.append(f'<a href="#etapa-{_esc(e["id"])}" class="node {st}" data-stage="{_esc(e["id"])}">'
                     f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="4"/>'
                     + (f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="4" fill="url(#hatch)" class="hatchfill"/>'
                        if st == "especificado_no_implementado" else "")
                     + f'<text x="{x + 10}" y="{y + 22}" class="nl i18n" data-l="es">{_esc(label.get("es", e["id"]))}</text>'
                     f'<text x="{x + 10}" y="{y + 22}" class="nl i18n" data-l="en">{_esc(label.get("en", e["id"]))}</text>'
                     f'<text x="{x + 10}" y="{y + 41}" class="ns i18n" data-l="es">{_esc(UI[st]["es"])} · {_esc(UI[e.get("ejecutor", "determinista")]["es"])}</text>'
                     f'<text x="{x + 10}" y="{y + 41}" class="ns i18n" data-l="en">{_esc(UI[st]["en"])} · {_esc(UI[e.get("ejecutor", "determinista")]["en"])}</text>'
                     + "</a>")
    parts.append("</svg>")
    return "".join(parts)


def layers_svg(f: dict) -> str:
    layers = [l["slug"] for l in f["models"]["layers"]]
    tables = f["models"]["tables"]
    layer_of = {t: d["layer"] for t, d in tables.items()}
    edges: dict[tuple[str, str], int] = {}
    for t, d in tables.items():
        for fk in d["fks"]:
            a, b = layer_of.get(t), layer_of.get(fk)
            if a and b and a != b:
                key = tuple(sorted((a, b), key=layers.index))
                edges[key] = edges.get(key, 0) + 1
    gap, top, W = 84, 150, 84 * (len(layers) - 1) + 120
    x = {l: 60 + i * gap for i, l in enumerate(layers)}
    parts = [f'<svg class="arcs" viewBox="0 0 {W} {top + 60}" width="{W}" height="{top + 60}" role="img" aria-labelledby="arc-t">'
             '<title id="arc-t">Capas y claves foráneas entre capas</title>']
    for (a, b), n in sorted(edges.items(), key=lambda kv: kv[1]):
        x1, x2 = x[a], x[b]
        r = (x2 - x1) / 2
        parts.append(f'<path d="M{x1},{top} A{r},{min(r, top - 14)} 0 0 1 {x2},{top}" class="arc" '
                     f'stroke-width="{1 + math.log2(n + 1):.1f}"><title>{a} ↔ {b}: {n} FK</title></path>')
    for l in layers:
        n = sum(1 for d in tables.values() if d["layer"] == l)
        parts.append(f'<a href="#capa-{l}"><circle cx="{x[l]}" cy="{top}" r="{5 + n}" class="dot"/>'
                     f'<text x="{x[l]}" y="{top + 26 + n}" text-anchor="middle" class="al">{l}</text>'
                     f'<text x="{x[l]}" y="{top + 40 + n}" text-anchor="middle" class="as">{n}</text></a>')
    parts.append("</svg>")
    return "".join(parts)


def infra_svg(f: dict) -> str:
    wf = {w["name"]: w for w in f["workflows"]}
    env = {r["name"]: r for r in f["env"]}
    svc = f["render"][0] if f["render"] else {}
    nodes = {
        "readers": (16, 115, "Lectores · editor", "Readers · editor"),
        "render": (300, 30, f"Render · {svc.get('plan') or '?'} · {svc.get('region') or '?'}", f"Render · {svc.get('plan') or '?'} · {svc.get('region') or '?'}"),
        "actions": (300, 200, "GitHub Actions", "GitHub Actions"),
        "neon": (640, 30, "Neon · Postgres", "Neon · Postgres"),
        "model": (640, 200, "Proveedor de modelos", "Model provider"),
    }
    sub = {
        "render": "sitio · /api/chat · /admin",
        "actions": " · ".join(f"{w['name']}" for w in f["workflows"]),
        "neon": "DATABASE_URL",
        "model": next((env[v]["render"] for v in ("CHAT_BASE_URL",) if v in env and env[v]["render"]), "") or "",
        "readers": "HTTPS",
    }
    edges = [("readers", "render", "HTTPS")]
    if env.get("DATABASE_URL", {}).get("render") == "secret":
        edges.append(("render", "neon", "DATABASE_URL"))
    if any("DATABASE_URL" in w["secrets"] for w in f["workflows"]):
        edges.append(("actions", "neon", "DATABASE_URL"))
    if env.get("CHAT_API_KEY", {}).get("render") == "secret":
        edges.append(("render", "model", "chat"))
    if any("CHAT_API_KEY" in w["secrets"] for w in f["workflows"]):
        edges.append(("actions", "model", "agentes"))
    W, H = 210, 62
    parts = ['<svg class="infra" viewBox="0 0 866 282" width="866" height="282" role="img" aria-labelledby="inf-t">'
             '<title id="inf-t">Qué corre dónde</title><defs><marker id="arr2" viewBox="0 0 8 8" refX="7" refY="4" '
             'markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="arrowhead"/></marker></defs>']
    for a, b, lbl in edges:
        (x1, y1, *_), (x2, y2, *_) = nodes[a], nodes[b]
        sx, sy = x1 + W, y1 + H / 2
        tx, ty = x2, y2 + H / 2
        mx = (sx + tx) / 2
        if abs(ty - sy) < 1:
            lx, ly, anchor = sx + 12, sy - 7, "start"
        elif ty > sy:
            lx, ly, anchor = tx - 10, ty - 8, "end"
        else:
            lx, ly, anchor = tx - 10, ty + 17, "end"
        parts.append(f'<path d="M{sx},{sy} C{mx},{sy} {mx},{ty} {tx - 2},{ty}" class="edge" marker-end="url(#arr2)"/>'
                     f'<text x="{lx}" y="{ly}" class="el" text-anchor="{anchor}">{_esc(lbl)}</text>')
    for k, (x, y, es, en) in nodes.items():
        parts.append(f'<g class="node implementado"><rect x="{x}" y="{y}" width="{W}" height="{H}" rx="4"/>'
                     f'<text x="{x + 10}" y="{y + 24}" class="nl i18n" data-l="es">{_esc(es)}</text>'
                     f'<text x="{x + 10}" y="{y + 24}" class="nl i18n" data-l="en">{_esc(en)}</text>'
                     f'<text x="{x + 10}" y="{y + 44}" class="ns">{_esc(sub.get(k, ""))[:42]}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------------ context
def build_context(src: Source, f: dict, reg: dict, ann: dict, live: dict | None) -> dict:
    names = ann.get("nombres") or {}
    a_et, a_ag, a_co = ann.get("etapas") or {}, ann.get("agentes") or {}, ann.get("compuertas") or {}
    a_cola = ann.get("cola") or {}
    pv = {p["ref"]: p for p in f["prompt_versions"]}
    run_budget = {r["tipo"]: r["budget_cents"] for r in f["agent"]["runs"]}
    wf_by_file = {w["file"]: w for w in f["workflows"]}
    live_runs = {r["tipo"]: r for r in (live or {}).get("runs", [])} if live and live.get("ok") else {}
    live_steps = {r["agente"]: r for r in (live or {}).get("steps", [])} if live and live.get("ok") else {}
    live_queue = {r["tipo"]: r for r in (live or {}).get("queue", [])} if live and live.get("ok") else {}
    cli = {c["name"]: c for c in f["cli"]}

    def consts(refs):
        seen, out = set(), []
        for ref in refs:
            path = ref.split("::")[0]
            if path.endswith(".py") and path not in seen:
                seen.add(path)
                for c in F.constants(src, path):
                    out.append(c | {"url": src.url(path, c["line"]), "path": path})
        return out

    stages = []
    for e in reg.get("etapas", []):
        a = a_et.get(e["id"], {})
        refs = e.get("codigo", [])
        sched = []
        progs = list(e.get("programacion", []))
        if any(p.startswith("app/pipeline/weekly.py") for p in progs):
            progs += [w["file"] for w in f["workflows"] if any("app.pipeline.weekly" in r for r in w["runs"])
                      and w["file"] not in progs]
        for p in progs:
            path = p.split("::")[0]
            if path in wf_by_file:
                w = wf_by_file[path]
                sched.append({"kind": "workflow", "link": src.link(p), "crons": w["crons"], "dispatch": w["dispatch"]})
            else:
                sched.append({"kind": "code", "link": src.link(p)})
        cmd = None
        if e.get("cli"):
            name = e["cli"].split()[-1]
            cmd = {"text": e["cli"], "help": (cli.get(name) or {}).get("help"), "args": (cli.get(name) or {}).get("args", [])}
        stages.append({
            **e, "name": names.get(e["id"], {"es": e["id"]}), "ann": a,
            "code": [src.link(r) for r in refs], "sched": sched, "cmd": cmd,
            "usage": _usage_for(f, refs),
            "tests": _tests(src, f, e.get("pruebas", [])),
            "spec": _spec(src, e.get("spec", [])),
            "gates": [{"id": g, "name": names.get(g, {"es": g})} for g in e.get("compuertas", [])],
            "agents": [{"id": x, "name": names.get(x, {"es": x})} for x in e.get("agentes", [])],
            "queue": [{"tipo": q, **a_cola.get(q, {})} for q in e.get("cola", [])],
            "budget": run_budget.get(e.get("run_tipo")),
            "consts": consts(refs),
            "live": live_runs.get(e.get("run_tipo")) if e.get("run_tipo") else None,
            "fallos": [x | {"link": src.link(x["ref"]) if x.get("ref") else None} for x in a.get("fallos", [])],
        })

    agents = []
    for ag in reg.get("agentes", []):
        role = ag.get("rol_modelo")
        cfg = _model_config(f, "chat" if role == "chat" else ("verifier" if role == "verifier" else "agent")) if role else []
        agents.append({
            **ag, "name": names.get(ag["id"], {"es": ag["id"]}), "ann": a_ag.get(ag["id"], {}),
            "prompt_link": src.link(ag["prompt"]) if ag.get("prompt") else None,
            "prompt_text": src.snippet(ag["prompt"], 80) if ag.get("prompt") else "",
            "version": (pv.get(ag.get("prompt_version")) or {}).get("value"),
            "version_link": src.link(ag["prompt_version"]) if ag.get("prompt_version") else None,
            "call_link": src.link(ag["llamada"]) if ag.get("llamada") else None,
            "models": cfg,
            "gates": [{"id": g, "name": names.get(g, {"es": g})} for g in ag.get("compuertas", [])],
            "queue": ag.get("cola", []),
            "spec": _spec(src, ag.get("spec", [])),
            "live": live_steps.get(ag.get("paso_registrado") or ""),
        })

    gates = []
    for g in reg.get("compuertas", []):
        code = []
        for r in g.get("codigo", []):
            link = src.link(r)
            sym = r.split("::")[1] if "::" in r else ""
            c = F.callers(src, r) if sym and sym[:1].islower() else None
            code.append(link | {"callable": c is not None,
                                "callers_app": len(c["app"]) if c else 0, "callers_tests": len(c["tests"]) if c else 0,
                                "callers": [{"label": f"{x['path']}:{x['line']}" + (f" · {x['func']}" if x["func"] else ""),
                                             "url": src.url(x["path"], x["line"])} for x in (c["app"] if c else [])[:6]]})
        unwired = [c for c in code if c["callable"] and c["callers_app"] == 0]
        gates.append({**g, "name": names.get(g["id"], {"es": g["id"]}), "ann": a_co.get(g["id"], {}), "code": code,
                      "tests": _tests(src, f, g.get("pruebas", [])), "unwired": unwired,
                      "stages": [s["id"] for s in reg.get("etapas", []) if g["id"] in s.get("compuertas", [])]})

    # queue: every type the code can emit
    q_types = []
    seen = set()
    for rv in f["agent"]["reviews"]:
        if rv["tipo"] in seen:
            continue
        seen.add(rv["tipo"])
        stage = _owner_stage(reg, f"{rv['path']}::{rv['func']}")
        q_types.append({"tipo": rv["tipo"], "ann": a_cola.get(rv["tipo"], {}), "link": src.url(rv["path"], rv["line"]),
                        "where": f"{rv['path']}:{rv['line']}", "stage": stage, "live": live_queue.get(rv["tipo"])})

    # data model
    tables = f["models"]["tables"]
    writers: dict[str, list[dict]] = {t: [] for t in tables}
    for key, u in f["usage"].items():
        for t in u["writes"]:
            if t in writers:
                writers[t].append({"key": key, "stage": _owner_stage(reg, key),
                                   "url": src.link(key.split(".")[0] if "." in key.split("::")[1] else key)["url"]})
    referenced_by: dict[str, list[str]] = {t: [] for t in tables}
    for t, d in tables.items():
        for fk in d["fks"]:
            if fk in referenced_by:
                referenced_by[fk].append(t)
    layers = []
    for l in f["models"]["layers"]:
        layers.append({"slug": l["slug"], "tables": [
            tables[t] | {"url": src.url("app/models.py", tables[t]["line"], tables[t]["end"]),
                         "writers": sorted(writers[t], key=lambda w: w["key"]),
                         "referenced_by": sorted(referenced_by[t]),
                         "inv": (ann.get("tablas") or {}).get(t)} for t in l["tables"]]})
    never_written = sorted(t for t, w in writers.items() if not [x for x in w if not x["key"].startswith("app/seed/")])

    # chat flow
    chat_flow = [
        ("app/main.py::chat", {"es": "Límite por IP; respuesta por SSE", "en": "Per-IP limit; SSE response"}),
        ("app/chat/service.py::handle", {"es": "Sesión sin identificador persistente", "en": "Session without a persistent id"}),
        ("app/chat/service.py::retrieve", {"es": "Recuperación BM25 sobre la edición, con hechos del encuadre opuesto (D19)", "en": "BM25 retrieval over the edition, with facts from the opposite framing (D19)"}),
        ("app/chat/prompt.py::render_context", {"es": "Contexto: idioma, modo, fecha de corte, documentos", "en": "Context: language, mode, cutoff date, documents"}),
        ("app/chat/service.py::call_model", {"es": "Modelo (proveedor configurable)", "en": "Model (configurable provider)"}),
        ("app/chat/verify.py::verify_answer", {"es": "El código verifica cada segmento", "en": "Code verifies every segment"}),
        ("app/chat/prompt.py::repair_message", {"es": "Si falla: motivos al modelo, un reintento", "en": "On failure: reasons back to the model, one retry"}),
        ("app/chat/service.py::_fallback", {"es": "Si vuelve a fallar: afirmaciones más cercanas", "en": "If it fails again: nearest claims"}),
    ]
    chat = {"flow": [{"link": src.link(r), "text": t} for r, t in chat_flow],
            "rules": [x | {"link": src.link(x["ref"]), "counts": {c: f["evals"]["categories"].get(c, 0) for c in x.get("eval", [])}}
                      for x in (ann.get("chat") or {}).get("reglas", [])],
            "resultados": (ann.get("chat") or {}).get("resultados"), "evals": f["evals"],
            "eval_link": src.url("evals/chat_eval.jsonl")}

    # discrepancies
    decisions = f["decisions"]
    dec_url = lambda d: src.url("docs/decisiones.md", d["line"])  # noqa: E731
    gaps_impl = [s for s in stages if s["estado"] == "especificado_no_implementado"]
    gaps_partial = [s for s in stages if s["estado"] == "parcial"]
    agents_missing = [a for a in agents if a.get("estado") == "especificado_no_implementado"]
    unwired = [(g, u) for g in gates for u in g["unwired"]]
    status_table = f["agentes_md"].get("Estado de implementación", [])
    deuda = {
        "stages_missing": gaps_impl, "stages_partial": gaps_partial, "agents_missing": agents_missing,
        "hallazgos": [h | {"links": [src.link(r) for r in h.get("refs", [])]} for h in ann.get("hallazgos", [])],
        "decisions_open": [d | {"url": dec_url(d)} for d in decisions if d["open"]],
        "decisions_all": [d | {"url": dec_url(d)} for d in decisions],
        "stale": [x | {"url": src.url(x["path"], x["line"])} for x in f["stale"]],
        "hardcoded": [x | {"url": src.url(x["path"], x["line"])} for x in f["hardcoded_country"]],
        "defaults": [x | {"url": src.url(x["code"][0]["path"], x["code"][0]["line"]) if x["code"] else None}
                     for x in f["default_vs_deployed"]],
        "unwired": unwired, "never_written": never_written,
        "status_table": status_table, "agentes_url": src.url("docs/agentes.md"),
        "fly_toml": f["present"].get("fly.toml"),
    }

    # infrastructure
    env_rows = []
    for r in f["env"]:
        env_rows.append(r | {"code_links": [{"label": f"{c['path']}:{c['line']}", "url": src.url(c["path"], c["line"])}
                                            for c in r["code"][:3]]})
    infra = {"svg": Markup(infra_svg(f)), "services": [s | {"link": src.link(s["ref"])} for s in (ann.get("infra") or {}).get("servicios", [])],
             "render": f["render"], "workflows": [w | {"url": src.url(w["file"])} for w in f["workflows"]],
             "env": env_rows, "limits": [x | {"link": src.link(x["ref"]) if x.get("ref") else None}
                                          for x in (ann.get("infra") or {}).get("limites", [])],
             "migrations": [m | {"url": src.url(m["file"])} for m in f["migrations"]]}

    # runbook, extension, glossary
    runbook = [r | {"links": [src.link(x) for x in r.get("refs", [])]} for r in ann.get("runbook", [])]
    extender = [x | {"links": [src.link(r) for r in x.get("refs", [])]} for x in ann.get("extender", [])]
    glosario = [g | {"link": src.link(g["ref"])} for g in ann.get("glosario", [])]
    routes = [r | {"url": src.url(r["file"], r["line"])} for r in f["routes"]]
    cli_rows = [c | {"url": src.url("app/cli.py", c["line"])} for c in f["cli"]]

    vision = ann.get("vision") or {}
    vis = {
        **vision,
        "principios": [p | {"link": src.link(p["ref"])} for p in vision.get("principios", [])],
        "cadencia": [c | {"link": src.link(c["ref"])} for c in vision.get("cadencia", [])],
        "recorrido": [r | {"link": src.link(r["ref"])} for r in vision.get("recorrido", [])],
        "regla_link": src.link(vision.get("regla_central_ref", "docs/agentes.md")),
        "counts": {
            "etapas": len(stages),
            "impl": sum(1 for s in stages if s["estado"] == "implementado"),
            "parcial": len(gaps_partial), "falta": len(gaps_impl),
            "agentes_impl": sum(1 for a in agents if a.get("estado") == "implementado"),
            "agentes_falta": len(agents_missing), "compuertas": len(gates),
            "tablas": len(tables), "capas": len(layers), "pruebas": len(f["tests"]),
            "workflows": len(f["workflows"]), "decisiones": len(decisions),
            "abiertas": len(deuda["decisions_open"]),
        },
    }

    autonomy_rows = f["agentes_md"].get("Niveles de autonomía", [])
    current_level = None
    if live and live.get("ok") and live.get("autonomy"):
        current_level = live["autonomy"]
    autonomy = {**(ann.get("autonomia") or {}), "rows": autonomy_rows, "current": current_level,
                "link": src.link((ann.get("autonomia") or {}).get("ref", "docs/agentes.md")),
                "admin": src.link("app/admin.py::set_autonomy"), "model": src.link("app/models.py::Country")}

    # search index
    index = []
    for s in stages:
        index.append({"l": s["name"].get("es"), "e": s["name"].get("en", ""), "k": "etapa", "h": f"#etapa-{s['id']}"})
    for a in agents:
        index.append({"l": a["name"].get("es"), "e": a["name"].get("en", ""), "k": "agente", "h": f"#agente-{a['id']}"})
    for g in gates:
        index.append({"l": g["name"].get("es"), "e": g["name"].get("en", ""), "k": "compuerta", "h": f"#compuerta-{g['id']}"})
    for t in tables:
        index.append({"l": t, "e": t, "k": "tabla", "h": f"#tabla-{t}"})
    for q in q_types:
        index.append({"l": q["tipo"], "e": q["tipo"], "k": "cola", "h": "#cola"})
    for r in env_rows:
        index.append({"l": r["name"], "e": r["name"], "k": "env", "h": "#env"})
    for g in glosario:
        index.append({"l": g["termino"], "e": g["termino"], "k": "glosario", "h": "#glosario"})
    for w in f["workflows"]:
        index.append({"l": w["file"], "e": w["file"], "k": "workflow", "h": "#workflows"})
    files = sorted({c["path"] for s in stages for c in s["code"] if c["ok"]} | {c["path"] for g in gates for c in g["code"] if c["ok"]})
    for p in files:
        index.append({"l": p, "e": p, "k": "archivo", "h": src.url(p)})

    return {
        "ui": UI, "views": VIEWS, "vision": vis, "stages": stages, "agents": agents, "gates": gates,
        "queue": q_types, "autonomy": autonomy, "layers": layers, "chat": chat, "infra": infra,
        "runbook": runbook, "cli": cli_rows, "routes": routes, "extender": extender, "deuda": deuda,
        "glosario": glosario, "live": live, "ann_meta": ann.get("meta") or {},
        "pipeline_svg": Markup(pipeline_svg(reg, names)), "layers_svg": Markup(layers_svg(f)),
        "commit": src.commit, "commit_short": src.commit[:7], "commit_url": f"{src.repo_url}/tree/{src.commit}",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "generator_url": src.url(GENERATOR), "registry_url": src.url(REGISTRY), "annotations_url": src.url(ANNOTATIONS),
        "repo_url": src.repo_url, "index": index, "names": names,
        "d43": next((d for d in decisions if d["id"] == "D43"), None),
        "d43_url": next((dec_url(d) for d in decisions if d["id"] == "D43"), None),
        "present": f["present"],
    }


def render(ctx: dict) -> str:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    return env.get_template("panel.html").render(**ctx)


def build_panel(out: Path | str | None = None, with_live: bool = True, src: Source | None = None) -> tuple[str, list[str]]:
    """Returns (html, problems). Writes the file if `out` is given."""
    src = src or Source(ROOT)
    reg, ann = load(src)
    if reg.get("repositorio"):
        src.repo_url = reg["repositorio"].rstrip("/")
    f = F.collect(src)
    problems = check(src, f, reg, ann)
    live = None
    if with_live:
        from .live import gather
        live = gather()
    ctx = build_context(src, f, reg, ann, live)
    ctx["problems"] = problems
    html = render(ctx)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
    return html, problems
