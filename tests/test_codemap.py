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
