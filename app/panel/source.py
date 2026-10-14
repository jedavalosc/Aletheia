"""Source index: resolves references like 'app/rules/verifier.py::verify_sentence' to a file
and line, and builds links to the repository at the current commit."""
from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ..config import ROOT

DEFAULT_REPO = "https://github.com/jedavalosc/aletheia"
_PATHLIKE = re.compile(r"^[\w.\-/]+\.(py|ya?ml|md|json|jsonl|toml|txt|html|sh|ini|example)$|^[\w.\-/]+/$|^Dockerfile$")


@dataclass
class Resolved:
    ref: str
    path: str
    symbol: str | None
    line: int | None
    end_line: int | None
    ok: bool
    why: str = ""


@dataclass
class PyModule:
    path: str
    tree: ast.Module
    lines: list[str]
    symbols: dict[str, tuple[int, int]] = field(default_factory=dict)


def commit() -> str:
    for var in ("RENDER_GIT_COMMIT", "GITHUB_SHA", "SOURCE_COMMIT"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "main"


def is_path_ref(ref: str) -> bool:
    """A spec entry like 'encargo §6' is prose; 'docs/agentes.md' or 'a.py::f' is a reference."""
    head = ref.split("::", 1)[0]
    return "::" in ref or bool(_PATHLIKE.match(head))


class Source:
    def __init__(self, root: Path = ROOT, repo_url: str = DEFAULT_REPO):
        self.root = root
        self.repo_url = repo_url.rstrip("/")
        self.commit = commit()
        self._mods: dict[str, PyModule | None] = {}

    # ---------------------------------------------------------------- files
    def exists(self, path: str) -> bool:
        return (self.root / path).exists()

    def text(self, path: str) -> str:
        p = self.root / path
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def py_files(self, *dirs: str) -> list[str]:
        out = []
        for d in dirs:
            base = self.root / d
            if base.is_file():
                out.append(d)
                continue
            out += sorted(str(p.relative_to(self.root)) for p in base.rglob("*.py") if "__pycache__" not in p.parts)
        return out

    def module(self, path: str) -> PyModule | None:
        if path not in self._mods:
            src = self.text(path)
            if not src or not path.endswith(".py"):
                self._mods[path] = None
            else:
                tree = ast.parse(src)
                mod = PyModule(path, tree, src.splitlines())
                for node in tree.body:
                    self._index(mod, node, "")
                self._mods[path] = mod
        return self._mods[path]

    def _index(self, mod: PyModule, node: ast.AST, prefix: str) -> None:
        end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mod.symbols[prefix + node.name] = (node.lineno, end)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    self._index(mod, sub, prefix + node.name + ".")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    mod.symbols[prefix + t.id] = (node.lineno, end)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            mod.symbols[prefix + node.target.id] = (node.lineno, end)

    # ------------------------------------------------------------- resolve
    def resolve(self, ref: str) -> Resolved:
        path, _, symbol = ref.partition("::")
        path = path.strip()
        symbol = symbol.strip() or None
        if not self.exists(path):
            return Resolved(ref, path, symbol, None, None, False, "archivo inexistente")
        if symbol is None:
            return Resolved(ref, path, None, None, None, True)
        mod = self.module(path)
        if mod is None:
            return Resolved(ref, path, symbol, None, None, False, "símbolo en archivo no Python")
        if symbol not in mod.symbols:
            return Resolved(ref, path, symbol, None, None, False, "símbolo inexistente")
        a, b = mod.symbols[symbol]
        return Resolved(ref, path, symbol, a, b, True)

    def url(self, path: str, line: int | None = None, end: int | None = None) -> str:
        u = f"{self.repo_url}/blob/{self.commit}/{path}"
        if line:
            u += f"#L{line}" + (f"-L{end}" if end and end != line else "")
        return u

    def link(self, ref: str) -> dict:
        r = self.resolve(ref)
        label = r.path + (f"::{r.symbol}" if r.symbol else "")
        return {"ref": ref, "label": label, "path": r.path, "symbol": r.symbol, "line": r.line, "ok": r.ok,
                "url": self.url(r.path, r.line) if r.ok else None, "why": r.why}

    def snippet(self, ref: str, max_lines: int = 40) -> str:
        r = self.resolve(ref)
        if not r.ok or r.line is None:
            return ""
        mod = self.module(r.path)
        lines = mod.lines[r.line - 1:r.end_line]
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["    …"]
        return "\n".join(lines)

    @cached_property
    def app_modules(self) -> list[PyModule]:
        return [m for m in (self.module(p) for p in self.py_files("app")) if m is not None]
