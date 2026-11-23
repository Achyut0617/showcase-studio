"""The fixed stage order and the stage contract. Every stage is a stub in Stage 0."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from showcase.job import Job

STAGE_ORDER: tuple[str, ...] = (
    "analyze",
    "research_style",
    "write_docs",
    "run",
    "plan_demo",
    "record",
    "write_script",
    "voice",
    "edit_video",
    "review",
    "publish",
)

APPROVAL_FILE = "approval.json"


class Stage(Protocol):
    name: str

    def run(self, job: Job) -> None: ...


class ApprovalRequired(Exception):
    """Raised by the publish stage until the author has approved the job."""


class StubStage:
    """Placeholder agent: records that it ran. Replaced stage by stage from S1 on."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, job: Job) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        (job.path / "logs" / f"{self.name}.log").write_text(
            f"stub: {self.name} ran at {stamp}\n", encoding="utf-8"
        )


class PublishStage(StubStage):
    """Refuses to run until publish/approval.json exists: nothing goes public unreviewed."""

    def run(self, job: Job) -> None:
        if not (job.path / "publish" / APPROVAL_FILE).exists():
            raise ApprovalRequired("waiting for approval: run `showcase approve <job>`")
        super().run(job)


def default_stages() -> list[Stage]:
    return [PublishStage(n) if n == "publish" else StubStage(n) for n in STAGE_ORDER]
