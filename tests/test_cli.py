import pytest

from showcase import __version__
from showcase.cli import main


def test_run_creates_job_and_waits(tmp_path, capsys, sample_source):
    code = main(["run", sample_source, "--jobs-dir", str(tmp_path / "jobs")])
    out = capsys.readouterr().out
    assert code == 0
    assert "waiting_approval" in out
    jobs = list((tmp_path / "jobs").iterdir())
    assert len(jobs) == 1 and jobs[0].name.startswith("nearbyconnect-")


def test_approve_and_resume_finish(tmp_path, capsys, sample_source):
    main(["run", sample_source, "--jobs-dir", str(tmp_path / "jobs")])
    job_dir = str(next((tmp_path / "jobs").iterdir()))
    assert main(["approve", job_dir]) == 0
    assert main(["resume", job_dir]) == 0
    assert "status: done" in capsys.readouterr().out


def test_status_bad_path_exits_2(tmp_path, capsys):
    code = main(["status", str(tmp_path / "missing")])
    assert code == 2
    assert "job.json" in capsys.readouterr().err


def test_run_bad_source_exits_2(tmp_path, capsys):
    code = main(["run", "   ", "--jobs-dir", str(tmp_path)])
    assert code == 2
    assert "cannot name a project" in capsys.readouterr().err


def test_failed_job_exits_1(tmp_path, monkeypatch, sample_source):
    from showcase import cli
    from showcase.stages import StubStage, default_stages

    class Boom(StubStage):
        def run(self, job):
            raise RuntimeError("boom")

    def broken():
        stages = default_stages()
        stages[0] = Boom("analyze")
        return stages

    monkeypatch.setattr(cli, "default_stages", broken)
    assert main(["run", sample_source, "--jobs-dir", str(tmp_path / "jobs")]) == 1


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_status_shows_source(tmp_path, capsys, sample_source):
    main(["run", sample_source, "--jobs-dir", str(tmp_path / "jobs")])
    job_dir = str(next((tmp_path / "jobs").iterdir()))
    capsys.readouterr()
    assert main(["status", job_dir]) == 0
    assert f"source: {sample_source}" in capsys.readouterr().out


def test_approve_records_who(tmp_path, sample_source):
    import json

    main(["run", sample_source, "--jobs-dir", str(tmp_path / "jobs")])
    job_dir = next((tmp_path / "jobs").iterdir())
    assert main(["approve", str(job_dir), "--by", "reviewer"]) == 0
    record = json.loads((job_dir / "publish" / "approval.json").read_text())
    assert record["approved_by"] == "reviewer"
