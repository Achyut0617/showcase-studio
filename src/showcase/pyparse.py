"""Static Python parsing for the code map (T1.3).

Uses only the standard ``ast`` module: the project's code is read, never imported
or run. A file that does not parse is reported with its error, not raised.
"""

from __future__ import annotations

import ast

_DOC_CHARS = 200


def _doc(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node, clean=True)  # type: ignore[arg-type]
    if not doc:
        return None
    first = doc.strip().split("\n\n", 1)[0].replace("\n", " ")
    return first[:_DOC_CHARS]


def _symbols(tree: ast.Module) -> list[dict]:
    out: list[dict] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append({"name": node.name, "kind": "function", "line": node.lineno,
                        "doc": _doc(node)})
        elif isinstance(node, ast.ClassDef):
            out.append({"name": node.name, "kind": "class", "line": node.lineno,
                        "doc": _doc(node)})
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append({"name": f"{node.name}.{item.name}", "kind": "method",
                                "line": item.lineno, "doc": _doc(item)})
    return out


def _imports(tree: ast.Module) -> list[dict]:
    """Every import in the file, including ones inside functions (lazy imports count too)."""
    out: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append({"module": alias.name, "names": [], "level": 0, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            out.append({
                "module": node.module or "",
                "names": [a.name for a in node.names],
                "level": node.level,
                "line": node.lineno,
            })
    out.sort(key=lambda i: i["line"])
    return out


def _has_main_guard(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in test.comparators)
            ):
                return True
    return False


def parse_python(text: str) -> dict:
    """Docstring, top-level symbols, imports and main guard of one Python file."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return {"doc": None, "symbols": [], "imports": [], "main_guard": False,
                "parse_error": f"{type(exc).__name__}: {exc}"}
    return {
        "doc": _doc(tree),
        "symbols": _symbols(tree),
        "imports": _imports(tree),
        "main_guard": _has_main_guard(tree),
        "parse_error": None,
    }


def resolve_import(imp: dict, module: str, is_package: bool) -> list[str]:
    """Candidate dotted module names an import may refer to, most specific first.

    ``module`` is the importing file's dotted name; ``is_package`` is True for an
    ``__init__.py``. ``from . import x`` may name submodule ``pkg.x`` or a symbol in
    ``pkg``, so both are returned and the caller keeps whichever exists in the repo.
    """
    if imp["level"] == 0:
        base = imp["module"]
    else:
        parts = module.split(".")
        if not is_package:
            parts = parts[:-1]
        drop = imp["level"] - 1
        if drop > len(parts):
            return []
        parts = parts[: len(parts) - drop] if drop else parts
        base = ".".join(p for p in [*parts, imp["module"]] if p)
    candidates = [f"{base}.{n}" if base else n for n in imp["names"] if n != "*"]
    if base:
        candidates.append(base)
    return candidates
