from showcase.cli import main

URL = "https://github.com/Achyut0617/NearbyConnect"


def test_run_creates_job_and_waits(tmp_path, capsys):
    code = main(["run", URL, "--jobs-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "waiting_approval" in out
    jobs = list(tmp_path.iterdir())
    assert len(jobs) == 1 and jobs[0].name.startswith("nearbyconnect-")


def test_approve_and_resume_finish(tmp_path, capsys):
    main(["run", URL, "--jobs-dir", str(tmp_path)])
    job_dir = str(next(tmp_path.iterdir()))
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


def test_failed_job_exits_1(tmp_path, monkeypatch):
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
    assert main(["run", URL, "--jobs-dir", str(tmp_path)]) == 1
