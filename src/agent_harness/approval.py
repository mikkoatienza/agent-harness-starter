"""Human approval step. Nothing is released without an explicit decision."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from agent_harness.models import ChangeSet, GateResult, Spec

Decision = Literal["approved", "rejected", "pending"]


class Approver(Protocol):
    """Decides whether a gated change may be released."""

    def decide(self, spec: Spec, changes: ChangeSet, gates: list[GateResult]) -> Decision:
        """Return approved, rejected, or pending."""
        ...


class CLIApprover:
    """Show a summary and ask on the terminal."""

    def __init__(
        self, ask: Callable[[str], str] = input, show: Callable[[str], None] = print
    ) -> None:
        self.ask, self.show = ask, show

    def decide(self, spec: Spec, changes: ChangeSet, gates: list[GateResult]) -> Decision:
        self.show(f"\nTicket {spec.ticket_id}: {spec.goal}")
        self.show(f"Files: {', '.join(changes.files)} ({changes.lines_changed} lines)")
        for g in gates:
            self.show(f"  [{'PASS' if g.passed else 'FAIL'}] {g.name}")
        ans = self.ask("Approve release? [y/N] ").strip().lower()
        return "approved" if ans in ("y", "yes") else "rejected"


class FileApprover:
    """Asynchronous approval through files, for CI or chat-ops.

    Writes ``<dir>/<ticket>.request.json`` and returns ``pending`` until a reviewer
    creates ``<ticket>.approved`` or ``<ticket>.rejected`` in the same directory.
    """

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def decide(self, spec: Spec, changes: ChangeSet, gates: list[GateResult]) -> Decision:
        self.dir.mkdir(parents=True, exist_ok=True)
        base = self.dir / spec.ticket_id
        if base.with_suffix(".approved").exists():
            return "approved"
        if base.with_suffix(".rejected").exists():
            return "rejected"
        base.with_suffix(".request.json").write_text(
            json.dumps(
                {
                    "ticket": spec.ticket_id,
                    "goal": spec.goal,
                    "files": changes.files,
                    "lines_changed": changes.lines_changed,
                    "gates": [g.__dict__ for g in gates],
                },
                indent=2,
            )
        )
        return "pending"


class StaticApprover:
    """Always returns the same decision. Intended for tests and dry runs only."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision

    def decide(self, spec: Spec, changes: ChangeSet, gates: list[GateResult]) -> Decision:
        return self.decision
