"""Quality gates. Each gate inspects the change set and workdir and passes or fails."""

from __future__ import annotations

import fnmatch
import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agent_harness.models import ChangeSet, GateResult, Spec


@dataclass
class GateContext:
    """Everything a gate may look at."""

    spec: Spec
    changes: ChangeSet
    workdir: Path


class Gate(Protocol):
    """A single quality check."""

    name: str

    def check(self, ctx: GateContext) -> GateResult:
        """Evaluate the gate."""
        ...


class CommandGate:
    """Pass when a shell command exits 0 in the workdir (tests, lint, type-check, build)."""

    def __init__(self, name: str, command: str, timeout: int = 600, blocking: bool = True) -> None:
        self.name, self.command, self.timeout, self.blocking = name, command, timeout, blocking

    def check(self, ctx: GateContext) -> GateResult:
        try:
            p = subprocess.run(
                shlex.split(self.command),
                cwd=ctx.workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return GateResult(self.name, False, str(e), self.blocking)
        tail = (p.stdout + p.stderr).strip().splitlines()[-5:]
        return GateResult(self.name, p.returncode == 0, "\n".join(tail), self.blocking)


DEFAULT_SECRET_PATTERNS = {
    "private-key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "aws-access-key": r"\bAKIA[0-9A-Z]{16}\b",
    "github-token": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    "openai-key": r"\bsk-[A-Za-z0-9_-]{20,}\b",
    "slack-token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b",
    "generic-assignment": r"(?i)\b(password|secret|api_key|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
}


class SecretScanGate:
    """Fail when added or modified files contain likely credentials."""

    name = "secret-scan"

    def __init__(self, patterns: dict[str, str] | None = None, allow: list[str] | None = None):
        self.patterns = {k: re.compile(v) for k, v in (patterns or DEFAULT_SECRET_PATTERNS).items()}
        self.allow = allow or []

    def check(self, ctx: GateContext) -> GateResult:
        hits = []
        for path, text in ctx.changes.contents.items():
            if any(fnmatch.fnmatch(path, a) for a in self.allow):
                continue
            for kind, rx in self.patterns.items():
                if rx.search(text):
                    hits.append(f"{path}: {kind}")
        return GateResult(self.name, not hits, "; ".join(hits) or "no secrets found")


class DiffScopeGate:
    """Restrict which paths may change. ``deny`` wins over ``allow``."""

    name = "diff-scope"

    def __init__(self, allow: list[str] | None = None, deny: list[str] | None = None) -> None:
        self.allow = allow or ["*"]
        self.deny = deny or []

    def check(self, ctx: GateContext) -> GateResult:
        bad = [
            f
            for f in ctx.changes.files
            if any(fnmatch.fnmatch(f, d) for d in self.deny)
            or not any(fnmatch.fnmatch(f, a) for a in self.allow)
        ]
        return GateResult(self.name, not bad, f"out of scope: {bad}" if bad else "in scope")


class SizeGate:
    """Cap the number of files and changed lines, so reviews stay reviewable."""

    name = "size"

    def __init__(self, max_files: int = 20, max_lines: int = 500) -> None:
        self.max_files, self.max_lines = max_files, max_lines

    def check(self, ctx: GateContext) -> GateResult:
        n, lines = len(ctx.changes.files), ctx.changes.lines_changed
        ok = 0 < n <= self.max_files and lines <= self.max_lines
        detail = f"{n} files, {lines} lines (limits {self.max_files}/{self.max_lines})"
        return GateResult(self.name, ok, detail if n else "no changes")


GateFactory = Callable[[dict[str, Any]], Gate]

REGISTRY: dict[str, GateFactory] = {
    "command": lambda c: CommandGate(
        c.get("name", "command"),
        c["run"],
        int(c.get("timeout", 600)),
        bool(c.get("blocking", True)),
    ),
    "secrets": lambda c: SecretScanGate(c.get("patterns"), c.get("allow")),
    "scope": lambda c: DiffScopeGate(c.get("allow"), c.get("deny")),
    "size": lambda c: SizeGate(int(c.get("max_files", 20)), int(c.get("max_lines", 500))),
}


def register_gate(kind: str, factory: GateFactory) -> None:
    """Make a custom gate type available to config files."""
    REGISTRY[kind] = factory


def build_gates(config: list[dict[str, Any]]) -> list[Gate]:
    """Instantiate gates from config entries like ``{type: command, name: tests, run: pytest}``."""
    gates = []
    for entry in config:
        kind = entry.get("type")
        if kind not in REGISTRY:
            raise ValueError(f"unknown gate type: {kind!r}")
        gates.append(REGISTRY[kind](entry))
    return gates
