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


def parse_python(text: str) -> dict:
    """Module docstring and top-level symbols (functions, classes, methods) of one file."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        return {"doc": None, "symbols": [], "parse_error": f"{type(exc).__name__}: {exc}"}
    return {"doc": _doc(tree), "symbols": _symbols(tree), "parse_error": None}
