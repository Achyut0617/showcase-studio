import json
from datetime import datetime

from showcase.job import Job
from showcase.orchestrator import approve, run_job
from showcase.stages import STAGE_ORDER, StubStage, default_stages

URL = "https://github.com/Achyut0617/NearbyConnect"


def make_job(tmp_path):
    return Job.create(URL, tmp_path, now=datetime(2026, 11, 30, 9, 0, 0))


def test_stage_order_is_fixed():
    assert STAGE_ORDER == (
        "analyze", "research_style", "write_docs", "run", "plan_demo", "record",
        "write_script", "voice", "edit_video", "review", "publish",
    )


def test_full_run_waits_for_approval(tmp_path):
    job = make_job(tmp_path)
    assert run_job(job, default_stages()) == "waiting_approval"
    for name in STAGE_ORDER[:-1]:
        assert job.status_of(name) == "done"
        assert (job.path / "logs" / f"{name}.log").exists()
    assert job.status_of("publish") == "waiting_approval"
    assert Job.load(job.path).status_of("publish") == "waiting_approval"


def test_approve_then_resume_finishes(tmp_path):
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


def test_failure_stops_and_records_error(tmp_path):
    job = make_job(tmp_path)
    stages = default_stages()
    stages[3] = Boom("run")
    assert run_job(job, stages) == "failed"
    assert job.stages["run"]["status"] == "failed"
    assert job.stages["run"]["error"] == "boom"
    for name in STAGE_ORDER[4:]:
        assert job.status_of(name) == "pending"


def test_resume_skips_done_and_reruns_running(tmp_path):
    job = make_job(tmp_path)
    job.set_stage("analyze", "done")
    job.set_stage("research_style", "running")  # simulates a crash mid-stage
    run_job(job, default_stages())
    assert not (job.path / "logs" / "analyze.log").exists()  # skipped
    assert (job.path / "logs" / "research_style.log").exists()  # re-run
    assert job.status_of("research_style") == "done"
