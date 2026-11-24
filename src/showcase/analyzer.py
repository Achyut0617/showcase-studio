"""The analyze stage: fetch the project, map it, and describe it.

T1.2 writes ingest.json (files, languages, manifests, sensitive files).
T1.3 writes code_map.json (symbols, dependency graph, call graph, entry points).
T1.4 turns these into brief.json / brief.md with an LLM.
"""

from __future__ import annotations

import json
from datetime import datetime

from showcase.codemap import build_code_map
from showcase.ingest import fetch_source, scan_tree
from showcase.job import Job

INGEST_FILE = "ingest.json"
CODE_MAP_FILE = "code_map.json"


class AnalyzeStage:
    name = "analyze"

    def __init__(self, fetch=fetch_source, max_file_bytes: int = 1_000_000) -> None:
        self._fetch = fetch
        self._max_file_bytes = max_file_bytes

    def run(self, job: Job) -> None:
        repo = job.path / "input" / "repo"
        fetched = self._fetch(job.source, repo)
        scan = scan_tree(repo, max_file_bytes=self._max_file_bytes)
        record = {
            "source": job.source,
            "fetched": fetched,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "repo_dir": "input/repo",
            **scan,
        }
        (job.path / INGEST_FILE).write_text(json.dumps(record, indent=2), encoding="utf-8")
        code_map = build_code_map(repo, scan)
        (job.path / CODE_MAP_FILE).write_text(json.dumps(code_map, indent=2), encoding="utf-8")
        summary = code_map["summary"]

        langs = ", ".join(
            f"{name} {info['lines']}" for name, info in list(scan["languages"].items())[:5]
        )
        lines = [
            f"analyze: ingested {job.source} ({fetched.get('commit') or fetched['kind']})",
            f"files: {scan['totals']['files']}, code lines: {scan['totals']['code_lines']}",
            f"primary language: {scan['primary_language']}",
            f"languages (lines): {langs or 'none'}",
            f"manifests: {', '.join(scan['manifests']) or 'none'}",
            f"code map: {summary['modules']} modules, {summary['symbols']} symbols, "
            f"{summary['dependency_edges']} internal imports, {len(code_map['calls'])} calls",
            "entry points: "
            + (", ".join(e["path"] for e in summary["entry_points"]) or "none found"),
        ]
        if code_map["parse_errors"]:
            lines.append(f"could not parse: {', '.join(code_map['parse_errors'])}")
        if scan["sensitive_files"]:
            lines.append(
                f"sensitive files (contents never sent to an LLM): "
                f"{', '.join(scan['sensitive_files'])}"
            )
        (job.path / "logs" / f"{self.name}.log").write_text("\n".join(lines) + "\n", "utf-8")
