# Project Showcase Studio

A hybrid multi-agent system that turns any codebase into a full technical showcase:
a deep explanation, documentation, a step-by-step tutorial, and a narrated demo video
in the author's own (cloned) voice — published only after the author approves it.

> **Status:** Stage 1 — Understand + Write, in progress. The orchestrator, job folder,
> resumable pipeline, approval gate and Docker sandbox are in place. The `analyze` stage
> fetches the project and writes `ingest.json` (file tree, languages, manifests, sensitive
> files) and `code_map.json` (symbols, dependency graph, Python call graph, entry points,
> hub modules). With an LLM configured it also writes `brief.json` / `brief.md`; until the
> provider is chosen (decision D-001) that step is skipped. Every other agent is still a stub.

## How it works

A fixed backbone (the **Orchestrator**) runs eleven stages in order. Each stage is an
agent that reasons and retries inside its own job, and agents talk only through files
in a per-job folder, so any stage can be re-run on its own.

```
analyze → research_style → write_docs → run → plan_demo → record
        → write_script → voice → edit_video → review → publish (needs approval)
```

```
jobs/<project>-<YYYYMMDD-HHMMSS>/
  job.json  input/  clips/  narration/  video/  docs/  publish/  logs/
```

## Quick start

```bash
pip install -e .[dev]

showcase run https://github.com/Achyut0617/NearbyConnect   # walks all stages, stops before publish
showcase status jobs/nearbyconnect-<timestamp>
showcase approve jobs/nearbyconnect-<timestamp>
showcase resume jobs/nearbyconnect-<timestamp>              # finishes publish
```

Build the sandbox image (untrusted projects only ever run inside it):

```bash
docker build -t showcase-sandbox:base sandbox/
```

## Commit convention

Commit messages start with the tracker ID so progress updates itself every night:

| Message | Meaning |
| --- | --- |
| `T1.3: add call-graph builder (2h)` | worked on task T1.3, 2 hours |
| `T1.3 done` | task T1.3 finished |
| `E-001: Docker build fails on WSL` | an error occurred (full write-up in the Error & Decision Log) |
| `D-002: chose open-source voice model` | a design decision was made |

## Project documents

- Design: [`docs/superpowers/specs/`](docs/superpowers/specs/) (living version linked inside)
- Current plan: [`docs/superpowers/plans/`](docs/superpowers/plans/)
- Voice sample guide: [`docs/voice-recording-guide.md`](docs/voice-recording-guide.md)

## Roadmap

| Stage | Dates | Result |
| --- | --- | --- |
| S0 Foundations | 30 Nov – 6 Dec 2026 | Skeleton, sandbox, voice samples |
| S1 Understand + Write | 7 – 27 Dec 2026 | README, architecture page, tutorial for any repo |
| S2 Run + Record | 28 Dec 2026 – 24 Jan 2027 | Automatic demo recording |
| S3 Narrate + Edit | 25 Jan – 21 Feb 2027 | Narrated walkthrough in the author's voice |
| S4 Style + Publish | 22 Feb – 14 Mar 2027 | One-click approve and publish |
| S5 Harden + Buffer | 15 – 28 Mar 2027 | Stable v1 |
