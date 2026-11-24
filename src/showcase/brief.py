"""The project brief (T1.4): ask an LLM to explain the project from the code map.

The prompt is built only from ingest.json, code_map.json and a few chosen files.
Sensitive files are named at most, never quoted. Everything is packed into a
character budget so a huge repo cannot blow the token bill (risk R-12).
"""

from __future__ import annotations

import json
from pathlib import Path

from showcase.llm import Message

PROMPT_BUDGET_CHARS = 60_000
_README_CHARS = 6_000
_MANIFEST_CHARS = 3_000
_ENTRY_CHARS = 4_000

BRIEF_KEYS = (
    "name", "one_liner", "problem", "audience", "how_it_works", "architecture",
    "tech_stack", "entry_points", "how_to_run", "notable", "open_questions",
)

SYSTEM = """You are the Analyzer in Project Showcase Studio. You explain a codebase to \
engineers who have never seen it. Use only the material given: if something is not \
shown, say so in open_questions instead of guessing. Every file path you mention must \
appear in the material. Reply with one JSON object and nothing else."""

SCHEMA = """{
  "name": "project name",
  "one_liner": "what it is, in one sentence",
  "problem": "the problem it solves and for whom",
  "audience": "who would use it",
  "how_it_works": ["ordered steps of the main flow, each naming the files involved"],
  "architecture": [{"component": "name", "files": ["path"], "role": "what it does"}],
  "tech_stack": ["language, framework or service actually used"],
  "entry_points": [{"path": "file", "what": "how it is started and what it does"}],
  "how_to_run": ["setup and run steps supported by the manifests or README"],
  "notable": ["design choices or techniques worth showing in a demo"],
  "open_questions": ["things the material does not answer"]
}"""


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n… [cut, {len(text) - limit} chars]"


def _read(repo: Path, rel: str, limit: int) -> str | None:
    try:
        return _clip((repo / rel).read_text(encoding="utf-8", errors="replace"), limit)
    except OSError:
        return None


def _readme(ingest: dict) -> str | None:
    for f in ingest["files"]:
        if "/" not in f["path"] and f["path"].lower().startswith("readme"):
            return f["path"]
    return None


def _module_lines(code_map: dict) -> list[str]:
    hubs = {h["path"] for h in code_map["summary"]["hubs"]}
    entries = {e["path"] for e in code_map["summary"]["entry_points"]}
    # most important modules first, so trimming drops the least useful ones
    order = sorted(
        code_map["modules"].items(),
        key=lambda kv: (kv[0] not in entries, kv[0] not in hubs, -len(kv[1]["used_by"]), kv[0]),
    )
    lines = []
    for path, mod in order:
        head = f"- {path}" + (f" — {mod['doc']}" if mod.get("doc") else "")
        syms = ", ".join(
            s["name"] + (f" ({s['doc']})" if s.get("doc") else "") for s in mod["symbols"][:15]
        )
        deps = ", ".join(mod["depends_on"][:8])
        lines.append(head + (f"\n  defines: {syms}" if syms else "")
                     + (f"\n  imports: {deps}" if deps else ""))
    return lines


