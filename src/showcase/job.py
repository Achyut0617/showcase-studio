"""The job folder: one per showcase run, shared by every agent through its files."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from showcase.source import project_name_from_source

JOB_SUBDIRS = ("input", "clips", "narration", "video", "docs", "publish", "logs")
STATUSES = frozenset({"pending", "running", "done", "failed", "waiting_approval"})
JOB_FILE = "job.json"


class JobError(Exception):
    """A job folder is missing or its job.json cannot be read."""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Job:
    path: Path
    project_name: str
    source: str
    created_at: str
    stages: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def create(cls, source: str, jobs_root: Path, now: datetime | None = None) -> Job:
        now = now or datetime.now()
        name = project_name_from_source(source)
        base = f"{name}-{now:%Y%m%d-%H%M%S}"
        jobs_root = Path(jobs_root)
        jobs_root.mkdir(parents=True, exist_ok=True)
        path, n = jobs_root / base, 1
        while True:
            try:
                path.mkdir()  # atomic claim: fails if another job took this name
                break
            except FileExistsError:
                n += 1
                path = jobs_root / f"{base}-{n}"
        for sub in JOB_SUBDIRS:
            (path / sub).mkdir()
        job = cls(path, name, source, now.isoformat(timespec="seconds"))
        job.save()
        return job

    @classmethod
    def load(cls, path: Path) -> Job:
        path = Path(path)
        file = path / JOB_FILE
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            for name, entry in dict(data.get("stages", {})).items():
                if entry.get("status") not in STATUSES:
                    raise ValueError(f"stage {name!r} has unknown status {entry.get('status')!r}")
            return cls(
                path=path,
                project_name=data["project_name"],
                source=data["source"],
                created_at=data["created_at"],
                stages=dict(data.get("stages", {})),
            )
        except FileNotFoundError as exc:
            raise JobError(f"no {JOB_FILE} found in {path}") from exc
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError, ValueError) as exc:
            raise JobError(f"{file} is not a valid {JOB_FILE}: {exc}") from exc

    def save(self) -> None:
        data = asdict(self)
        data.pop("path")
        fd, tmp = tempfile.mkstemp(dir=self.path, prefix=".job-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path / JOB_FILE)

    def set_stage(
        self, name: str, status: str, error: str | None = None, seconds: float | None = None
    ) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown stage status {status!r}; expected one of {sorted(STATUSES)}")
        entry = {"status": status, "updated_at": _now_iso()}
        if error is not None:
            entry["error"] = error
        if seconds is not None:
            entry["seconds"] = round(seconds, 2)
        self.stages[name] = entry
        self.save()

    def status_of(self, name: str) -> str:
        return self.stages.get(name, {}).get("status", "pending")
