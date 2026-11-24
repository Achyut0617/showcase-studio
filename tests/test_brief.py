from showcase.brief import build_brief_prompt
from showcase.codemap import build_code_map
from showcase.ingest import scan_tree


def make_repo(root, extra=None):
    files = {
        "README.md": "# Chatty\nA tiny chat server.\n",
        "requirements.txt": "flask\n",
        "app/__init__.py": "",
        "app/main.py": 'from .db import connect\nif __name__ == "__main__":\n    connect()\n',
        "app/db.py": '"""Database helpers."""\ndef connect():\n    """Open the DB."""\n',
        ".env": "SECRET_TOKEN=hunter2\n",
        **(extra or {}),
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    scan = scan_tree(root)
    ingest = {"source": str(root), **scan}
    return ingest, build_code_map(root, scan)


def test_prompt_contains_material_but_never_secrets(tmp_path):
    ingest, cm = make_repo(tmp_path)
    system, user = build_brief_prompt(tmp_path, ingest, cm)
    assert system.role == "system" and "JSON" in system.content
    text = user.content
    assert "A tiny chat server." in text
    assert "flask" in text
    assert "app/db.py — Database helpers." in text
    assert "connect (Open the DB.)" in text
    assert "entry point app/main.py" in text
    assert ".env" in text  # named, so the brief knows config exists
    assert "hunter2" not in text  # but never quoted


def test_prompt_respects_budget_and_says_what_was_cut(tmp_path):
    extra = {f"pkg/m{i:03}.py": f'"""Module {i} {"x" * 200}."""\n' for i in range(300)}
    ingest, cm = make_repo(tmp_path, extra)
    _, user = build_brief_prompt(tmp_path, ingest, cm, budget_chars=8_000)
    assert len(user.content) <= 8_000
    assert "more modules not shown" in user.content
    # the entry point is listed before ordinary modules, so it survives trimming
    assert "- app/main.py" in user.content


def test_huge_readme_cannot_crowd_out_modules(tmp_path):
    ingest, cm = make_repo(tmp_path, {"setup.cfg": "y" * 3_000, "Makefile": "z" * 3_000})
    (tmp_path / "README.md").write_text("w" * 50_000)
    _, user = build_brief_prompt(tmp_path, ingest, cm, budget_chars=6_000)
    assert len(user.content) <= 6_000
    assert "- app/main.py" in user.content
