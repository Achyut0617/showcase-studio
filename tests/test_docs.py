import json

import pytest

from showcase.docs import DocsError, load_analysis


def write_analysis(job, ingest=None, code_map=None, brief=None):
    ingest = ingest or {"source": "https://github.com/Achyut0617/NearbyConnect.git",
                        "repo_dir": "input/repo", "files": [], "languages": {},
                        "manifests": [], "sensitive_files": [], "primary_language": None,
                        "totals": {"files": 0, "bytes": 0, "code_lines": 0}}
    code_map = code_map or {"summary": {"modules": 0, "symbols": 0, "dependency_edges": 0,
                                        "entry_points": [], "hubs": []},
                            "modules": {}, "dependencies": [], "calls": [],
                            "external_packages": {}, "parse_errors": {}}
    (job / "ingest.json").write_text(json.dumps(ingest))
    (job / "code_map.json").write_text(json.dumps(code_map))
    if brief is not None:
        (job / "brief.json").write_text(json.dumps(brief))
    return job


def test_load_analysis_reads_files_and_names_project(tmp_path):
    a = load_analysis(write_analysis(tmp_path))
    assert a.brief is None
    assert a.name == "NearbyConnect"
    assert a.repo == tmp_path / "input" / "repo"


def test_brief_name_wins(tmp_path):
    a = load_analysis(write_analysis(tmp_path, brief={"name": "Nearby Connect"}))
    assert a.name == "Nearby Connect"


def test_missing_ingest_names_the_file(tmp_path):
    with pytest.raises(DocsError, match="ingest.json"):
        load_analysis(tmp_path)


def test_corrupt_code_map_names_the_file(tmp_path):
    write_analysis(tmp_path)
    (tmp_path / "code_map.json").write_text("{nope")
    with pytest.raises(DocsError, match="code_map.json"):
        load_analysis(tmp_path)
