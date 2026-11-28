"""The docs agent (T1.5): README, SETUP and ARCHITECTURE pages for the analysed project.

Everything here is built from what the analyze stage wrote (ingest.json,
code_map.json and, when an LLM is set, brief.json). Facts that come from the
code are stated; anything only an LLM could say is taken from the brief or left
as a visible TODO for the author, never invented.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

INGEST_FILE = "ingest.json"
CODE_MAP_FILE = "code_map.json"
BRIEF_FILE = "brief.json"


class DocsError(Exception):
    """The analysis files the docs agent needs are missing or unreadable."""


@dataclass
class Analysis:
    """What the analyze stage learned about one project."""

    ingest: dict
    code_map: dict
    brief: dict | None
    repo: Path

    @property
    def name(self) -> str:
        if self.brief and self.brief.get("name"):
            return str(self.brief["name"])
        return Path(self.ingest.get("source", "project").rstrip("/\\")).name.removesuffix(".git")


def _read_json(path: Path, required: bool) -> dict | None:
    if not path.is_file():
        if required:
            raise DocsError(f"{path.name} not found in {path.parent} - run the analyze stage first")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise DocsError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DocsError(f"{path.name} must hold a JSON object")
    return data


def load_analysis(job_path: Path) -> Analysis:
    """Read the analyze stage's output from a job folder."""
    job_path = Path(job_path)
    ingest = _read_json(job_path / INGEST_FILE, required=True)
    code_map = _read_json(job_path / CODE_MAP_FILE, required=True)
    brief = _read_json(job_path / BRIEF_FILE, required=False)
    repo = job_path / ingest.get("repo_dir", "input/repo")
    return Analysis(ingest=ingest, code_map=code_map, brief=brief, repo=repo)


def render_tree(paths: list[str], max_depth: int = 3, max_entries: int = 60) -> str:
    """A ``tree``-style listing of repo paths, folders first, cut at a depth and size.

    Deeper levels collapse into their folder; anything over ``max_entries`` is
    summarised as ``... N more`` so huge repos still give a readable page.
    """
    root: dict = {}
    for p in sorted(paths):
        node = root
        parts = p.split("/")
        for i, part in enumerate(parts):
            if i >= max_depth:
                break
            last = i == len(parts) - 1
            node = node.setdefault(part, None if last else {})
            if node is None:
                break

    lines: list[str] = []
    hidden = 0

    def walk(node: dict, prefix: str) -> None:
        nonlocal hidden
        items = sorted(node.items(), key=lambda kv: (kv[1] is None, kv[0].lower()))
        for i, (name, child) in enumerate(items):
            if len(lines) >= max_entries:
                hidden += 1
                continue
            last = i == len(items) - 1
            label = f"{name}/" if child is not None else name
            lines.append(f"{prefix}{'└── ' if last else '├── '}{label}")
            if child:
                walk(child, prefix + ("    " if last else "│   "))

    walk(root, "")
    if hidden:
        lines.append(f"... {hidden} more")
    return "\n".join(lines)


def _node_id(path: str) -> str:
    return "m_" + "".join(c if c.isalnum() else "_" for c in path)


def dependency_diagram(code_map: dict, max_nodes: int = 25) -> str | None:
    """A Mermaid ``graph LR`` of internal imports, keeping the most connected modules.

    Returns None when the project has no internal imports to draw.
    """
    edges = [(d["from"], d["to"]) for d in code_map.get("dependencies", [])]
    if not edges:
        return None
    degree: dict[str, int] = {}
    for a, b in edges:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    keep = set(sorted(degree, key=lambda p: (-degree[p], p))[:max_nodes])
    shown = [(a, b) for a, b in edges if a in keep and b in keep]
    lines = ["```mermaid", "graph LR"]
    for p in sorted(keep):
        lines.append(f'  {_node_id(p)}["{p}"]')
    for a, b in shown:
        lines.append(f"  {_node_id(a)} --> {_node_id(b)}")
    lines.append("```")
    dropped = len(degree) - len(keep)
    if dropped:
        lines.append(f"\n_{dropped} less-connected modules left out of the diagram._")
    return "\n".join(lines)


# manifest file name -> (install step, run step or None)
_SIMPLE_STEPS = {
    "requirements.txt": ("pip install -r requirements.txt", None),
    "Pipfile": ("pipenv install", None),
    "environment.yml": ("conda env create -f environment.yml", None),
    "go.mod": ("go mod download", "go run ."),
    "Cargo.toml": ("cargo build", "cargo run"),
    "pom.xml": ("mvn package", None),
    "build.gradle": ("./gradlew build", None),
    "build.gradle.kts": ("./gradlew build", None),
    "CMakeLists.txt": ("cmake -S . -B build && cmake --build build", None),
    "platformio.ini": ("pio run", "pio run --target upload"),
    "Gemfile": ("bundle install", None),
    "composer.json": ("composer install", None),
    "pubspec.yaml": ("flutter pub get", "flutter run"),
    "Dockerfile": ("docker build -t app .", "docker run --rm app"),
    "docker-compose.yml": (None, "docker compose up"),
    "docker-compose.yaml": (None, "docker compose up"),
    "compose.yaml": (None, "docker compose up"),
}
_NPM_SCRIPTS = ("dev", "start", "build", "test")


