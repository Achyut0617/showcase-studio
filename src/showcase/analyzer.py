"""The analyze stage. T1.2: fetch the project and write ingest.json.

Later tasks build on this: T1.3 adds parsing and the dependency/call graph,
T1.4 turns it all into brief.json / brief.md with an LLM.
"""

from __future__ import annotations

import json
from datetime import datetime

from showcase.ingest import fetch_source, scan_tree
from showcase.job import Job

INGEST_FILE = "ingest.json"


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

        langs = ", ".join(
            f"{name} {info['lines']}" for name, info in list(scan["languages"].items())[:5]
        )
        lines = [
            f"analyze: ingested {job.source} ({fetched.get('commit') or fetched['kind']})",
            f"files: {scan['totals']['files']}, code lines: {scan['totals']['code_lines']}",
            f"primary language: {scan['primary_language']}",
            f"languages (lines): {langs or 'none'}",
            f"manifests: {', '.join(scan['manifests']) or 'none'}",
        ]
        if scan["sensitive_files"]:
            lines.append(
                f"sensitive files (contents never sent to an LLM): "
                f"{', '.join(scan['sensitive_files'])}"
            )
        (job.path / "logs" / f"{self.name}.log").write_text("\n".join(lines) + "\n", "utf-8")
