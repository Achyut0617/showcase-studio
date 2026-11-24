import json

import pytest

from showcase.brief import BriefError, build_brief_prompt, parse_brief_reply, render_brief_md
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


def good_reply(**over):
    data = {
        "name": "Chatty",
        "one_liner": "A tiny chat server.",
        "problem": "Talk to people nearby.",
        "audience": "Students",
        "how_it_works": ["app/main.py calls connect() in app/db.py"],
        "architecture": [
            {"component": "Storage", "files": ["app/db.py", "app/ghost.py"], "role": "DB"}
        ],
        "tech_stack": ["Python", "Flask"],
        "entry_points": [
            {"path": "app/main.py", "what": "python -m app.main"},
            {"path": "server.py", "what": "invented"},
        ],
        "how_to_run": ["pip install -r requirements.txt"],
        "notable": ["Relative imports"],
        "open_questions": ["Which database?"],
    }
    data.update(over)
    return data


KNOWN = {"app/main.py", "app/db.py", "README.md"}


def test_parse_drops_made_up_paths():
    brief = parse_brief_reply("```json\n" + json.dumps(good_reply()) + "\n```", KNOWN)
    assert brief["architecture"][0]["files"] == ["app/db.py"]
    assert [e["path"] for e in brief["entry_points"]] == ["app/main.py"]
    assert brief["unverified_paths"] == ["app/ghost.py", "server.py"]


def test_parse_accepts_prose_around_json():
    brief = parse_brief_reply("Here you go:\n" + json.dumps(good_reply()) + "\nThanks", KNOWN)
    assert brief["name"] == "Chatty"


@pytest.mark.parametrize("reply,msg", [
    ("no json here", "no JSON object"),
    ("{broken", "no JSON object"),
    ('{"a": }', "not valid JSON"),
    (json.dumps({"name": "x"}), "missing keys"),
    (json.dumps(good_reply(tech_stack="Python")), "`tech_stack` must be a list"),
    (json.dumps(good_reply(entry_points=[{"what": "x"}])), "need a `path`"),
])
def test_parse_rejects_bad_replies(reply, msg):
    with pytest.raises(BriefError, match=msg):
        parse_brief_reply(reply, KNOWN)


def test_render_markdown():
    md = render_brief_md(parse_brief_reply(json.dumps(good_reply()), KNOWN))
    assert md.startswith("# Chatty\n\n_A tiny chat server._")
    assert "| Storage | `app/db.py` | DB |" in md
    assert "- `app/main.py` — python -m app.main" in md
    assert "1. pip install -r requirements.txt" in md
    assert "## Removed claims" in md and "`server.py`" in md
