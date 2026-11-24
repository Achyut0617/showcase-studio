"""Repo ingestion (T1.2): fetch a project into the job and map its files and languages.

Nothing here runs the project's own code. Cloning uses an argument list (never a
shell), only https/ssh sources, no submodules, no LFS downloads and no prompts.
Symlinks are recorded but never followed, so a repo cannot point the scan at files
outside itself.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", "bower_components", ".venv", "venv", "env",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist",
        "build", "target", ".next", ".nuxt", ".gradle", ".idea", ".vscode", "coverage",
        ".pio", ".dart_tool", "Pods", ".terraform",
    }
)

# name -> (language, kind). kind decides what counts as "code" for the primary language.
_EXT: dict[str, tuple[str, str]] = {
    ".py": ("Python", "code"), ".pyi": ("Python", "code"), ".ipynb": ("Jupyter", "code"),
    ".js": ("JavaScript", "code"), ".mjs": ("JavaScript", "code"),
    ".cjs": ("JavaScript", "code"), ".jsx": ("JavaScript", "code"),
    ".ts": ("TypeScript", "code"), ".tsx": ("TypeScript", "code"),
    ".java": ("Java", "code"), ".kt": ("Kotlin", "code"), ".kts": ("Kotlin", "code"),
    ".c": ("C", "code"), ".h": ("C", "code"),
    ".cpp": ("C++", "code"), ".cc": ("C++", "code"), ".cxx": ("C++", "code"),
    ".hpp": ("C++", "code"), ".hh": ("C++", "code"), ".ino": ("Arduino", "code"),
    ".cs": ("C#", "code"), ".go": ("Go", "code"), ".rs": ("Rust", "code"),
    ".rb": ("Ruby", "code"), ".php": ("PHP", "code"), ".swift": ("Swift", "code"),
    ".dart": ("Dart", "code"), ".scala": ("Scala", "code"), ".r": ("R", "code"),
    ".m": ("Objective-C", "code"), ".lua": ("Lua", "code"), ".sol": ("Solidity", "code"),
    ".sh": ("Shell", "code"), ".bash": ("Shell", "code"), ".ps1": ("PowerShell", "code"),
    ".sql": ("SQL", "code"), ".v": ("Verilog", "code"), ".sv": ("SystemVerilog", "code"),
    ".vhd": ("VHDL", "code"), ".s": ("Assembly", "code"), ".asm": ("Assembly", "code"),
    ".html": ("HTML", "markup"), ".htm": ("HTML", "markup"), ".css": ("CSS", "markup"),
    ".scss": ("SCSS", "markup"), ".vue": ("Vue", "code"), ".svelte": ("Svelte", "code"),
    ".json": ("JSON", "data"), ".yaml": ("YAML", "data"), ".yml": ("YAML", "data"),
    ".toml": ("TOML", "data"), ".xml": ("XML", "data"), ".ini": ("INI", "data"),
    ".csv": ("CSV", "data"), ".proto": ("Protocol Buffers", "code"),
    ".md": ("Markdown", "docs"), ".rst": ("reStructuredText", "docs"),
    ".txt": ("Text", "docs"),
}
_NAMES: dict[str, tuple[str, str]] = {
    "Dockerfile": ("Dockerfile", "build"), "Makefile": ("Makefile", "build"),
    "CMakeLists.txt": ("CMake", "build"), "Jenkinsfile": ("Groovy", "build"),
    "Procfile": ("Procfile", "build"), "Gemfile": ("Ruby", "build"),
    # lock files are machine-generated: listed, but never mistaken for the project's code
    "package-lock.json": ("Lockfile", "generated"), "yarn.lock": ("Lockfile", "generated"),
    "pnpm-lock.yaml": ("Lockfile", "generated"), "poetry.lock": ("Lockfile", "generated"),
    "Pipfile.lock": ("Lockfile", "generated"), "Cargo.lock": ("Lockfile", "generated"),
    "composer.lock": ("Lockfile", "generated"), "Gemfile.lock": ("Lockfile", "generated"),
    "go.sum": ("Lockfile", "generated"), "uv.lock": ("Lockfile", "generated"),
}
_SHEBANG = {
    "python": "Python", "node": "JavaScript", "bash": "Shell", "sh": "Shell",
    "zsh": "Shell", "ruby": "Ruby", "perl": "Perl",
}
_KIND = {lang: kind for lang, kind in [*_EXT.values(), *_NAMES.values()]}
_KIND.update({"Perl": "code"})

MANIFESTS = frozenset(
    {
        "package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
        "Pipfile", "environment.yml", "pom.xml", "build.gradle", "build.gradle.kts",
        "Cargo.toml", "go.mod", "CMakeLists.txt", "Makefile", "platformio.ini",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml",
        "Gemfile", "composer.json", "pubspec.yaml", "*.csproj", "*.sln",
    }
)

_SENSITIVE_NAME = re.compile(
    r"^(\.env(\..+)?|.*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|dsa|ecdsa|ed25519)"
    r"|credentials\.json|service-account.*\.json|\.npmrc|\.pypirc|\.netrc)$",
    re.IGNORECASE,
)
_NOT_SENSITIVE = re.compile(r"\.(example|sample|template|dist)$", re.IGNORECASE)

_REMOTE = re.compile(r"^(https://|ssh://|git@[\w.-]+:)", re.IGNORECASE)

Runner = Callable[..., subprocess.CompletedProcess]


class IngestError(Exception):
    """The project could not be fetched."""


# --- languages ------------------------------------------------------------


def detect_language(path: Path) -> str | None:
    """Language of one file from its name, extension, or ``#!`` line; None if unknown."""
    path = Path(path)
    if path.name in _NAMES:
        return _NAMES[path.name][0]
    ext = path.suffix.lower()
    if ext in _EXT:
        return _EXT[ext][0]
    if ext == "":
        try:
            with path.open("rb") as fh:
                first = fh.readline(200)
        except OSError:
            return None
        if first.startswith(b"#!"):
            words = first[2:].decode("utf-8", "replace").replace("/", " ").split()
            for word in reversed(words):
                name = re.sub(r"[\d.]+$", "", word)
                if name in _SHEBANG:
                    return _SHEBANG[name]
    return None


