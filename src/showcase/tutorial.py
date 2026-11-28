"""The tutorial page (T1.6): get it running, then read the code in the order it runs.

Built from the same analysis as the other docs. The reading order follows the
project's own imports outward from its entry points, so a newcomer meets each
file after the file that uses it. Nothing is guessed: steps come from manifests,
explanations from docstrings or the LLM brief, and gaps are visible TODOs.
"""

from __future__ import annotations

from collections import deque

from showcase.codemap import python_source_roots
from showcase.docs import TODO, Analysis, _first_line, env_var_names, setup_steps
from showcase.ingest import is_remote

_TEST_HINTS = ("test", "tests", "spec", "__tests__", "conftest")


def is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (any(p in _TEST_HINTS for p in parts[:-1])
            or name.startswith("test_") or name.startswith("conftest")
            or ".test." in name or ".spec." in name or name.endswith("_test.py"))


def reading_order(code_map: dict, limit: int = 12) -> list[str]:
    """Modules in the order a reader should meet them: entry points, then what they import.

    Breadth-first over ``depends_on`` from each entry point; test files are left
    out. If there are no entry points, start from the most-used modules instead.
    """
    modules = code_map.get("modules", {})
    summary = code_map.get("summary", {})
    starts = [e["path"] for e in summary.get("entry_points", []) if e["path"] in modules]
    if not starts:
        starts = [h["path"] for h in summary.get("hubs", []) if h["path"] in modules]
    order: list[str] = []
    seen: set[str] = set()
    queue = deque(p for p in starts if not is_test_path(p))
    while queue and len(order) < limit:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        order.append(path)
        for dep in modules.get(path, {}).get("depends_on", []):
            if dep not in seen and not is_test_path(dep):
                queue.append(dep)
    return order


def _symbol_lines(mod: dict, path: str, limit: int = 5) -> list[str]:
    """Top-level functions and classes worth pointing at, documented ones first."""
    syms = [s for s in mod.get("symbols", []) if s.get("kind") in ("function", "class")]
    syms.sort(key=lambda s: (not s.get("doc"), s.get("line", 0)))
    out = []
    for s in syms[:limit]:
        doc = _first_line(s.get("doc"))
        out.append(f"- `{s['name']}` ({s['kind']}, line {s.get('line', '?')})"
                   + (f" - {doc}" if doc else ""))
    return out


def _code_block(cmds: list[str]) -> list[str]:
    return ["```bash", *cmds, "```"]


def render_tutorial(analysis: Analysis) -> str:
    """TUTORIAL.md: clone, install, configure, run, test, then a guided read of the code."""
    cm, brief = analysis.code_map, analysis.brief or {}
    source = analysis.ingest.get("source", "")
    steps = setup_steps(analysis)
    out = [f"# Tutorial: {analysis.name}", ""]
    out.append(brief.get("one_liner") or TODO.format("one sentence on what this is."))
    out += ["", "By the end you will have the project running and know which file does what, "
            "in the order the code runs.", ""]

    n = 0

    def section(title: str) -> None:
        nonlocal n
        n += 1
        out.extend(["", f"## {n}. {title}", ""])

    section("Get the code")
    if is_remote(source):
        folder = source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        out += _code_block([f"git clone {source}", f"cd {folder}"])
    else:
        out.append("Open the project folder in a terminal.")

    for kind, title in (("install", "Install dependencies"), ("run", "Run it")):
        section(title)
        chosen = [s.command for s in steps if s.kind == kind]
        if kind == "run":
            env = env_var_names(analysis)
            if env:
                out.append("First fill in the settings it needs - copy each template "
                           "and set your own values:")
                out.append("")
                out += [f"- `{rel}` -> " + ", ".join(f"`{v}`" for v in names)
                        for rel, names in env.items()]
                out.append("")
        out += _code_block(chosen) if chosen else [TODO.format(f"how to {kind} it.")]
        if kind == "run" and brief.get("how_to_run"):
            out += ["", *[f"- {s}" for s in brief["how_to_run"]]]

    tests = [s.command for s in steps if s.kind == "test"]
    has_py_tests = any(is_test_path(p) and p.endswith(".py") for p in cm.get("modules", {}))
    if not tests and has_py_tests and "pytest" in cm.get("external_packages", {}):
        roots = python_source_roots(list(cm.get("modules", {})))
        test_root = next((r for r in roots if any(
            is_test_path(p) and p.startswith(r + "/") for p in cm["modules"])), "")
        tests = [f"(cd {test_root} && pytest -q)" if test_root else "pytest -q"]
    if tests:
        section("Run the tests")
        out += _code_block(tests)

    order = reading_order(cm)
    section("Read the code")
    if not order:
        out.append(TODO.format("no entry point or shared module was found to start from."))
    entries = {e["path"]: e["why"] for e in cm.get("summary", {}).get("entry_points", [])}
    modules = cm.get("modules", {})
    for i, path in enumerate(order, 1):
        mod = modules.get(path, {})
        out += ["", f"### {n}.{i} `{path}`", ""]
        if path in entries:
            out += [f"**Start here** - an entry point (found by {entries[path]}).", ""]
        doc = _first_line(mod.get("doc"))
        if doc:
            out.append(doc)
        syms = _symbol_lines(mod, path)
        if syms:
            out += ["", "Look at:", "", *syms]
        nxt = [d for d in mod.get("depends_on", []) if d in order and order.index(d) > i - 1]
        if nxt:
            out += ["", "Leads to: " + ", ".join(f"`{d}`" for d in nxt)]
    left = len([p for p in modules if not is_test_path(p)]) - len(order)
    if left > 0:
        out += ["", f"_{left} more modules are not covered here - see ARCHITECTURE.md._"]

    section("Where to go next")
    out.append("- [ARCHITECTURE.md](ARCHITECTURE.md) - every module and how they connect")
    out.append("- [SETUP.md](SETUP.md) - full setup and configuration")
    out += [f"- {x}" for x in brief.get("notable", [])]
    return "\n".join(out).rstrip() + "\n"
