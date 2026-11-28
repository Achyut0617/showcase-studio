from showcase.tutorial import is_test_path, reading_order


def cm(entries, deps, hubs=()):
    mods = {}
    for a, bs in deps.items():
        mods.setdefault(a, {"depends_on": []})["depends_on"] = list(bs)
        for b in bs:
            mods.setdefault(b, {"depends_on": []})
    return {"modules": mods, "summary": {
        "entry_points": [{"path": e, "why": "x"} for e in entries],
        "hubs": [{"path": h, "used_by": 1} for h in hubs]}}


def test_is_test_path():
    assert is_test_path("src/backend/tests/test_api.py")
    assert is_test_path("web/src/App.test.tsx")
    assert is_test_path("conftest.py")
    assert not is_test_path("src/backend/routers/people.py")
    assert not is_test_path("src/latest.py")


def test_reading_order_is_breadth_first_from_entry_points_without_tests():
    m = cm(["main.py"], {"main.py": ["db.py", "routers/a.py", "tests/test_x.py"],
                         "routers/a.py": ["models/user.py", "db.py"]})
    assert reading_order(m) == ["main.py", "db.py", "routers/a.py", "models/user.py"]


def test_reading_order_falls_back_to_hubs_and_respects_limit():
    m = cm([], {"a.py": ["b.py"], "b.py": ["c.py"]}, hubs=["b.py"])
    assert reading_order(m) == ["b.py", "c.py"]
    assert reading_order(m, limit=1) == ["b.py"]


def test_render_tutorial_walks_setup_then_code(tmp_path):
    import json

    from showcase.docs import load_analysis
    from showcase.tutorial import render_tutorial

    repo = tmp_path / "input" / "repo"
    repo.mkdir(parents=True)
    (repo / "requirements.txt").write_text("fastapi\n")
    (repo / ".env.example").write_text("API_KEY=x\n")
    ingest = {"source": "https://github.com/Achyut0617/NearbyConnect.git", "repo_dir": "input/repo",
              "manifests": ["requirements.txt"],
              "files": [{"path": ".env.example", "sensitive": False, "skipped": None}]}
    code_map = {
        "summary": {"entry_points": [{"path": "main.py", "why": "conventional name"}], "hubs": []},
        "modules": {
            "main.py": {"doc": "Starts the API.", "depends_on": ["db.py"],
                        "symbols": [{"name": "health", "kind": "function", "line": 9,
                                     "doc": "Is the server alive?"}]},
            "db.py": {"doc": None, "depends_on": [], "symbols": []},
            "tests/test_main.py": {"doc": None, "depends_on": ["main.py"], "symbols": []},
        },
        "external_packages": {"pytest": 1, "fastapi": 1},
    }
    (tmp_path / "ingest.json").write_text(json.dumps(ingest))
    (tmp_path / "code_map.json").write_text(json.dumps(code_map))
    md = render_tutorial(load_analysis(tmp_path))
    assert "git clone https://github.com/Achyut0617/NearbyConnect.git\ncd NearbyConnect" in md
    assert "## 2. Install dependencies" in md and "pip install -r requirements.txt" in md
    assert "`.env.example` -> `API_KEY`" in md
    assert "TODO (author):** how to run it." in md
    assert "## 4. Run the tests" in md and "pytest -q" in md
    assert "### 5.1 `main.py`" in md and "**Start here**" in md
    assert "- `health` (function, line 9) - Is the server alive?" in md
    assert "Leads to: `db.py`" in md
    assert "### 5.2 `db.py`" in md and "test_main" not in md