def _is_manifest(name: str) -> bool:
    return name in MANIFESTS or any(
        m.startswith("*") and name.endswith(m[1:]) for m in MANIFESTS
    )


def _is_sensitive(name: str) -> bool:
    return bool(_SENSITIVE_NAME.match(name)) and not _NOT_SENSITIVE.search(name)


# --- tree scan ------------------------------------------------------------


def scan_tree(root: Path, max_file_bytes: int = 1_000_000) -> dict:
    """Map every file under ``root``: path, size, language, line count and flags.

    Vendor/build folders are pruned, symlinks are listed but not followed, binary
    files and files over ``max_file_bytes`` are not line-counted. Sensitive files
    (``.env``, keys) are flagged so later agents never send their contents to an LLM.
    """
    root = Path(root)
    files: list[dict] = []
    skipped_dirs: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        keep = []
        for d in sorted(dirnames):
            full = here / d
            if d in SKIP_DIRS:
                skipped_dirs.add(d)
            elif full.is_symlink():
                files.append(_entry(root, full, skipped="symlink"))
            else:
                keep.append(d)
        dirnames[:] = keep
        for name in sorted(filenames):
            files.append(_scan_file(root, here / name, max_file_bytes))
    files.sort(key=lambda f: f["path"])

    languages: dict[str, dict] = {}
    for f in files:
        lang = f["language"]
        if lang is None:
            continue
        slot = languages.setdefault(lang, {"files": 0, "lines": 0, "kind": _KIND[lang]})
        slot["files"] += 1
        slot["lines"] += f["lines"] or 0

    code = {k: v for k, v in languages.items() if v["kind"] == "code"}
    primary = max(code, key=lambda k: (code[k]["lines"], code[k]["files"]), default=None)
    return {
        "files": files,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1]["lines"])),
        "primary_language": primary,
        "manifests": sorted(f["path"] for f in files if _is_manifest(Path(f["path"]).name)),
        "sensitive_files": [f["path"] for f in files if f["sensitive"]],
        "skipped_dirs": sorted(skipped_dirs),
        "totals": {
            "files": len(files),
            "bytes": sum(f["size"] or 0 for f in files),
            "code_lines": sum(v["lines"] for v in code.values()),
        },
    }


def _entry(root: Path, path: Path, **overrides) -> dict:
    entry = {
        "path": path.relative_to(root).as_posix(),
        "size": None,
        "language": None,
        "lines": None,
        "binary": False,
        "sensitive": _is_sensitive(path.name),
        "skipped": None,
    }
    entry.update(overrides)
    return entry


def _scan_file(root: Path, path: Path, max_file_bytes: int) -> dict:
    if path.is_symlink():
        return _entry(root, path, skipped="symlink")
    try:
        size = path.stat().st_size
    except OSError:
        return _entry(root, path, skipped="unreadable")
    entry = _entry(root, path, size=size, language=detect_language(path))
    if size > max_file_bytes:
        entry["skipped"] = "too_large"
        return entry
    try:
        data = path.read_bytes()
    except OSError:
        entry["skipped"] = "unreadable"
        return entry
    if b"\x00" in data[:8192]:
        entry["binary"] = True
        entry["language"] = None
        return entry
    entry["lines"] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
    return entry


# --- fetching -------------------------------------------------------------


def is_remote(source: str) -> bool:
    return bool(_REMOTE.match(source.strip()))


def fetch_source(
    source: str, dest: Path, *, timeout: int = 300, runner: Runner = subprocess.run
) -> dict:
    """Put the project at ``source`` into ``dest`` (replacing any leftover copy).

    Remote: shallow ``git clone`` of an https/ssh URL. Local: copy of an existing
    folder without vendor/build directories. Returns ``{"kind", "commit"?}``.
    """
    source = source.strip()
    dest = Path(dest)
    if is_remote(source):
        _clear(dest)
        return _clone(source, dest, timeout, runner)
    if "::" in source or source.startswith("-") or re.match(r"^[a-z][\w+.-]*://", source, re.I):
        raise IngestError(
            f"unsupported source {source!r}: use an https:// or git@ URL, or a local folder"
        )
    src = Path(source).expanduser()
    if not src.is_dir():
        raise IngestError(f"local folder not found: {source}")
    _clear(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, symlinks=True, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    return {"kind": "local"}


def _clear(dest: Path) -> None:
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)


def _clone(source: str, dest: Path, timeout: int, runner: Runner) -> dict:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",  # private/missing repo fails fast instead of hanging
        "GIT_LFS_SKIP_SMUDGE": "1",  # don't pull large LFS blobs
        "GIT_ASKPASS": "",
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
        "-c", "protocol.ssh.allow=always",
        "clone", "--depth", "1", "--no-tags", "--single-branch",
        "--", source, str(dest),
    ]
    try:
        result = runner(args, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise IngestError(f"git clone timed out after {timeout}s: {source}") from exc
    except FileNotFoundError as exc:
        raise IngestError("git is not installed or not on PATH") from exc
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise IngestError(f"git clone failed for {source}: {' '.join(tail)}")
    head = runner(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    commit = head.stdout.strip() if head.returncode == 0 else None
    return {"kind": "git", "commit": commit}
