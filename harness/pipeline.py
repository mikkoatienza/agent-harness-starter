"""A tiny, dependency-free pipeline that moves a ticket through stages.

Stages: intake -> spec -> execute -> gates -> review -> release.
The "agent" is any callable that takes a spec and returns a change set,
so you can plug in an LLM client, a script, or the bundled stub.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable


@dataclass
class Ticket:
    id: str
    title: str
    body: str
    acceptance: list[str] = field(default_factory=list)


@dataclass
class Spec:
    ticket_id: str
    goal: str
    acceptance: list[str]
    out_of_scope: list[str]


@dataclass
class ChangeSet:
    files: dict[str, str]          # path -> new content
    tests_passed: bool
    notes: str = ""


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class RunRecord:
    ticket_id: str
    stage: str = "intake"
    events: list[dict] = field(default_factory=list)

    def log(self, stage: str, **data) -> None:
        self.stage = stage
        self.events.append({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": stage, **data,
        })


Agent = Callable[[Spec], ChangeSet]
Gate = Callable[[Spec, ChangeSet], GateResult]


def write_spec(ticket: Ticket) -> Spec:
    """Turn a ticket into an explicit spec. Refuses tickets with no acceptance criteria."""
    if not ticket.acceptance:
        raise ValueError(f"ticket {ticket.id} has no acceptance criteria; send back to intake")
    return Spec(ticket.id, ticket.title, list(ticket.acceptance), out_of_scope=["unrelated refactors"])


# ---- built-in gates -------------------------------------------------------

def gate_tests(spec: Spec, cs: ChangeSet) -> GateResult:
    return GateResult("tests", cs.tests_passed, "" if cs.tests_passed else "agent reported failing tests")


def gate_nonempty(spec: Spec, cs: ChangeSet) -> GateResult:
    ok = bool(cs.files)
    return GateResult("non-empty", ok, "" if ok else "no files changed")


def gate_no_secrets(spec: Spec, cs: ChangeSet) -> GateResult:
    markers = ("BEGIN PRIVATE KEY", "AKIA", "sk-", "password=")
    hits = [p for p, c in cs.files.items() if any(m in c for m in markers)]
    return GateResult("no-secrets", not hits, f"possible secret in {hits}" if hits else "")


def gate_scope(max_files: int = 10) -> Gate:
    def _g(spec: Spec, cs: ChangeSet) -> GateResult:
        ok = len(cs.files) <= max_files
        return GateResult("scope", ok, "" if ok else f"{len(cs.files)} files > {max_files}")
    return _g


DEFAULT_GATES: list[Gate] = [gate_nonempty, gate_tests, gate_no_secrets, gate_scope()]


def run(ticket: Ticket, agent: Agent, gates: list[Gate] | None = None,
        reviewer: Callable[[Spec, ChangeSet], bool] | None = None) -> RunRecord:
    """Run one ticket end to end. A human (or stand-in) reviewer must approve before release."""
    rec = RunRecord(ticket.id)
    rec.log("intake", title=ticket.title)
    try:
        spec = write_spec(ticket)
    except ValueError as e:
        rec.log("rejected", reason=str(e))
        return rec
    rec.log("spec", acceptance=spec.acceptance)

    cs = agent(spec)
    rec.log("execute", files=sorted(cs.files), notes=cs.notes)

    results = [g(spec, cs) for g in (gates or DEFAULT_GATES)]
    rec.log("gates", results=[asdict(r) for r in results])
    if not all(r.passed for r in results):
        rec.log("blocked", failed=[r.name for r in results if not r.passed])
        return rec

    approved = reviewer(spec, cs) if reviewer else False
    rec.log("review", approved=approved)
    if not approved:
        rec.log("awaiting-review")
        return rec
    rec.log("release", files=sorted(cs.files))
    return rec


def stub_agent(spec: Spec) -> ChangeSet:
    """Deterministic stand-in for an LLM agent, for demos and tests."""
    body = f"# {spec.goal}\n\n" + "\n".join(f"- [x] {a}" for a in spec.acceptance) + "\n"
    return ChangeSet({f"docs/{spec.ticket_id}.md": body}, tests_passed=True, notes="stub")


def load_ticket(path: str) -> Ticket:
    with open(path) as f:
        return Ticket(**json.load(f))
