"""Command line: showcase run | resume | status | approve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from showcase import __version__
from showcase.job import Job, JobError
from showcase.orchestrator import approve, run_job
from showcase.stages import STAGE_ORDER, default_stages


def _print_status(job: Job, final: str | None = None) -> None:
    print(f"job: {job.path}")
    for name in STAGE_ORDER:
        entry = job.stages.get(name, {})
        error = f"  ({entry['error']})" if entry.get("error") else ""
        print(f"  {name:<15} {job.status_of(name)}{error}")
    if final:
        print(f"status: {final}")
        if final == "waiting_approval":
            print(f"next: showcase approve {job.path}  then  showcase resume {job.path}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="showcase", description=__doc__)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="start a new job for a GitHub URL or local folder")
    run.add_argument("source")
    run.add_argument("--jobs-dir", default="jobs", type=Path)
    for name, help_text in (
        ("resume", "continue a job from its first unfinished stage"),
        ("status", "show each stage's status"),
        ("approve", "approve a job for publishing"),
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("job_dir", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    final = None
    try:
        if args.command == "run":
            job = Job.create(args.source, args.jobs_dir)
            final = run_job(job, default_stages())
            _print_status(job, final)
        else:
            job = Job.load(args.job_dir)
            if args.command == "resume":
                final = run_job(job, default_stages())
                _print_status(job, final)
            elif args.command == "status":
                _print_status(job)
            elif args.command == "approve":
                approve(job)
                print(f"approved: {job.path}")
    except (JobError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1 if final == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
