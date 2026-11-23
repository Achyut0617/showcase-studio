# Project Showcase Studio — Design (summary)

Full, living version: https://claude.ai/artifact/AvhUb4ro13CApWCjoMBBnX
Approved by Achyut on 2026-11-23. This file is the in-repo copy builders plan from.

## Intent
A hybrid multi-agent system that turns any project into a technical showcase:
deep explanation, docs, tutorial, and a narrated demo video in Achyut's cloned
voice, published after his approval. Audience: engineers. Version 1 is a
personal tool (his machine, his keys, his voice).

## Approach (chosen: C, hybrid)
A fixed backbone (the Orchestrator) runs stages in a fixed order; each stage is
an agent that can reason and retry inside its own job. Agents communicate only
through files in a per-job folder.

## Components
1. Orchestrator — runs stages in order, retries, resumes, logs cost, owns the job folder
2. Analyzer — brief.json / brief.md
3. Runner — runs the project in Docker or flags `simulated`
4. Demo planner — demo_script.json
5. Recorder — browser / terminal / code clips
6. Trend researcher — style_guide.md
7. Script writer — narration per chapter, length by content
8. Voice agent — narration audio in Achyut's cloned voice
9. Video editor — walkthrough + 60 s highlight clip
10. Docs & tutorial agent — README, SETUP, ARCHITECTURE, TUTORIAL
11. Review screen + Publisher — nothing publishes without approval

## Job folder
```
jobs/<project-name>-<date>/
  job.json  input/  brief.json  brief.md  run_report.json  demo_script.json
  style_guide.md  clips/  narration/  video/  docs/  publish/  logs/
```
- `publish/approval.json` must exist before the Publisher runs.
- `simulated: true` in run_report.json travels forward and is labelled on screen.

## Constraints
- ~12 h/week; student budget; CPU rendering; untrusted code only in Docker
  (no host mounts beyond the job input, network off by default, CPU/RAM limits, non-root).
- Voice clone trained only on Achyut's own recordings, private.
- Python for orchestrator and agents.

## Anti-goals
Nothing public without review; no copied text from other projects; predicted
output never shown as real; wrong claims about the code.

## Stages
S0 Foundations (30 Nov – 6 Dec 2026) · S1 Understand + Write · S2 Run + Record ·
S3 Narrate + Edit · S4 Style + Publish · S5 Harden + Buffer (to 28 Mar 2027).
