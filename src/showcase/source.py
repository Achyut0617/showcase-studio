"""Turn a project source (GitHub URL, SSH remote or local folder) into a project name."""

import re


def project_name_from_source(source: str) -> str:
    """Return a lowercase slug ``[a-z0-9-]`` naming the project at ``source``.

    Accepts https URLs, ``git@host:user/repo.git`` remotes and local paths
    (POSIX or Windows). Raises ``ValueError`` when no usable name remains.
    """
    text = re.split(r"[?#]", source.strip(), maxsplit=1)[0]  # drop ?query and #fragment
    parts = [p for p in re.split(r"[/\\:]", text) if p]
    if not parts:
        raise ValueError(f"cannot name a project from source {source!r}")
    last = parts[-1]
    if last.lower().endswith(".git"):
        last = last[:-4]
    slug = re.sub(r"[^a-z0-9]+", "-", last.lower()).strip("-")
    if not slug:
        raise ValueError(f"cannot name a project from source {source!r}")
    return slug
