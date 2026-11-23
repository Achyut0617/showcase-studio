# Stage 0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable skeleton: `showcase run <github-url-or-folder>` creates a job folder and walks all 11 stages as stubs, resumable, with an approval gate before publish and a hardened Docker sandbox command.

**Architecture:** `src/showcase/` package. `source.py` names a project from its source; `job.py` owns the job folder and `job.json`; `stages.py` defines the fixed stage order and stub stages; `orchestrator.py` runs them in order with resume and an approval gate; `sandbox.py` builds the locked-down `docker run` command; `cli.py` exposes it.

**Tech Stack:** Python ≥ 3.11, stdlib only at runtime (argparse, json, dataclasses, pathlib). Dev: pytest, ruff. Docker for the sandbox image. GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-11-23-project-showcase-studio-design.md`

## Global Constraints

- Python for orchestrator and agents; runtime has no third-party dependencies in Stage 0.
- Job folder layout exactly: `job.json input/ clips/ narration/ video/ docs/ publish/ logs/` under `jobs/<project-name>-<YYYYMMDD-HHMMSS>/`.
- Stage order (fixed): `analyze, research_style, write_docs, run, plan_demo, record, write_script, voice, edit_video, review, publish`.
- Publish never runs unless `publish/approval.json` exists.
- Sandbox: network off by default, memory and CPU limits, non-root user, all capabilities dropped, `no-new-privileges`, only the job's `input/` mounted.
- Commit messages carry the task ID, e.g. `T0.2: orchestrator skeleton (3h)`.

## Review Focus

1. Source given as `git@github.com:user/repo.git`, with a trailing `/`, or with `.git` → same clean project name `repo`.
2. Two jobs for the same project started in the same second → second folder must not overwrite the first.
3. Process killed mid-stage (stage left `running` in job.json) → `resume` re-runs that stage instead of skipping it.
4. Corrupted or missing `job.json` → clear error message naming the file, not a raw traceback.
5. Job path containing spaces → sandbox command still mounts it correctly (argument list, never a shell string).

---

### Task 1 (T0.1): Repo layout, tooling, CI

**Files:**
- Create: `pyproject.toml`, `src/showcase/__init__.py`, `.gitignore`, `.github/workflows/ci.yml`, `README.md`, `tests/__init__.py`

- [ ] **Step 1:** `pyproject.toml` with project name `project-showcase-studio`, `requires-python = ">=3.11"`, src layout, script `showcase = "showcase.cli:main"`, optional dev deps `pytest>=8`, `ruff>=0.5`; ruff line-length 100.
- [ ] **Step 2:** `.gitignore` ignores `jobs/`, `.venv/`, `__pycache__/`, `.env`, `voice-samples/`.
- [ ] **Step 3:** CI on push/PR: Python 3.11 and 3.12, `pip install -e .[dev]`, `ruff check .`, `pytest -q`.
- [ ] **Step 4:** README: one-line pitch, status (Stage 0), quick start, commit convention (T/E/D IDs), links to design doc and tracker.
- [ ] **Step 5:** Verify `pip install -e .[dev] && ruff check . && pytest -q` (0 tests OK). Commit `T0.1: repo layout, tooling, CI`.

### Task 2 (T0.2a): Project name from source

**Files:** Create `src/showcase/source.py`; Test `tests/test_source.py`

**Interfaces:** Produces `project_name_from_source(source: str) -> str` (lowercase slug of `[a-z0-9-]`, raises `ValueError` on empty result).

- [ ] **Step 1: failing tests**
```python
@pytest.mark.parametrize("src,expected", [
    ("https://github.com/Achyut0617/NearbyConnect", "nearbyconnect"),
    ("https://github.com/Achyut0617/NearbyConnect.git", "nearbyconnect"),
    ("https://github.com/Achyut0617/NearbyConnect/", "nearbyconnect"),
    ("git@github.com:Achyut0617/StealthLedger-v1.git", "stealthledger-v1"),
    ("/home/me/My Project", "my-project"),
    ("C:\\code\\Smart_Scholar", "smart-scholar"),
])
def test_project_name(src, expected): ...
def test_empty_source_raises(): with pytest.raises(ValueError): project_name_from_source("  ")
```
- [ ] **Step 2:** run, expect FAIL. **Step 3:** implement (split on `/`, `\`, `:`; strip `.git`; slugify). **Step 4:** PASS. **Step 5:** commit `T0.2: project name from source`.

### Task 3 (T0.2b): Job folder and state

**Files:** Create `src/showcase/job.py`; Test `tests/test_job.py`

**Interfaces:**
- Produces `JOB_SUBDIRS = ("input","clips","narration","video","docs","publish","logs")`
- `class JobError(Exception)`
- `@dataclass class Job: path: Path; project_name: str; source: str; created_at: str; stages: dict[str, dict]`
  - `Job.create(source: str, jobs_root: Path, now: datetime | None = None) -> Job` — makes folder + subdirs + `job.json`; on name collision appends `-2`, `-3`…
  - `Job.load(path: Path) -> Job` — raises `JobError` naming `job.json` if missing or invalid JSON
  - `job.save() -> None` — atomic write (temp file + replace)
  - `job.set_stage(name: str, status: str, error: str | None = None) -> None` — status in `{"pending","running","done","failed","waiting_approval"}`, records `updated_at`, saves
  - `job.status_of(name: str) -> str` — `"pending"` if unseen

- [ ] **Step 1: failing tests:** `test_create_makes_layout` (all subdirs + job.json, name `nearbyconnect-20261130-090000` for fixed `now`), `test_same_second_collision_gets_suffix` (second create → `...-2`), `test_load_roundtrip`, `test_load_missing_raises_joberror` and `test_load_corrupt_raises_joberror` (message contains `job.json`), `test_set_stage_rejects_unknown_status`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `T0.2: job folder and state`.

### Task 4 (T0.2c): Stages and orchestrator

**Files:** Create `src/showcase/stages.py`, `src/showcase/orchestrator.py`; Test `tests/test_orchestrator.py`

**Interfaces:**
- `STAGE_ORDER: tuple[str, ...]` (Global Constraints order)
- `class Stage(Protocol): name: str; def run(self, job: Job) -> None`
- `class StubStage: __init__(self, name: str)`; `run` writes `logs/<name>.log` with one line `stub: <name> ran at <iso time>`
- `class ApprovalRequired(Exception)`
- `class PublishStage(StubStage)` — raises `ApprovalRequired` unless `job.path/"publish"/"approval.json"` exists
- `default_stages() -> list[Stage]` — one per `STAGE_ORDER`, publish = `PublishStage`
- `run_job(job: Job, stages: list[Stage]) -> str` — returns final status: `"done"`, `"failed"`, or `"waiting_approval"`. Skips stages already `done`; re-runs `running`/`failed`/`pending`; on `ApprovalRequired` marks `waiting_approval` and stops; on other exception marks `failed` with `str(exc)` and stops.
- `approve(job: Job, by: str = "achyut") -> None` — writes `publish/approval.json` `{"approved_by", "approved_at"}`.

- [ ] **Step 1: failing tests:** `test_full_run_waits_for_approval` (all stages before publish `done`, publish `waiting_approval`); `test_approve_then_resume_finishes` (returns `done`); `test_failure_stops_and_records_error` (a stage raising `RuntimeError("boom")` → `failed`, error `"boom"`, later stages `pending`); `test_resume_skips_done_and_reruns_running` (pre-set `analyze=done`, `research_style=running` → analyze log not rewritten, research_style re-run).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `T0.2: stages and orchestrator`.

### Task 5 (T0.2d): CLI

**Files:** Create `src/showcase/cli.py`; Test `tests/test_cli.py`

**Interfaces:** `main(argv: list[str] | None = None) -> int`. Subcommands: `run <source> [--jobs-dir jobs]`, `resume <job_dir>`, `status <job_dir>`, `approve <job_dir>`. Prints the job path and a stage table; `JobError` → message on stderr, exit 2.

- [ ] **Step 1: failing tests:** `test_run_creates_job_and_waits` (exit 0, output contains `waiting_approval`), `test_status_bad_path_exits_2`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** commit `T0.2: command-line interface`.

### Task 6 (T0.3): Docker sandbox

**Files:** Create `sandbox/Dockerfile`, `src/showcase/sandbox.py`; Test `tests/test_sandbox.py`

**Interfaces:** `@dataclass class SandboxLimits: cpus: float = 2.0; memory: str = "4g"; pids: int = 256; network: bool = False` and `docker_run_args(image: str, input_dir: Path, command: list[str], limits: SandboxLimits = SandboxLimits()) -> list[str]`.

- [ ] **Step 1: failing tests:** args contain `--network none` (and not when `network=True`), `--memory 4g`, `--cpus 2.0`, `--pids-limit 256`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user runner`, `--rm`; exactly one `-v` whose value is `<abs input_dir>:/work` even when the path has spaces; command appended last.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5:** Dockerfile: `python:3.12-slim`, install `git nodejs npm`, create user `runner` (uid 1000), `WORKDIR /work`, `USER runner`. Verify `docker build -t showcase-sandbox:base sandbox/` succeeds (if Docker is available).
- [ ] **Step 6:** commit `T0.3: Docker sandbox base`.

### Task 7 (T0.4): Voice sample guide

**Files:** Create `docs/voice-recording-guide.md`

- [ ] **Step 1:** Guide: room/mic setup, format (WAV, 44.1/48 kHz, mono), 3 sessions × 10 min of reading technical text in his natural explaining voice, script prompts, file naming `voice-samples/session-01.wav`, privacy (never committed — `.gitignore`), checklist.
- [ ] **Step 2:** commit `T0.4: voice recording guide`.

### Finish
- [ ] Full `ruff check . && pytest -q` green; push `main` to GitHub; CI green.