def build_brief_prompt(
    repo: Path, ingest: dict, code_map: dict, budget_chars: int = PROMPT_BUDGET_CHARS
) -> list[Message]:
    repo = Path(repo)
    sensitive = set(ingest["sensitive_files"])
    parts: list[str] = []
    langs = ", ".join(f"{k} ({v['lines']} lines)" for k, v in ingest["languages"].items())
    parts.append(
        f"# Overview\nsource: {ingest['source']}\nprimary language: "
        f"{ingest['primary_language']}\nlanguages: {langs}\n"
        f"files: {ingest['totals']['files']}, code lines: {ingest['totals']['code_lines']}"
    )
    if sensitive:
        parts.append("# Sensitive files (contents withheld)\n" + "\n".join(sorted(sensitive)))

    readme = _readme(ingest)
    if readme and readme not in sensitive:
        text = _read(repo, readme, _README_CHARS)
        if text:
            parts.append(f"# {readme}\n{text}")
    for m in ingest["manifests"]:
        if m not in sensitive:
            text = _read(repo, m, _MANIFEST_CHARS)
            if text:
                parts.append(f"# manifest: {m}\n{text}")

    s = code_map["summary"]
    parts.append(
        "# Code map summary\n"
        + "\n".join(f"- entry point {e['path']} ({e['why']})" for e in s["entry_points"])
        + ("\n" if s["entry_points"] else "")
        + "\n".join(f"- hub {h['path']} (imported by {h['used_by']})" for h in s["hubs"])
        + f"\nexternal packages: {', '.join(code_map['external_packages']) or 'none'}"
    )
    for e in s["entry_points"][:3]:
        if e["path"] not in sensitive:
            text = _read(repo, e["path"], _ENTRY_CHARS)
            if text:
                parts.append(f"# entry point source: {e['path']}\n{text}")

    tail = f"\n\nReply with JSON in exactly this shape:\n{SCHEMA}"
    # leave at least a quarter of the budget for the module list
    head = _clip("\n\n".join(parts), max(budget_chars * 3 // 4 - len(tail), 0))
    room = budget_chars - len(head) - len(tail) - len("\n\n# Modules\n")
    kept, used = [], 0
    lines = _module_lines(code_map)
    for line in lines:
        if used + len(line) + 1 > room:
            break
        kept.append(line)
        used += len(line) + 1
    if len(kept) < len(lines):
        kept.append(f"… {len(lines) - len(kept)} more modules not shown")
    files_block = "\n\n# Modules\n" + "\n".join(kept)
    return [Message("system", SYSTEM), Message("user", head + files_block + tail)]


def known_paths(ingest: dict) -> set[str]:
    return {f["path"] for f in ingest["files"]}


class BriefError(Exception):
    """The model's reply is not a usable brief."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise BriefError("reply contains no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BriefError(f"reply is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BriefError("reply JSON is not an object")
    return data


def parse_brief_reply(text: str, known: set[str]) -> dict:
    """Validate the reply; drop file references that are not in the repo.

    A made-up path is a wrong claim about the code (an anti-goal), so it is removed
    and listed under ``unverified_paths`` for the review screen rather than trusted.
    """
    data = _extract_json(text)
    missing = [k for k in BRIEF_KEYS if k not in data]
    if missing:
        raise BriefError(f"reply is missing keys: {', '.join(missing)}")
    for key in ("how_it_works", "architecture", "tech_stack", "entry_points",
                "how_to_run", "notable", "open_questions"):
        if not isinstance(data[key], list):
            raise BriefError(f"`{key}` must be a list")

    unverified: set[str] = set()
    for comp in data["architecture"]:
        if not isinstance(comp, dict):
            raise BriefError("`architecture` items must be objects")
        files = [f for f in comp.get("files", []) if isinstance(f, str)]
        unverified.update(f for f in files if f not in known)
        comp["files"] = [f for f in files if f in known]
    entries = []
    for e in data["entry_points"]:
        if not isinstance(e, dict) or not isinstance(e.get("path"), str):
            raise BriefError("`entry_points` items need a `path`")
        if e["path"] in known:
            entries.append(e)
        else:
            unverified.add(e["path"])
    data["entry_points"] = entries
    data["unverified_paths"] = sorted(unverified)
    return {k: data[k] for k in (*BRIEF_KEYS, "unverified_paths")}


def render_brief_md(brief: dict) -> str:
    """Human-readable brief.md for the author and the later agents."""
    def bullets(items: list) -> str:
        return "\n".join(f"- {i}" for i in items) or "- (none)"

    out = [f"# {brief['name']}", "", f"_{brief['one_liner']}_", "",
           "## Problem", brief["problem"], "", "## Audience", brief["audience"], "",
           "## How it works"]
    out += [f"{n}. {step}" for n, step in enumerate(brief["how_it_works"], 1)] or ["(none)"]
    out += ["", "## Architecture", "", "| Component | Files | Role |", "| --- | --- | --- |"]
    for c in brief["architecture"]:
        files = ", ".join(f"`{f}`" for f in c.get("files", [])) or "—"
        out.append(f"| {c.get('component', '?')} | {files} | {c.get('role', '')} |")
    out += ["", "## Tech stack", bullets(brief["tech_stack"]), "", "## Entry points"]
    out += [f"- `{e['path']}` — {e.get('what', '')}" for e in brief["entry_points"]] or \
        ["- (none)"]
    out += ["", "## How to run"]
    out += [f"{n}. {step}" for n, step in enumerate(brief["how_to_run"], 1)] or ["(none)"]
    out += ["", "## Worth showing", bullets(brief["notable"]),
            "", "## Open questions", bullets(brief["open_questions"])]
    if brief.get("unverified_paths"):
        out += ["", "## Removed claims",
                "The model named these paths, which are not in the repo; they were dropped:",
                bullets([f"`{p}`" for p in brief["unverified_paths"]])]
    return "\n".join(out) + "\n"


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)
