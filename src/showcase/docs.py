"""The docs agent (T1.5): README, SETUP and ARCHITECTURE pages for the analysed project.

Everything here is built from what the analyze stage wrote (ingest.json,
code_map.json and, when an LLM is set, brief.json). Facts that come from the
code are stated; anything only an LLM could say is taken from the brief or left
as a visible TODO for the author, never invented.
"""

from __future__ import annotations

import json
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
