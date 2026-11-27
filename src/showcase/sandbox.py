"""Build the locked-down `docker run` command that untrusted projects run inside."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxLimits:
    cpus: float = 2.0
    memory: str = "4g"
    pids: int = 256
    network: bool = False
    read_only: bool = True  # root filesystem; /tmp stays writable as a tmpfs


def docker_run_args(
    image: str,
    input_dir: Path,
    command: list[str],
    limits: SandboxLimits = SandboxLimits(),  # noqa: B008 - frozen dataclass, safe default
) -> list[str]:
    """Return the argument list (never a shell string) for one sandboxed run.

    Only the job's input folder is mounted, at /work. Network is off unless
    ``limits.network`` is True. The container runs as the non-root ``runner``
    user with every capability dropped, on a read-only root filesystem
    unless ``limits.read_only`` is False.
    """
    args = ["docker", "run", "--rm"]
    if not limits.network:
        args += ["--network", "none"]
    if limits.read_only:
        args += ["--read-only", "--tmpfs", "/tmp:rw,size=512m"]
    args += [
        "--memory", limits.memory,
        "--cpus", str(limits.cpus),
        "--pids-limit", str(limits.pids),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "runner",
        "-v", f"{Path(input_dir).resolve()}:/work",
        "-w", "/work",
        image,
        *command,
    ]
    return args
