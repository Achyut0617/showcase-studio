import os
import subprocess

import pytest

from showcase.ingest import (
    IngestError,
    detect_language,
    fetch_source,
    is_remote,
    scan_tree,
)


def write(root, rel, text="", data=None):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        p.write_bytes(data)
    else:
        p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    write(root, "app/main.py", "import os\n\nprint('hi')\n")
    write(root, "app/util.py", "def f():\n    return 1\n")
    write(root, "web/App.tsx", "export const A = () => null;\n")
    write(root, "README.md", "# Proj\n")
    write(root, "package.json", "{}\n")
    write(root, "pyproject.toml", "[project]\nname='p'\n")
    write(root, "Dockerfile", "FROM python:3.12\n")
    write(root, ".env", "API_KEY=secret\n")
    write(root, ".env.example", "API_KEY=\n")
    write(root, "logo.png", data=b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    write(root, "node_modules/lib/index.js", "module.exports = 1\n")
    write(root, ".git/HEAD", "ref: refs/heads/main\n")
    return root


# --- language detection ---------------------------------------------------


@pytest.mark.parametrize(
    "name,lang",
    [
        ("a.py", "Python"),
        ("a.tsx", "TypeScript"),
        ("a.jsx", "JavaScript"),
        ("a.c", "C"),
        ("a.h", "C"),
        ("a.cpp", "C++"),
        ("Dockerfile", "Dockerfile"),
        ("Makefile", "Makefile"),
        ("CMakeLists.txt", "CMake"),
        ("README.md", "Markdown"),
        ("package-lock.json", "Lockfile"),
        ("data.weird", None),
    ],
)
def test_detect_language_by_name(tmp_path, name, lang):
    p = write(tmp_path, name, "x\n")
    assert detect_language(p) == lang


def test_detect_language_from_shebang(tmp_path):
    p = write(tmp_path, "bin/run", "#!/usr/bin/env python3\nprint(1)\n")
    assert detect_language(p) == "Python"
    q = write(tmp_path, "bin/go", "#!/bin/bash\necho hi\n")
    assert detect_language(q) == "Shell"


# --- tree scan ------------------------------------------------------------


def test_scan_counts_languages_and_picks_primary(project):
    result = scan_tree(project)
    langs = result["languages"]
    assert langs["Python"] == {"files": 2, "lines": 5, "kind": "code"}
    assert langs["TypeScript"]["files"] == 1
    assert result["primary_language"] == "Python"  # Markdown/TOML never win


def test_scan_skips_vendor_and_git_dirs(project):
    paths = {f["path"] for f in scan_tree(project)["files"]}
    assert "app/main.py" in paths
    assert not any(p.startswith(("node_modules/", ".git/")) for p in paths)
    assert set(scan_tree(project)["skipped_dirs"]) >= {"node_modules", ".git"}


def test_scan_uses_posix_relative_paths(project):
    for f in scan_tree(project)["files"]:
        assert "\\" not in f["path"] and not f["path"].startswith("/")


def test_binary_files_are_flagged_and_not_line_counted(project):
    files = {f["path"]: f for f in scan_tree(project)["files"]}
    assert files["logo.png"]["binary"] is True
    assert files["logo.png"]["lines"] is None


def test_secret_files_flagged_but_examples_are_not(project):
    files = {f["path"]: f for f in scan_tree(project)["files"]}
    assert files[".env"]["sensitive"] is True
    assert files[".env.example"]["sensitive"] is False
    assert ".env" in scan_tree(project)["sensitive_files"]


def test_manifests_found(project):
    assert set(scan_tree(project)["manifests"]) == {"package.json", "pyproject.toml", "Dockerfile"}


def test_large_files_not_line_counted(project):
    write(project, "big.py", "x = 1\n" * 50)
    files = {f["path"]: f for f in scan_tree(project, max_file_bytes=100)["files"]}
    assert files["big.py"]["lines"] is None
    assert files["big.py"]["skipped"] == "too_large"


@pytest.mark.skipif(os.name == "nt", reason="symlinks need admin on Windows")
def test_symlinks_are_never_followed(project, tmp_path):
    outside = write(tmp_path, "outside/secret.txt", "top secret\n")
    (project / "link.txt").symlink_to(outside)
    (project / "linkdir").symlink_to(outside.parent, target_is_directory=True)
    files = {f["path"]: f for f in scan_tree(project)["files"]}
    assert files["link.txt"]["skipped"] == "symlink"
    assert files["link.txt"]["lines"] is None
    assert not any(p.startswith("linkdir/") for p in files)


def test_totals(project):
    totals = scan_tree(project)["totals"]
    assert totals["files"] == len(scan_tree(project)["files"])
    assert totals["code_lines"] == 6  # 5 Python + 1 TypeScript


# --- source fetching ------------------------------------------------------


@pytest.mark.parametrize(
    "src,remote",
    [
        ("https://github.com/Achyut0617/NearbyConnect", True),
        ("git@github.com:Achyut0617/NearbyConnect.git", True),
        ("ssh://git@github.com/a/b.git", True),
        ("/home/me/project", False),
        ("C:\\code\\proj", False),
    ],
)
def test_is_remote(src, remote):
    assert is_remote(src) is remote


@pytest.mark.parametrize(
    "src",
    [
        "ext::sh -c touch% /tmp/pwned",  # git's ext transport runs commands
        "--upload-pack=touch /tmp/pwned",
        "file:///etc",
        "http://github.com/a/b",  # plain http not allowed
    ],
)
def test_fetch_rejects_unsafe_sources(tmp_path, src):
    with pytest.raises(IngestError):
        fetch_source(src, tmp_path / "repo")


def test_fetch_missing_local_folder_raises(tmp_path):
    with pytest.raises(IngestError, match="not found"):
        fetch_source(str(tmp_path / "nope"), tmp_path / "repo")


def test_fetch_local_copies_without_vendor_dirs(project, tmp_path):
    dest = tmp_path / "job" / "repo"
    info = fetch_source(str(project), dest)
    assert (dest / "app" / "main.py").exists()
    assert not (dest / "node_modules").exists()
    assert info["kind"] == "local"


def test_fetch_remote_builds_safe_git_command(tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if "clone" in args:
            (tmp_path / "repo").mkdir()
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "abc123\n", "")

    info = fetch_source("https://github.com/a/b", tmp_path / "repo", runner=fake_run)
    clone_args, kwargs = calls[0]
    assert clone_args[0] == "git" and "clone" in clone_args
    assert "--depth" in clone_args
    assert "protocol.allow=never" in clone_args  # blocks ext::, file:// etc. even if parsed
    i = clone_args.index("--")
    assert clone_args[i + 1 :] == ["https://github.com/a/b", str(tmp_path / "repo")]
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs.get("shell") in (None, False)
    assert info == {"kind": "git", "commit": "abc123"}


def test_fetch_remote_failure_raises_with_git_message(tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 128, "", "fatal: repository not found\n")

    with pytest.raises(IngestError, match="repository not found"):
        fetch_source("https://github.com/a/missing", tmp_path / "repo", runner=fake_run)


def test_fetch_replaces_leftover_folder_from_crashed_run(project, tmp_path):
    dest = tmp_path / "repo"
    write(dest, "stale.txt", "old\n")
    fetch_source(str(project), dest)
    assert not (dest / "stale.txt").exists()


def test_lock_files_are_generated_not_data(project):
    write(project, "package-lock.json", "{\n}\n" * 500)
    langs = scan_tree(project)["languages"]
    assert langs["Lockfile"]["kind"] == "generated"
    assert "JSON" not in langs or langs["JSON"]["lines"] < 10
