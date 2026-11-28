from showcase.codemap import build_code_map, python_module_name
from showcase.ingest import scan_tree


def write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def code_map(root):
    return build_code_map(root, scan_tree(root))


def test_python_module_names():
    assert python_module_name("src/app/db.py") == "src.app.db"
    assert python_module_name("app/__init__.py") == "app"
    assert python_module_name("main.py") == "main"


def test_python_dependencies_resolved_inside_repo(tmp_path):
    write(tmp_path, {
        "src/app/__init__.py": "",
        "src/app/db.py": "import sqlite3\ndef connect():\n    pass\n",
        "src/app/models.py": "from .db import connect\n",
        "src/app/main.py": "from app import models\nimport requests\nimport os\n",
    })
    cm = code_map(tmp_path)
    deps = {(d["from"], d["to"]) for d in cm["dependencies"]}
    assert ("src/app/models.py", "src/app/db.py") in deps
    assert ("src/app/main.py", "src/app/models.py") in deps
    assert cm["modules"]["src/app/db.py"]["used_by"] == ["src/app/models.py"]
    # stdlib (sqlite3, os) is not an external package; requests is
    assert cm["external_packages"] == {"requests": 1}


def test_js_dependencies_and_packages(tmp_path):
    write(tmp_path, {
        "src/app.ts": "import express from 'express';\nimport { q } from './db';\n"
                      "import fs from 'node:fs';\nimport x from '@scope/pkg/sub';\n",
        "src/db.ts": "export function q() {}\n",
    })
    cm = code_map(tmp_path)
    assert cm["dependencies"] == [{"from": "src/app.ts", "to": "src/db.ts"}]
    assert cm["external_packages"] == {"express": 1, "@scope/pkg": 1}
    assert [s["name"] for s in cm["modules"]["src/db.ts"]["symbols"]] == ["q"]


def test_sensitive_and_unparseable_files(tmp_path):
    write(tmp_path, {
        "ok.py": "def f():\n    pass\n",
        "bad.py": "def (:\n",
        "notes.md": "# hi\n",
        ".env": "KEY=1\n",
    })
    cm = code_map(tmp_path)
    assert set(cm["modules"]) == {"ok.py", "bad.py"}
    assert list(cm["parse_errors"]) == ["bad.py"]


def test_python_call_graph_across_files(tmp_path):
    write(tmp_path, {
        "app/__init__.py": "",
        "app/db.py": "def connect():\n    pass\nclass Store:\n    def get(self):\n        pass\n",
        "app/service.py": (
            "from .db import connect, Store\n"
            "import app.db\n"
            "from app import db as dbmod\n"
            "def helper():\n    pass\n"
            "def run():\n"
            "    connect()\n"
            "    helper()\n"
            "    app.db.connect()\n"
            "    Store().get()\n"
            "    print('x')\n"
            "class Svc:\n"
            "    def a(self):\n        self.b()\n        self.missing()\n"
            "    def b(self):\n        pass\n"
        ),
    })
    calls = {(c["from"], c["to"]) for c in code_map(tmp_path)["calls"]}
    assert calls == {
        ("app/service.py::run", "app/db.py::connect"),
        ("app/service.py::run", "app/service.py::helper"),
        ("app/service.py::run", "app/db.py::Store"),
        ("app/service.py::Svc.a", "app/service.py::Svc.b"),
    }


def test_entry_points_and_hubs(tmp_path):
    write(tmp_path, {
        "pyproject.toml": '[project]\nname="x"\n[project.scripts]\ntool = "pkg.cli:main"\n',
        "package.json": '{"main": "./web/index.js", "bin": {"w": "web/bin.js"}}',
        "pkg/__init__.py": "",
        "pkg/cli.py": "from . import core\n",
        "pkg/core.py": "",
        "pkg/job.py": "from . import core\n",
        "run.py": 'import pkg.core\nif __name__ == "__main__":\n    pass\n',
        "web/index.js": "",
        "web/bin.js": "",
        "deep/a/b/main.py": "",
    })
    s = code_map(tmp_path)["summary"]
    entries = {e["path"]: e["why"] for e in s["entry_points"]}
    assert entries["pkg/cli.py"] == "pyproject script `tool`"
    assert entries["web/index.js"] == "package.json"
    assert entries["web/bin.js"] == "package.json"
    assert "run.py" in entries
    assert "deep/a/b/main.py" not in entries
    assert s["hubs"][0] == {"path": "pkg/core.py", "used_by": 3}


def test_broken_manifests_do_not_crash(tmp_path):
    write(tmp_path, {"package.json": "{not json", "pyproject.toml": "[[[", "a.py": ""})
    assert code_map(tmp_path)["summary"]["entry_points"] == []


def test_backend_in_subfolder_resolves_its_own_top_level_imports(tmp_path):
    from showcase.codemap import build_code_map, python_source_roots
    from showcase.ingest import scan_tree

    files = {
        "src/backend/requirements.txt": "fastapi\n",
        "src/backend/main.py": "from services.matching import match\nimport db\n",
        "src/backend/db.py": "def get_db():\n    pass\n",
        "src/backend/services/__init__.py": "",
        "src/backend/services/matching.py": "from models.user import User\n\n"
                                            "def match():\n    return User\n",
        "src/backend/models/__init__.py": "",
        "src/backend/models/user.py": "class User:\n    pass\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    assert python_source_roots(list(files)) == ["src/backend"]
    cm = build_code_map(tmp_path, scan_tree(tmp_path))
    deps = {(d["from"], d["to"]) for d in cm["dependencies"]}
    assert ("src/backend/main.py", "src/backend/services/matching.py") in deps
    assert ("src/backend/main.py", "src/backend/db.py") in deps
    assert ("src/backend/services/matching.py", "src/backend/models/user.py") in deps
    assert {"services", "models", "db"}.isdisjoint(cm["external_packages"])
