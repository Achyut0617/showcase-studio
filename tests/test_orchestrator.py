import json
from datetime import datetime

import pytest

from showcase.job import Job
from showcase.orchestrator import approve, run_job
from showcase.stages import STAGE_ORDER, StubStage, default_stages


@pytest.fixture
def make_job(sample_source):
    def _make(tmp_path):
        return Job.create(sample_source, tmp_path / "jobs", now=datetime(2026, 11, 30, 9, 0, 0))

    return _make


def test_stage_order_is_fixed():
    assert STAGE_ORDER == (
        "analyze", "research_style", "write_docs", "run", "plan_demo", "record",
        "write_script", "voice", "edit_video", "review", "publish",
    )


def test_full_run_waits_for_approval(tmp_path, make_job):
    job = make_job(tmp_path)
    assert run_job(job, default_stages()) == "waiting_approval"
    for name in STAGE_ORDER[:-1]:
        assert job.status_of(name) == "done"
        assert (job.path / "logs" / f"{name}.log").exists()
    assert job.status_of("publish") == "waiting_approval"
    assert Job.load(job.path).status_of("publish") == "waiting_approval"


def test_approve_then_resume_finishes(tmp_path, make_job):
    job = make_job(tmp_path)
    run_job(job, default_stages())
    approve(job)
    approval = json.loads((job.path / "publish" / "approval.json").read_text())
    assert approval["approved_by"] == "achyut"
    assert "approved_at" in approval
    assert run_job(Job.load(job.path), default_stages()) == "done"


class Boom(StubStage):
    def run(self, job):
        raise RuntimeError("boom")


def test_failure_stops_and_records_error(tmp_path, make_job):
    job = make_job(tmp_path)
    stages = default_stages()
    stages[3] = Boom("run")
    assert run_job(job, stages) == "failed"
    assert job.stages["run"]["status"] == "failed"
    assert job.stages["run"]["error"] == "boom"
    for name in STAGE_ORDER[4:]:
        assert job.status_of(name) == "pending"


def test_resume_skips_done_and_reruns_running(tmp_path, make_job):
    job = make_job(tmp_path)
    job.set_stage("analyze", "done")
    job.set_stage("research_style", "running")  # simulates a crash mid-stage
    run_job(job, default_stages())
    assert not (job.path / "logs" / "analyze.log").exists()  # skipped
    assert (job.path / "logs" / "research_style.log").exists()  # re-run
    assert job.status_of("research_style") == "done"


def test_finished_stages_record_duration(tmp_path, make_job):
    job = make_job(tmp_path)
    run_job(job, [StubStage("analyze")])
    seconds = job.stages["analyze"]["seconds"]
    assert isinstance(seconds, float) and seconds >= 0


def test_default_pipeline_writes_docs(tmp_path, sample_source):
    from showcase.docs import WriteDocsStage
    from showcase.job import Job
    from showcase.orchestrator import run_job
    from showcase.stages import default_stages

    stages = default_stages()
    assert any(isinstance(s, WriteDocsStage) for s in stages)
    job = Job.create(sample_source, tmp_path / "jobs")
    assert run_job(job, stages) == "waiting_approval"
    assert job.status_of("write_docs") == "done"
    assert (job.path / "docs" / "README.md").exists()
