"""Lightweight JavaScript / TypeScript parsing for the code map (T1.3).

Pattern-based, not a full parser: it finds imports, ``require`` calls and the
top-level functions and classes a reader would look for first. Good enough to
draw the dependency graph; precise call graphs for JS come later if needed.
Comments are blanked out first so commented-out code is not reported.
"""

from __future__ import annotations

import posixpath
import re

_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)

_X = re.M | re.X

_IMPORT_PATTERNS = [
    # import x, {a, b as c} from "y";  export {a} from "y";  export * from "y"
    re.compile(
        r"""^\s*(?:import|export)\s+(?:type\s+)?
            (?P<what>[\w$*{},\s]+?)\s+from\s+['"](?P<spec>[^'"]+)['"]""",
        _X,
    ),
    # import "y";  (side-effect import)
    re.compile(r"""^\s*import\s+['"](?P<spec>[^'"]+)['"]""", re.M),
    # require("y") / import("y")
    re.compile(r"""\b(?:require|import)\s*\(\s*['"](?P<spec>[^'"]+)['"]\s*\)"""),
]

_EXPORT = r"^(?:export\s+(?:default\s+)?)?"
_SYMBOL_PATTERNS = [
    (re.compile(_EXPORT + r"(?:async\s+)?function\s*\*?\s*(?P<name>[\w$]+)\s*[(<]", re.M),
     "function"),
    (re.compile(_EXPORT + r"(?:abstract\s+)?class\s+(?P<name>[\w$]+)", re.M), "class"),
    (
        re.compile(
            r"""^(?:export\s+)?(?:const|let|var)\s+(?P<name>[\w$]+)\s*(?::[^=]+)?=\s*
                (?:async\s+)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[\w$]+\s*=>)""",
            _X,
        ),
        "function",
    ),
]

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")


def _blank_comments(text: str) -> str:
    # keep newlines so line numbers stay right
    return _COMMENTS.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _names(what: str | None) -> list[str]:
    if not what:
        return []
    out = []
    for part in re.split(r"[{},]", what):
        part = part.strip()
        if not part or part == "*" or part.startswith("* as"):
            continue
        out.append(part.split(" as ")[0].strip())
    return out


def parse_js(text: str) -> dict:
    """Imports and top-level functions/classes of one JS/TS file (same shape as Python)."""
    clean = _blank_comments(text)
    imports: dict[tuple[str, int], dict] = {}
    for pattern in _IMPORT_PATTERNS:
        for m in pattern.finditer(clean):
            line = _line(clean, m.start("spec"))
            key = (m.group("spec"), line)
            what = m.groupdict().get("what")
            imports.setdefault(
                key, {"module": m.group("spec"), "names": _names(what), "level": 0, "line": line}
            )
    symbols = []
    for pattern, kind in _SYMBOL_PATTERNS:
        for m in pattern.finditer(clean):
            symbols.append({"name": m.group("name"), "kind": kind,
                            "line": _line(clean, m.start()), "doc": None, "calls": []})
    symbols.sort(key=lambda s: s["line"])
    return {
        "doc": None,
        "symbols": symbols,
        "imports": sorted(imports.values(), key=lambda i: i["line"]),
        "main_guard": False,
        "parse_error": None,
    }


def resolve_js_import(spec: str, importer: str, existing: set[str]) -> str | None:
    """Repo path a relative import points to (``./db`` -> ``src/db.ts``); None for packages."""
    if not spec.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
    if base.startswith(".."):
        return None
    candidates = [base]
    candidates += [base + ext for ext in JS_EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in JS_EXTENSIONS]
    for c in candidates:
        if c in existing:
            return c
    return None
