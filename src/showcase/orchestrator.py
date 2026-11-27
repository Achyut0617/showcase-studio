"""The fixed backbone: runs stages in order, resumes, and stops at the approval gate."""

from __future__ import annotations

import json
import time
from datetime import datetime

from showcase.job import Job
from showcase.stages import APPROVAL_FILE, ApprovalRequired, Stage


def run_job(job: Job, stages: list[Stage]) -> str:
    """Run every stage not yet done. Returns "done", "failed" or "waiting_approval"."""
    for stage in stages:
        if job.status_of(stage.name) == "done":
            continue
        job.set_stage(stage.name, "running")
        started = time.monotonic()
        try:
            stage.run(job)
        except ApprovalRequired:
            job.set_stage(stage.name, "waiting_approval")
            return "waiting_approval"
        except Exception as exc:  # any agent failure stops the job, resumable later
            job.set_stage(
                stage.name, "failed", error=str(exc), seconds=time.monotonic() - started
            )
            return "failed"
        job.set_stage(stage.name, "done", seconds=time.monotonic() - started)
    return "done"


def approve(job: Job, by: str = "achyut") -> None:
    """Record the author's approval so the publish stage may run."""
    record = {"approved_by": by, "approved_at": datetime.now().isoformat(timespec="seconds")}
    approval = job.path / "publish" / APPROVAL_FILE
    approval.write_text(json.dumps(record, indent=2), encoding="utf-8")
