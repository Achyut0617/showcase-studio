"""The tutorial page (T1.6): get it running, then read the code in the order it runs.

Built from the same analysis as the other docs. The reading order follows the
project's own imports outward from its entry points, so a newcomer meets each
file after the file that uses it. Nothing is guessed: steps come from manifests,
explanations from docstrings or the LLM brief, and gaps are visible TODOs.
"""

from __future__ import annotations

from collections import deque

_TEST_HINTS = ("test", "tests", "spec", "__tests__", "conftest")


def is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    name = parts[-1]
    return (any(p in _TEST_HINTS for p in parts[:-1])
            or name.startswith("test_") or name.startswith("conftest")
            or ".test." in name or ".spec." in name or name.endswith("_test.py"))


def reading_order(code_map: dict, limit: int = 12) -> list[str]:
    """Modules in the order a reader should meet them: entry points, then what they import.

    Breadth-first over ``depends_on`` from each entry point; test files are left
    out. If there are no entry points, start from the most-used modules instead.
    """
    modules = code_map.get("modules", {})
    summary = code_map.get("summary", {})
    starts = [e["path"] for e in summary.get("entry_points", []) if e["path"] in modules]
    if not starts:
        starts = [h["path"] for h in summary.get("hubs", []) if h["path"] in modules]
    order: list[str] = []
    seen: set[str] = set()
    queue = deque(p for p in starts if not is_test_path(p))
    while queue and len(order) < limit:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        order.append(path)
        for dep in modules.get(path, {}).get("depends_on", []):
            if dep not in seen and not is_test_path(dep):
                queue.append(dep)
    return order
