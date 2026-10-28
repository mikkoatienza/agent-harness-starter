"""Snapshot a working directory and diff two snapshots into a ChangeSet."""

from __future__ import annotations

import difflib
import fnmatch
from pathlib import Path

from agent_harness.models import ChangeSet

DEFAULT_IGNORE = [".git/*", "*/__pycache__/*", "__pycache__/*", "*.pyc", ".harness/*"]

Snapshot = dict[str, str]


def snapshot(root: Path, ignore: list[str] | None = None, max_bytes: int = 1_000_000) -> Snapshot:
    """Read every text file under ``root`` (skipping ``ignore`` globs and binaries)."""
    pats = DEFAULT_IGNORE + (ignore or [])
    snap: Snapshot = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.stat().st_size > max_bytes:
            continue
        rel = p.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in pats):
            continue
        try:
            snap[rel] = p.read_text()
        except UnicodeDecodeError:
            continue
    return snap


def diff(before: Snapshot, after: Snapshot) -> ChangeSet:
    """Compare two snapshots."""
    cs = ChangeSet()
    for path in sorted(before.keys() | after.keys()):
        a, b = before.get(path), after.get(path)
        if a == b:
            continue
        if a is None:
            cs.added.append(path)
        elif b is None:
            cs.deleted.append(path)
        else:
            cs.modified.append(path)
        if b is not None:
            cs.contents[path] = b
        cs.lines_changed += sum(
            1
            for ln in difflib.unified_diff((a or "").splitlines(), (b or "").splitlines(), n=0)
            if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
        )
    return cs
