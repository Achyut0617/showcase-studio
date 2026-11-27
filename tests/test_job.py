import json
from datetime import datetime

import pytest

from showcase.job import JOB_SUBDIRS, Job, JobError

URL = "https://github.com/Achyut0617/NearbyConnect"
NOW = datetime(2026, 11, 30, 9, 0, 0)


def test_create_makes_layout(tmp_path):
    job = Job.create(URL, tmp_path, now=NOW)
    assert job.path == tmp_path / "nearbyconnect-20261130-090000"
    for sub in JOB_SUBDIRS:
        assert (job.path / sub).is_dir()
    data = json.loads((job.path / "job.json").read_text())
    assert data["project_name"] == "nearbyconnect"
    assert data["source"] == URL
    assert data["stages"] == {}


def test_same_second_collision_gets_suffix(tmp_path):
    first = Job.create(URL, tmp_path, now=NOW)
    second = Job.create(URL, tmp_path, now=NOW)
    third = Job.create(URL, tmp_path, now=NOW)
    assert first.path.name == "nearbyconnect-20261130-090000"
    assert second.path.name == "nearbyconnect-20261130-090000-2"
    assert third.path.name == "nearbyconnect-20261130-090000-3"


def test_load_roundtrip(tmp_path):
    job = Job.create(URL, tmp_path, now=NOW)
    job.set_stage("analyze", "done")
    loaded = Job.load(job.path)
    assert loaded.project_name == "nearbyconnect"
    assert loaded.status_of("analyze") == "done"
    assert loaded.status_of("publish") == "pending"


def test_load_missing_raises_joberror(tmp_path):
    with pytest.raises(JobError, match="job.json"):
        Job.load(tmp_path / "nope")


def test_load_corrupt_raises_joberror(tmp_path):
    job = Job.create(URL, tmp_path, now=NOW)
    (job.path / "job.json").write_text("{not json")
    with pytest.raises(JobError, match="job.json"):
        Job.load(job.path)


def test_set_stage_rejects_unknown_status(tmp_path):
    job = Job.create(URL, tmp_path, now=NOW)
    with pytest.raises(ValueError):
        job.set_stage("analyze", "almost")


def test_set_stage_records_error(tmp_path):
    job = Job.create(URL, tmp_path, now=NOW)
    job.set_stage("run", "failed", error="boom")
    loaded = Job.load(job.path)
    assert loaded.stages["run"]["status"] == "failed"
    assert loaded.stages["run"]["error"] == "boom"
    assert "updated_at" in loaded.stages["run"]


def test_load_rejects_unknown_stage_status(tmp_path, sample_source):
    job = Job.create(sample_source, tmp_path / "jobs")
    data = json.loads((job.path / "job.json").read_text())
    data["stages"] = {"analyze": {"status": "finished"}}
    (job.path / "job.json").write_text(json.dumps(data))
    with pytest.raises(JobError, match="unknown status"):
        Job.load(job.path)
