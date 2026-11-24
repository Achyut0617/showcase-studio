import json
from datetime import datetime

from showcase.analyzer import INGEST_FILE, AnalyzeStage
from showcase.job import Job


def make_job(source, tmp_path):
    return Job.create(source, tmp_path / "jobs", now=datetime(2026, 11, 30, 9, 0, 0))


def test_analyze_writes_ingest_json_and_log(tmp_path, sample_source):
    job = make_job(sample_source, tmp_path)
    AnalyzeStage().run(job)
    data = json.loads((job.path / INGEST_FILE).read_text())
    assert data["source"] == sample_source
    assert data["fetched"] == {"kind": "local"}
    assert data["repo_dir"] == "input/repo"
    assert data["primary_language"] == "Python"
    assert {f["path"] for f in data["files"]} == {"README.md", "app/main.py"}
    assert (job.path / "input" / "repo" / "app" / "main.py").exists()
    log = (job.path / "logs" / "analyze.log").read_text()
    assert "primary language: Python" in log


def test_analyze_mentions_sensitive_files_in_log(tmp_path, sample_source):
    from pathlib import Path

    (Path(sample_source) / ".env").write_text("KEY=1\n")
    job = make_job(sample_source, tmp_path)
    AnalyzeStage().run(job)
    assert ".env" in (job.path / "logs" / "analyze.log").read_text()


def test_analyze_passes_job_source_to_fetcher(tmp_path, sample_source):
    seen = {}

    def fake_fetch(source, dest):
        seen["source"], seen["dest"] = source, dest
        dest.mkdir(parents=True)
        (dest / "x.go").write_text("package main\n")
        return {"kind": "git", "commit": "deadbeef"}

    job = make_job(sample_source, tmp_path)
    AnalyzeStage(fetch=fake_fetch).run(job)
    assert seen == {"source": sample_source, "dest": job.path / "input" / "repo"}
    data = json.loads((job.path / INGEST_FILE).read_text())
    assert data["fetched"]["commit"] == "deadbeef"
    assert data["primary_language"] == "Go"


def test_analyze_writes_code_map(tmp_path, sample_source):
    from showcase.analyzer import CODE_MAP_FILE

    job = make_job(sample_source, tmp_path)
    AnalyzeStage().run(job)
    cm = json.loads((job.path / CODE_MAP_FILE).read_text())
    assert "app/main.py" in cm["modules"]
    assert cm["summary"]["entry_points"] == [{"path": "app/main.py", "why": "conventional name"}]
    assert "entry points: app/main.py" in (job.path / "logs" / "analyze.log").read_text()


def test_analyze_skips_brief_without_llm(tmp_path, sample_source):
    job = make_job(sample_source, tmp_path)
    AnalyzeStage().run(job)
    assert not (job.path / "brief.json").exists()
    assert "brief: skipped" in (job.path / "logs" / "analyze.log").read_text()


BRIEF = {
    "name": "NearbyConnect", "one_liner": "Says hello.", "problem": "p", "audience": "a",
    "how_it_works": ["app/main.py prints"], "architecture": [],
    "tech_stack": ["Python"], "entry_points": [{"path": "app/main.py", "what": "run"}],
    "how_to_run": ["python app/main.py"], "notable": [], "open_questions": [],
}


def test_analyze_writes_brief_with_llm_and_retries_once(tmp_path, sample_source):
    from showcase.llm import FakeLLM

    llm = FakeLLM(["sorry, no json", json.dumps(BRIEF)])
    job = make_job(sample_source, tmp_path)
    AnalyzeStage(llm=llm).run(job)
    brief = json.loads((job.path / "brief.json").read_text())
    assert brief["name"] == "NearbyConnect" and brief["model"] == "fake-model"
    assert (job.path / "brief.md").read_text().startswith("# NearbyConnect")
    assert len(llm.prompts) == 2 and "could not be used" in llm.prompts[1][-1].content
    usage = (job.path / "logs" / "llm_usage.jsonl").read_text().splitlines()
    assert [json.loads(u)["agent"] for u in usage] == ["analyzer.brief", "analyzer.brief.retry"]


def test_analyze_fails_after_second_bad_reply(tmp_path, sample_source):
    import pytest

    from showcase.brief import BriefError
    from showcase.llm import FakeLLM

    job = make_job(sample_source, tmp_path)
    with pytest.raises(BriefError):
        AnalyzeStage(llm=FakeLLM(["nope", "still nope"])).run(job)
    assert not (job.path / "brief.json").exists()
