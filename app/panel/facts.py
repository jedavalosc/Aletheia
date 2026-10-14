"""Repository introspection for the panel. Pure: reads files, never the database or the
environment's secret values. Each function returns plain data the template can render."""
from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict

import yaml

from .source import Source

SECRET_NAME = re.compile(r"(_KEY$|PASSWORD|SECRET|_TOKEN$|DATABASE_URL)")
LAYER_RE = re.compile(r"^# -+ ([a-z][a-z ]*)$")
GENERIC_NAMES = {"run", "merge", "gate", "get", "step", "review", "llm", "answer", "handle", "render", "main", "chat",
                 "collect", "group", "extract", "queue", "page", "status", "scan"}


def _const(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        if isinstance(node, ast.BinOp):
            try:
                return eval(compile(ast.Expression(node), "<const>", "eval"), {"__builtins__": {}})  # noqa: S307 - literals only
            except Exception:  # noqa: BLE001
                return None
        return None


def _walk_with_func(tree: ast.Module):
    """Yield (node, enclosing function name) for every node."""
    stack: list[tuple[ast.AST, str | None]] = [(tree, None)]
    while stack:
        node, fn = stack.pop()
        for child in ast.iter_child_nodes(node):
            name = fn
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = child.name if fn is None else f"{fn}.{child.name}"
            elif isinstance(child, ast.ClassDef):
                name = child.name
            yield child, name
            stack.append((child, name))


# --------------------------------------------------------------------------- models
def models(src: Source) -> dict:
    path = "app/models.py"
    mod = src.module(path)
    if mod is None:
        return {"layers": [], "tables": {}, "class_to_table": {}}
    marks = [(i + 1, m.group(1).strip()) for i, line in enumerate(mod.lines) if (m := LAYER_RE.match(line.strip()))]
    tables, class_to_table = {}, {}
    layers: dict[str, list[str]] = defaultdict(list)
    for node in mod.tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        tname = None
        cols, checks, fks = [], [], []
        for sub in node.body:
            if isinstance(sub, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in sub.targets):
                tname = _const(sub.value)
            if isinstance(sub, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__table_args__" for t in sub.targets):
                for call in ast.walk(sub.value):
                    if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "CheckConstraint":
                        expr = _const(call.args[0]) if call.args else ""
                        name = next((_const(k.value) for k in call.keywords if k.arg == "name"), None)
                        checks.append({"name": name, "expr": expr})
            if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name) and isinstance(sub.value, ast.Call):
                fname = getattr(sub.value.func, "id", "") or getattr(sub.value.func, "attr", "")
                if fname == "relationship":
                    continue
                typ = ast.unparse(sub.annotation)
                typ = re.sub(r"^Mapped\[(.*)\]$", r"\1", typ)
                fk = None
                for call in ast.walk(sub.value):
                    if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "ForeignKey" and call.args:
                        target = _const(call.args[0]) or ""
                        fk = target.split(".")[0]
                pk = any(k.arg == "primary_key" and _const(k.value) is True for k in sub.value.keywords)
                line = mod.lines[sub.lineno - 1]
                comment = line.split("  # ", 1)[1].strip() if "  # " in line else ""
                cols.append({"name": sub.target.id, "type": typ, "fk": fk, "pk": pk, "comment": comment, "line": sub.lineno})
                if fk:
                    fks.append(fk)
        if not tname:
            continue
        layer = next((name for ln, name in reversed(marks) if ln < node.lineno), "otros")
        doc = ast.get_docstring(node) or ""
        tables[tname] = {"name": tname, "cls": node.name, "line": node.lineno, "end": node.end_lineno, "doc": doc,
                         "columns": cols, "checks": checks, "fks": sorted(set(fks)), "layer": layer}
        class_to_table[node.name] = tname
        layers[layer].append(tname)
    order = []
    for _, name in marks:
        if name in layers and name not in order:
            order.append(name)
    for name in layers:
        if name not in order:
            order.append(name)
    return {"layers": [{"slug": n, "tables": layers[n]} for n in order], "tables": tables, "class_to_table": class_to_table}


def table_usage(src: Source, class_to_table: dict) -> dict:
    """Per function (path::name): tables written (constructor or delete) and read (other m.X use)."""
    usage: dict[str, dict] = {}
    for mod in src.app_modules:
        if mod.path == "app/models.py" or mod.path.startswith("app/panel/"):
            continue
        for node, fn in _walk_with_func(mod.tree):
            if fn is None:
                continue
            key = f"{mod.path}::{fn}"
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "m" \
                    and node.attr in class_to_table:
                usage.setdefault(key, {"writes": set(), "reads": set()})["reads"].add(class_to_table[node.attr])
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "m" \
                        and f.attr in class_to_table:
                    usage.setdefault(key, {"writes": set(), "reads": set()})["writes"].add(class_to_table[f.attr])
                fname = getattr(f, "id", "") or getattr(f, "attr", "")
                if fname in ("delete", "sqldelete") and node.args:
                    a = node.args[0]
                    if isinstance(a, ast.Attribute) and a.attr in class_to_table:
                        usage.setdefault(key, {"writes": set(), "reads": set()})["writes"].add(class_to_table[a.attr])
    for v in usage.values():
        v["reads"] -= v["writes"]
    return usage


# ---------------------------------------------------------------- agentic literals
def agent_literals(src: Source) -> dict:
    runs, steps, reviews, llm_calls = [], [], [], []
    for mod in src.app_modules:
        for node, fn in _walk_with_func(mod.tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            first = _const(node.args[0]) if node.args else None
            where = {"path": mod.path, "line": node.lineno, "func": fn}
            if isinstance(f, ast.Name) and f.id == "agent_run" and len(node.args) > 1:
                tipo = _const(node.args[1])
                if isinstance(tipo, str):
                    budget = next((_const(k.value) for k in node.keywords if k.arg == "budget_cents"), None)
                    runs.append({"tipo": tipo, "budget_cents": budget, **where})
            elif isinstance(f, ast.Attribute) and f.attr == "step" and isinstance(first, str):
                steps.append({"name": first, **where})
            elif isinstance(f, ast.Attribute) and f.attr == "review" and isinstance(first, str):
                reviews.append({"tipo": first, **where})
            elif isinstance(f, ast.Attribute) and f.attr == "llm" and len(node.args) >= 4:
                role = next((_const(k.value) for k in node.keywords if k.arg == "role"), "agent")
                pv = node.args[3]
                llm_calls.append({"role": role, "prompt_version_name": getattr(pv, "id", None),
                                  "system_name": getattr(node.args[1], "id", None), **where})
    return {"runs": runs, "steps": steps, "reviews": reviews, "llm_calls": llm_calls}


def prompt_versions(src: Source) -> list[dict]:
    out = []
    for path in src.py_files("app/agents", "app/chat"):
        mod = src.module(path)
        for node in mod.tree.body if mod else []:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.endswith("VERSION") and isinstance(_const(node.value), str):
                        out.append({"ref": f"{path}::{t.id}", "value": _const(node.value), "line": node.lineno})
    return out


def constants(src: Source, path: str) -> list[dict]:
    mod = src.module(path)
    out = []
    for node in mod.tree.body if mod else []:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper() and not name.startswith("_"):
                v = _const(node.value)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    line = mod.lines[node.lineno - 1]
                    note = line.split("#", 1)[1].strip() if "#" in line else ""
                    out.append({"name": name, "value": v, "line": node.lineno, "note": note})
    return out


def callers(src: Source, ref: str) -> dict:
    """Approximate call sites of a function symbol in app/, tests/ and evals/."""
    path, _, sym = ref.partition("::")
    name = sym.split(".")[-1]
    out = {"app": [], "tests": []}
    if not name or name in GENERIC_NAMES:
        return None  # too common a name to count by name; reported as unknown
    for p in src.py_files("app", "tests", "evals"):
        mod = src.module(p)
        if mod is None or p.startswith("app/panel/"):
            continue
        imported = p == path or any(isinstance(n, ast.ImportFrom) and any(a.name == name for a in n.names)
                                    for n in ast.walk(mod.tree))
        for node, fn in _walk_with_func(mod.tree):
            if isinstance(node, ast.Call):
                f = node.func
                hit = (isinstance(f, ast.Name) and f.id == name and imported) or \
                      (isinstance(f, ast.Attribute) and f.attr == name)
                if hit and not (p == path and fn == sym):
                    out["tests" if p.startswith(("tests/", "evals/")) else "app"].append(
                        {"path": p, "line": node.lineno, "func": fn})
    return out


# ------------------------------------------------------------------- configuration
def env_vars(src: Source) -> list[dict]:
    rows: dict[str, dict] = {}

    def row(name):
        return rows.setdefault(name, {"name": name, "secret": bool(SECRET_NAME.search(name)), "code": [],
                                      "default": None, "render": None, "workflows": {}, "example": None})

    pat = re.compile(r"(?:os\.environ\.get|_int|_thinking)\(\s*\"([A-Z][A-Z0-9_]+)\"(?:\s*,\s*([^)\n]+))?")
    for p in src.py_files("app", "evals", "migrations"):
        if p.startswith("app/panel/"):
            continue
        for i, line in enumerate(src.text(p).splitlines(), 1):
            for mt in pat.finditer(line):
                r = row(mt.group(1))
                r["code"].append({"path": p, "line": i})
                d = (mt.group(2) or "").strip().rstrip(")")
                if d and r["default"] is None and not d.startswith(("provider", "self", "settings")):
                    r["default"] = d
    for sh in ("scripts/start.sh", "scripts/pipeline.sh"):
        for i, line in enumerate(src.text(sh).splitlines(), 1):
            for v in re.findall(r"\$\{?([A-Z][A-Z0-9_]+)", line):
                row(v)["code"].append({"path": sh, "line": i})
    rd = yaml.safe_load(src.text("render.yaml") or "{}") or {}
    for svc in rd.get("services", []):
        for ev in svc.get("envVars", []):
            r = row(ev["key"])
            if ev.get("sync") is False:
                r["secret"], r["render"] = True, "secret"
            else:
                r["render"] = str(ev.get("value", ""))
    for wf in workflows(src):
        for k, v in wf["env"].items():
            r = row(k)
            if "secrets." in str(v):
                r["secret"] = True
                r["workflows"][wf["file"]] = "secret"
            else:
                r["workflows"][wf["file"]] = str(v)
    for i, line in enumerate(src.text(".env.example").splitlines(), 1):
        mt = re.match(r"^#?\s*([A-Z][A-Z0-9_]+)=([^#\n]*)", line)
        if mt:
            r = row(mt.group(1))
            r["example"] = "" if r["secret"] else mt.group(2).strip()
    for r in rows.values():
        if r["secret"]:  # never display values of secrets, wherever they came from
            r["default"] = None
            r["example"] = None if r["example"] is None else ""
    return sorted(rows.values(), key=lambda r: (not r["secret"], r["name"]))


def _cron_text(expr: str) -> dict:
    parts = expr.split()
    days = {"*": None, "0": "domingo", "1": "lunes", "2": "martes", "3": "miércoles", "4": "jueves", "5": "viernes",
            "6": "sábado"}
    days_en = {"0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday", "4": "Thursday", "5": "Friday",
               "6": "Saturday"}
    out = {"expr": expr, "es": expr, "en": expr}
    if len(parts) != 5:
        return out
    mi, hr, _, _, dw = parts
    if hr.startswith("*/"):
        n = hr[2:]
        out["es"] = f"cada {n} horas, al minuto {mi} (UTC)"
        out["en"] = f"every {n} hours, at minute {mi} (UTC)"
    elif hr.isdigit() and mi.isdigit():
        brt = (int(hr) - 3) % 24
        d_es = days.get(dw) or "cada día"
        d_en = days_en.get(dw) or "every day"
        out["es"] = f"{d_es} {int(hr):02d}:{int(mi):02d} UTC = {brt:02d}:{int(mi):02d} BRT"
        out["en"] = f"{d_en} {int(hr):02d}:{int(mi):02d} UTC = {brt:02d}:{int(mi):02d} BRT"
    return out


def workflows(src: Source) -> list[dict]:
    out = []
    base = src.root / ".github" / "workflows"
    for p in sorted(base.glob("*.yml")) if base.exists() else []:
        rel = str(p.relative_to(src.root))
        d = yaml.safe_load(p.read_text()) or {}
        on = d.get("on") or d.get(True) or {}
        if isinstance(on, list):
            on = {k: None for k in on}
        crons = [_cron_text(c["cron"]) for c in (on.get("schedule") or [])] if isinstance(on, dict) else []
        dispatch = isinstance(on, dict) and "workflow_dispatch" in on
        inputs = list(((on.get("workflow_dispatch") or {}).get("inputs") or {}).keys()) if dispatch else []
        env, runs, timeout, secrets = {}, [], None, set()
        for job in (d.get("jobs") or {}).values():
            timeout = job.get("timeout-minutes", timeout)
            for st in job.get("steps", []):
                env.update(st.get("env") or {})
                if st.get("run"):
                    runs += [ln.strip() for ln in str(st["run"]).splitlines() if ln.strip()]
        secrets = sorted(set(re.findall(r"secrets\.([A-Z0-9_]+)", p.read_text())))
        triggers = [k for k in (on.keys() if isinstance(on, dict) else [])]
        out.append({"file": rel, "name": d.get("name", p.stem), "crons": crons, "dispatch": dispatch,
                    "inputs": inputs, "triggers": triggers, "env": env, "runs": runs, "timeout": timeout,
                    "secrets": secrets})
    return out


def render_services(src: Source) -> list[dict]:
    rd = yaml.safe_load(src.text("render.yaml") or "{}") or {}
    keys = ("type", "name", "runtime", "plan", "region", "healthCheckPath", "autoDeployTrigger", "dockerfilePath")
    return [{k: svc.get(k) for k in keys} for svc in rd.get("services", [])]


def model_settings(src: Source) -> list[dict]:
    """Which provider and model each role uses, as configured in files (never live secrets)."""
    rows = []
    for role, prov, model in (("chat", "CHAT_PROVIDER", "CHAT_MODEL"), ("agentes", "AGENT_PROVIDER", "AGENT_MODEL"),
                              ("verificador", "VERIFIER_PROVIDER", "VERIFIER_MODEL")):
        rows.append({"role": role, "provider_var": prov, "model_var": model})
    return rows


# ------------------------------------------------------------------- entry points
def cli_commands(src: Source) -> list[dict]:
    mod = src.module("app/cli.py")
    cmds, by_var = [], {}
    for node in ast.walk(mod.tree) if mod else []:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr == "add_parser":
                name = _const(node.value.args[0])
                hlp = next((_const(k.value) for k in node.value.keywords if k.arg == "help"), "")
                c = {"name": name, "help": hlp, "args": [], "line": node.lineno}
                cmds.append(c)
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        by_var[t.id] = c
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr == "add_parser":
                cmds.append({"name": _const(node.value.args[0]), "line": node.lineno, "args": [],
                             "help": next((_const(k.value) for k in node.value.keywords if k.arg == "help"), "")})
            elif isinstance(f, ast.Attribute) and f.attr == "add_argument" and isinstance(f.value, ast.Name) \
                    and f.value.id in by_var and node.value.args:
                by_var[f.value.id]["args"].append(_const(node.value.args[0]))
    return sorted(cmds, key=lambda c: c["line"])


def routes(src: Source) -> list[dict]:
    out = []
    for path, prefix in (("app/admin.py", "/admin"), ("app/main.py", "")):
        mod = src.module(path)
        for node in ast.walk(mod.tree) if mod else []:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ("get", "post") \
                            and dec.args:
                        out.append({"method": dec.func.attr.upper(), "path": prefix + (_const(dec.args[0]) or ""),
                                    "func": node.name, "file": path, "line": node.lineno,
                                    "doc": (ast.get_docstring(node) or "").split("\n")[0]})
    return out


def tests(src: Source) -> dict:
    out = {}
    for p in src.py_files("tests"):
        mod = src.module(p)
        for node in mod.tree.body if mod else []:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                out[f"{p}::{node.name}"] = {"path": p, "name": node.name, "line": node.lineno, "end": node.end_lineno}
    return out


def evals(src: Source) -> dict:
    cats = Counter()
    langs = Counter()
    for line in src.text("evals/chat_eval.jsonl").splitlines():
        if line.strip():
            d = json.loads(line)
            cats[d.get("category", "?")] += 1
            langs[d.get("lang", "?")] += 1
    return {"total": sum(cats.values()), "categories": dict(cats), "langs": dict(langs)}


def migrations(src: Source) -> list[dict]:
    out = []
    base = src.root / "migrations" / "versions"
    for p in sorted(base.glob("*.py")) if base.exists() else []:
        t = p.read_text()
        rev = re.search(r"^revision\s*[:=].*?['\"]([^'\"]+)['\"]", t, re.M)
        doc = re.search(r'^"""(.+?)(?:\n|""")', t, re.S)
        out.append({"file": str(p.relative_to(src.root)), "revision": rev.group(1) if rev else "",
                    "doc": (doc.group(1).strip() if doc else "")[:160]})
    return out


# ---------------------------------------------------------------------- documents
def decisions(src: Source) -> list[dict]:
    out = []
    for i, line in enumerate(src.text("docs/decisiones.md").splitlines(), 1):
        mt = re.match(r"^\*\*(D\d+[a-z]?)\.\s*(.+?)\*\*\s*(.*)$", line)
        if mt:
            body = mt.group(3)
            out.append({"id": mt.group(1), "title": mt.group(2).rstrip("."), "line": i,
                        "open": "[A confirmar]" in body, "text": re.sub(r"\s*\[A confirmar\]\s*", " ", body).strip()})
    return out


def md_tables(src: Source, path: str) -> dict[str, list[list[str]]]:
    """Markdown tables keyed by the nearest preceding '## ' heading."""
    out, heading, current = {}, "", None
    for line in src.text(path).splitlines():
        if line.startswith("## "):
            heading, current = line[3:].strip(), None
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            if current is None:
                current = out.setdefault(heading, [])
            current.append(cells)
        else:
            current = None  # a non-table line ends the table
    return out


def stale_mentions(src: Source) -> list[dict]:
    """Mentions of the retired Fly.io deployment in code, scripts and docs (the brief changed to Render)."""
    pat = re.compile(r"\bFly\b|fly\.io|fly deploy|fly machine|fly secrets|fly mpg|fly\.toml|Fly Managed", re.I)
    files = src.py_files("app", "migrations") + ["scripts/start.sh", "scripts/pipeline.sh", "README.md", "Dockerfile",
                                                 ".env.example", "docs/decisiones.md", "docs/agentes.md"]
    out = []
    for p in files:
        if p.startswith("app/panel/"):
            continue
        for i, line in enumerate(src.text(p).splitlines(), 1):
            if pat.search(line):
                out.append({"path": p, "line": i, "text": line.strip()[:180]})
    return out


def hardcoded_country(src: Source) -> list[dict]:
    out = []
    for p in src.py_files("app"):
        if p.startswith(("app/seed/", "app/panel/")):
            continue
        for i, line in enumerate(src.text(p).splitlines(), 1):
            if re.search(r"[\"']BR[\"']", line) and "os.environ" not in line:
                out.append({"path": p, "line": i, "text": line.strip()[:160]})
    return out


def default_vs_deployed(src: Source, env: list[dict]) -> list[dict]:
    """Variables whose default in code differs from the value deployed on Render."""
    out = []
    for r in env:
        if r["secret"] or r["default"] is None or r["render"] in (None, "secret"):
            continue
        d = r["default"].strip().strip('"').strip("'")
        if d != r["render"] and not d[:1].isdigit():
            out.append({"name": r["name"], "default": d, "render": r["render"], "code": r["code"][:1]})
    return out


def collect(src: Source) -> dict:
    mdl = models(src)
    env = env_vars(src)
    return {
        "models": mdl,
        "usage": table_usage(src, mdl["class_to_table"]),
        "agent": agent_literals(src),
        "prompt_versions": prompt_versions(src),
        "env": env,
        "workflows": workflows(src),
        "render": render_services(src),
        "cli": cli_commands(src),
        "routes": routes(src),
        "tests": tests(src),
        "evals": evals(src),
        "migrations": migrations(src),
        "decisions": decisions(src),
        "agentes_md": md_tables(src, "docs/agentes.md"),
        "stale": stale_mentions(src),
        "hardcoded_country": hardcoded_country(src),
        "default_vs_deployed": default_vs_deployed(src, env),
        "present": {p: src.exists(p) for p in ("render.yaml", ".github/workflows", "tests", "README.md", ".env.example",
                                               "docs/decisiones.md", "docs/agentes.md", "fly.toml")},
    }
