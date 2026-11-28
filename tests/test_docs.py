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


def _analysis_with(tmp_path, files: dict[str, str]):
    repo = tmp_path / "input" / "repo"
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    write_analysis(tmp_path, ingest={"source": "x", "repo_dir": "input/repo",
                                     "manifests": sorted(files), "files": []})
    return load_analysis(tmp_path)


def test_setup_steps_from_package_json_and_requirements(tmp_path):
    from showcase.docs import setup_steps

    a = _analysis_with(tmp_path, {
        "requirements.txt": "flask\n",
        "web/package.json": json.dumps({"scripts": {"dev": "vite", "test": "vitest"}}),
    })
    cmds = [(s.command, s.source, s.kind) for s in setup_steps(a)]
    assert cmds == [
        ("pip install -r requirements.txt", "requirements.txt", "install"),
        ("cd web && npm install", "web/package.json", "install"),
        ("cd web && npm run dev", "web/package.json", "run"),
        ("cd web && npm run test", "web/package.json", "test"),
    ]


def test_setup_steps_pyproject_scripts_and_bad_files(tmp_path):
    from showcase.docs import setup_steps

    a = _analysis_with(tmp_path, {
        "pyproject.toml": '[project]\nname="x"\n[project.scripts]\ntool = "x.cli:main"\n',
        "package.json": "{broken",
    })
    cmds = [s.command for s in setup_steps(a)]
    assert cmds == ["npm install", "pip install -e .", "tool --help"]


def test_env_var_names_reads_names_not_values(tmp_path):
    from showcase.docs import env_var_names

    repo = tmp_path / "input" / "repo"
    repo.mkdir(parents=True)
    (repo / ".env.example").write_text("# comment\nAPI_KEY=sk-real-looking\nexport DB_URL=x\n"
                                       "API_KEY=again\n")
    (repo / ".env").write_text("SECRET=1\n")
    files = [{"path": ".env.example", "sensitive": False, "skipped": None},
             {"path": ".env", "sensitive": True, "skipped": None}]
    write_analysis(tmp_path, ingest={"source": "x", "repo_dir": "input/repo", "files": files})
    found = env_var_names(load_analysis(tmp_path))
    assert found == {".env.example": ["API_KEY", "DB_URL"]}
    assert "sk-real" not in json.dumps(found)


def test_render_setup_sections_and_todos(tmp_path):
    from showcase.docs import render_setup

    a = _analysis_with(tmp_path, {"package.json": json.dumps({"scripts": {"start": "node ."}})})
    a.ingest["languages"] = {"JavaScript": {"kind": "code", "files": 1, "lines": 3},
                             "Markdown": {"kind": "docs", "files": 1, "lines": 1}}
    md = render_setup(a)
    assert md.startswith("# Setting up ")
    assert "- JavaScript" in md and "Markdown" not in md
    assert "npm install" in md and "npm start" in md
    assert "_From: `package.json`._" in md
    assert "## Test" not in md


def test_render_setup_without_manifests_leaves_todos(tmp_path):
    from showcase.docs import render_setup

    md = render_setup(_analysis_with(tmp_path, {}))
    assert md.count("TODO (author)") == 3


def test_render_architecture_from_code_map(tmp_path):
    from showcase.docs import render_architecture

    write_analysis(tmp_path, ingest={
        "source": "x/NearbyConnect", "repo_dir": "input/repo", "primary_language": "Python",
        "totals": {"files": 3, "code_lines": 40},
        "files": [{"path": "app/main.py"}, {"path": "app/db.py"},
                  {"path": ".env", "sensitive": True}],
    }, code_map={
        "summary": {"modules": 2, "symbols": 4,
                    "entry_points": [{"path": "app/main.py", "why": "conventional name"}],
                    "hubs": [{"path": "app/db.py", "used_by": 1}]},
        "modules": {"app/db.py": {"docstring": "Database access.\nMore."}},
        "dependencies": [{"from": "app/main.py", "to": "app/db.py"}],
        "external_packages": {"flask": 2},
    })
    md = render_architecture(load_analysis(tmp_path))
    assert "3 files, 40 lines of code; primary language Python" in md
    assert "└── main.py" in md and ".env" not in md
    assert "- `app/main.py` - found by conventional name" in md
    assert "```mermaid" in md
    assert "- `app/db.py` - imported by 1: Database access." in md
    assert "`flask`" in md
    assert "TODO (author)" in md  # no brief yet


def test_render_architecture_uses_brief_components(tmp_path):
    from showcase.docs import render_architecture

    write_analysis(tmp_path, brief={"architecture": [
        {"component": "API", "files": ["app/main.py"], "role": "serves requests"}]})
    md = render_architecture(load_analysis(tmp_path))
    assert "- **API** - serves requests (`app/main.py`)" in md
    assert "TODO" not in md


def test_render_readme_without_brief_uses_facts(tmp_path):
    from showcase.docs import render_readme

    a = _analysis_with(tmp_path, {"requirements.txt": "flask\n"})
    a.ingest["languages"] = {"Python": {"kind": "code", "lines": 120}}
    a.code_map["external_packages"] = {"flask": 3}
    md = render_readme(a)
    assert "TODO (author)" in md
    assert "- Python (120 lines)" in md and "`flask`" in md
    assert "pip install -r requirements.txt" in md
    assert "[SETUP.md](SETUP.md)" in md


def test_render_readme_with_brief(tmp_path):
    from showcase.docs import render_readme

    write_analysis(tmp_path, brief={"name": "NearbyConnect", "one_liner": "Finds people nearby.",
                                    "problem": "Hard to meet.", "how_it_works": ["a", "b"],
                                    "tech_stack": ["FastAPI"]})
    md = render_readme(load_analysis(tmp_path))
    assert md.startswith("# NearbyConnect\n\nFinds people nearby.")
    assert "1. a\n2. b" in md and "- FastAPI" in md and "TODO" not in md
