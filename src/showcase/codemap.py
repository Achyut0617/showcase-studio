"""The code map (T1.3): modules, their symbols, and how they depend on each other.

Built from the ingest scan, so pruned folders, symlinks, binary, oversized and
sensitive files are never opened here either. Only Python and JS/TS are parsed;
other languages still appear in ingest.json, just without symbols.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from showcase.jsparse import JS_EXTENSIONS, parse_js, resolve_js_import
from showcase.pyparse import parse_python, resolve_import

PARSERS = {"Python": "python", "JavaScript": "js", "TypeScript": "js", "Vue": "js",
           "Svelte": "js"}


def python_module_name(path: str) -> str:
    """Dotted module for a repo path: ``src/app/db.py`` -> ``src.app.db``."""
    parts = path[: -len(".py")].split("/") if path.endswith(".py") else path.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _python_index(paths: list[str]) -> dict[str, str]:
    """Dotted name -> path, with ``src.`` dropped too so ``from app import x`` resolves."""
    index: dict[str, str] = {}
    for p in paths:
        name = python_module_name(p)
        index.setdefault(name, p)
        if name.startswith("src."):
            index.setdefault(name[len("src."):], p)
    return index


def _external_name(imp: dict, kind: str) -> str | None:
    mod = imp["module"]
    if kind == "python":
        if imp["level"] or not mod:
            return None
        top = mod.split(".")[0]
        return None if top in sys.stdlib_module_names else top
    if mod.startswith((".", "/", "node:")):
        return None
    if mod.startswith("@"):
        return "/".join(mod.split("/")[:2])
    return mod.split("/")[0]


def build_code_map(repo: Path, scan: dict) -> dict:
    """Parse every readable Python/JS/TS file and link imports to files in the repo."""
    repo = Path(repo)
    parseable = [
        f for f in scan["files"]
        if f["language"] in PARSERS and not f["sensitive"] and not f["skipped"]
        and not f["binary"]
        and (f["language"] == "Python" or f["path"].endswith(JS_EXTENSIONS))
    ]
    paths = [f["path"] for f in parseable]
    py_index = _python_index([p for p in paths if p.endswith(".py")])
    existing = set(paths)

    modules: dict[str, dict] = {}
    edges: set[tuple[str, str]] = set()
    external: Counter[str] = Counter()
    for f in parseable:
        kind = PARSERS[f["language"]]
        text = (repo / f["path"]).read_text(encoding="utf-8", errors="replace")
        parsed = parse_python(text) if kind == "python" else parse_js(text)
        deps: set[str] = set()
        for imp in parsed["imports"]:
            target = None
            if kind == "python":
                name = python_module_name(f["path"])
                is_pkg = f["path"].endswith("__init__.py")
                for cand in resolve_import(imp, name, is_pkg):
                    if cand in py_index:
                        target = py_index[cand]
                        break
            else:
                target = resolve_js_import(imp["module"], f["path"], existing)
            imp["resolved"] = target
            if target and target != f["path"]:
                deps.add(target)
            elif not target:
                ext = _external_name(imp, kind)
                if ext:
                    external[ext] += 1
        edges.update((f["path"], d) for d in deps)
        modules[f["path"]] = {"language": f["language"], **parsed,
                              "depends_on": sorted(deps)}

    for path, mod in modules.items():
        mod["used_by"] = sorted(src for src, dst in edges if dst == path)

    calls = sorted(
        {edge for path, mod in modules.items() if mod["language"] == "Python"
         for edge in _python_call_edges(path, mod, modules)}
    )
    return {
        "modules": dict(sorted(modules.items())),
        "calls": [{"from": a, "to": b} for a, b in calls],
        "dependencies": [{"from": a, "to": b} for a, b in sorted(edges)],
        "external_packages": dict(external.most_common()),
        "parse_errors": {p: m["parse_error"] for p, m in modules.items() if m["parse_error"]},
    }


def _python_call_edges(path: str, mod: dict, modules: dict[str, dict]) -> set[tuple[str, str]]:
    """``file::function`` -> ``file::function`` edges for calls that land inside the repo.

    Resolves local names, ``from x import f``, ``import pkg.mod`` / submodule
    references and ``self.method``. Anything dynamic is left out rather than guessed.
    """
    def defined(p: str) -> set[str]:
        return {s["name"] for s in modules[p]["symbols"]} if p in modules else set()

    local = defined(path)
    aliases: dict[str, tuple[str, str | None]] = {}
    for imp in mod["imports"]:
        target = imp.get("resolved")
        if not target:
            continue
        if imp["names"]:
            for n in imp["names"]:
                if n in defined(target):
                    aliases[n] = (target, n)
                elif python_module_name(target).endswith(n):
                    aliases[n] = (target, None)
        else:
            aliases[imp["module"]] = (target, None)

    def resolve(call: str, cls: str | None) -> tuple[str, str] | None:
        if call in local:
            return path, call
        if cls and call.startswith("self."):
            name = f"{cls}.{call[len('self.'):]}"
            return (path, name) if name in local else None
        if call in aliases and aliases[call][1]:
            return aliases[call]  # type: ignore[return-value]
        parts = call.split(".")
        for i in range(len(parts) - 1, 0, -1):
            head, rest = ".".join(parts[:i]), ".".join(parts[i:])
            if head in aliases:
                target, sym = aliases[head]
                name = f"{sym}.{rest}" if sym else rest
                return (target, name) if name in defined(target) else None
        return None

    edges: set[tuple[str, str]] = set()
    for sym in mod["symbols"]:
        cls = sym["name"].split(".")[0] if sym["kind"] == "method" else None
        for call in sym["calls"]:
            hit = resolve(call, cls)
            if hit:
                edges.add((f"{path}::{sym['name']}", f"{hit[0]}::{hit[1]}"))
    return edges
