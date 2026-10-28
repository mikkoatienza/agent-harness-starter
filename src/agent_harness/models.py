"""Core data types passed between harness stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ticket:
    """A unit of work, as it arrives at intake."""

    id: str
    title: str
    body: str = ""
    acceptance: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Spec:
    """An explicit, reviewable description of what the agent must do."""

    ticket_id: str
    goal: str
    context: str
    acceptance: list[str]
    constraints: list[str] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the spec as Markdown, the format handed to agents."""
        parts = [f"# {self.goal}", "", f"Ticket: {self.ticket_id}", ""]
        if self.context:
            parts += ["## Context", self.context, ""]
        parts += ["## Acceptance criteria", *[f"- {a}" for a in self.acceptance], ""]
        if self.constraints:
            parts += ["## Constraints", *[f"- {c}" for c in self.constraints], ""]
        if self.feedback:
            parts += ["## Feedback from previous attempt", *[f"- {f}" for f in self.feedback], ""]
        return "\n".join(parts)


@dataclass
class ChangeSet:
    """Files the agent touched, measured by comparing workdir snapshots."""

    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    lines_changed: int = 0
    contents: dict[str, str] = field(default_factory=dict)

    @property
    def files(self) -> list[str]:
        """All touched paths, sorted."""
        return sorted({*self.added, *self.modified, *self.deleted})


@dataclass
class AgentResult:
    """What an agent reports after one attempt."""

    ok: bool
    summary: str = ""
    tokens: int = 0
    log: str = ""


@dataclass
class GateResult:
    """Outcome of one quality gate."""

    name: str
    passed: bool
    detail: str = ""
    blocking: bool = True


@dataclass
class RunResult:
    """Final outcome of a harness run."""

    ticket_id: str
    status: str  # released | awaiting-approval | rejected | blocked | budget-exceeded | invalid
    attempts: int = 0
    tokens: int = 0
    seconds: float = 0.0
    gates: list[GateResult] = field(default_factory=list)
    changes: ChangeSet = field(default_factory=ChangeSet)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "attempts": self.attempts,
            "tokens": self.tokens,
            "seconds": round(self.seconds, 3),
            "files": self.changes.files,
            "lines_changed": self.changes.lines_changed,
            "gates": [g.__dict__ for g in self.gates],
            "notes": self.notes,
        }
