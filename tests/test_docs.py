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


def test_render_tree_folders_first_and_nested():
    from showcase.docs import render_tree

    out = render_tree(["README.md", "app/main.py", "app/db/models.py"])
    assert out.splitlines() == [
        "├── app/",
        "│   ├── db/",
        "│   │   └── models.py",
        "│   └── main.py",
        "└── README.md",
    ]


def test_render_tree_cuts_depth_and_size():
    from showcase.docs import render_tree

    deep = render_tree(["a/b/c/d/e.py"], max_depth=2)
    assert "e.py" not in deep and "b/" in deep
    big = render_tree([f"f{i:03}.py" for i in range(100)], max_entries=10)
    assert big.splitlines()[-1] == "... 90 more"


def test_dependency_diagram_draws_edges_with_safe_ids():
    from showcase.docs import dependency_diagram

    cm = {"dependencies": [{"from": "app/main.py", "to": "app/db.py"}]}
    out = dependency_diagram(cm)
    assert out.startswith("```mermaid\ngraph LR")
    assert 'm_app_main_py["app/main.py"]' in out
    assert "m_app_main_py --> m_app_db_py" in out


def test_dependency_diagram_none_without_imports_and_caps_nodes():
    from showcase.docs import dependency_diagram

    assert dependency_diagram({"dependencies": []}) is None
    deps = [{"from": "hub.py", "to": f"m{i}.py"} for i in range(30)]
    out = dependency_diagram({"dependencies": deps}, max_nodes=5)
    assert out.count('"]') == 5
    assert "26 less-connected modules" in out