@dataclass
class Step:
    command: str
    source: str  # the manifest the step was read from
    kind: str  # "install" | "run" | "test"


def _npm_steps(repo: Path, rel: str) -> list[Step]:
    steps = [Step("npm install", rel, "install")]
    try:
        scripts = json.loads((repo / rel).read_text(encoding="utf-8")).get("scripts") or {}
    except (ValueError, OSError, AttributeError):
        scripts = {}
    for name in _NPM_SCRIPTS:
        if name in scripts:
            cmd = "npm start" if name == "start" else f"npm run {name}"
            steps.append(Step(cmd, rel, "test" if name == "test" else "run"))
    return steps


def _pyproject_steps(repo: Path, rel: str) -> list[Step]:
    steps = [Step("pip install -e .", rel, "install")]
    try:
        data = tomllib.loads((repo / rel).read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return steps
    for name in sorted(data.get("project", {}).get("scripts", {})):
        steps.append(Step(f"{name} --help", rel, "run"))
    return steps


def setup_steps(analysis: Analysis) -> list[Step]:
    """Install / run / test commands backed by a manifest; root manifests first."""
    manifests = sorted(analysis.ingest.get("manifests", []), key=lambda m: (m.count("/"), m))
    steps: list[Step] = []
    for rel in manifests:
        folder, _, name = rel.rpartition("/")
        if name == "package.json":
            found = _npm_steps(analysis.repo, rel)
        elif name == "pyproject.toml":
            found = _pyproject_steps(analysis.repo, rel)
        elif name in _SIMPLE_STEPS:
            install, run = _SIMPLE_STEPS[name]
            found = [Step(c, rel, k) for c, k in ((install, "install"), (run, "run")) if c]
        else:
            continue
        for step in found:
            if folder:
                step.command = f"cd {folder} && {step.command}"
            steps.append(step)
    return steps


_ENV_TEMPLATE = re.compile(r"(^|/)\.?env(\.[\w-]+)?\.(example|sample|template|dist)$", re.I)
_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def env_var_names(analysis: Analysis) -> dict[str, list[str]]:
    """Variable names declared in .env.example-style templates, per template file.

    Only names are returned - values are never copied into the docs, even from a
    template, in case someone committed a real key there.
    """
    found: dict[str, list[str]] = {}
    for f in analysis.ingest.get("files", []):
        rel = f["path"]
        if f.get("sensitive") or f.get("skipped") or not _ENV_TEMPLATE.search(rel):
            continue
        try:
            text = (analysis.repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names = [m.group(1) for line in text.splitlines() if (m := _ENV_KEY.match(line))]
        if names:
            found[rel] = list(dict.fromkeys(names))
    return found

TODO = "> **TODO (author):** {}"


def render_setup(analysis: Analysis) -> str:
    """SETUP.md: prerequisites, install, configure, run, test - each step cites its manifest."""
    steps = setup_steps(analysis)
    out = [f"# Setting up {analysis.name}", ""]
    langs = [n for n, i in analysis.ingest.get("languages", {}).items() if i.get("kind") == "code"]
    out += ["## Prerequisites", ""]
    out += [f"- {lang}" for lang in langs[:5]] or [TODO.format("list what must be installed.")]
    for kind, title in (("install", "Install"), ("run", "Run"), ("test", "Test")):
        chosen = [s for s in steps if s.kind == kind]
        if not chosen and kind == "test":
            continue
        out += ["", f"## {title}", ""]
        if not chosen:
            out.append(TODO.format(f"no manifest says how to {kind} this project."))
            continue
        out.append("```bash")
        out += [s.command for s in chosen]
        out.append("```")
        out.append("")
        out.append("_From: " + ", ".join(sorted({f"`{s.source}`" for s in chosen})) + "._")
    env = env_var_names(analysis)
    if env:
        out += ["", "## Configuration", "",
                "Copy the template and fill in your own values:", ""]
        for rel, names in env.items():
            out.append(f"`{rel}`:")
            out.append("")
            out += [f"- `{n}`" for n in names]
            out.append("")
    if analysis.brief and analysis.brief.get("how_to_run"):
        out += ["", "## Notes from the analysis", ""]
        out += [f"- {s}" for s in analysis.brief["how_to_run"]]
    return "\n".join(out).rstrip() + "\n"
