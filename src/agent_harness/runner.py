"""The harness loop: spec -> attempt -> gates -> (retry) -> approval -> release."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent_harness.agents import Agent, LLMAgent, ShellAgent
from agent_harness.approval import Approver, CLIApprover, FileApprover, StaticApprover
from agent_harness.audit import AuditLog
from agent_harness.config import Budget, HarnessConfig
from agent_harness.gates import Gate, GateContext, build_gates
from agent_harness.llm import get_llm
from agent_harness.models import RunResult, Ticket
from agent_harness.spec import LLMSpecWriter, SpecError, SpecWriter, TemplateSpecWriter
from agent_harness.workspace import diff, snapshot


@dataclass
class Harness:
    """Wires the pluggable parts together. Build directly or via :meth:`from_config`."""

    agent: Agent
    gates: list[Gate]
    approver: Approver
    spec_writer: SpecWriter = field(default_factory=TemplateSpecWriter)
    budget: Budget = field(default_factory=Budget)
    ignore: list[str] = field(default_factory=list)
    audit_dir: Path | None = None

    @classmethod
    def from_config(cls, cfg: HarnessConfig, workdir: Path) -> Harness:
        """Instantiate every component from a :class:`HarnessConfig`."""
        a = cfg.agent
        agent: Agent
        if a.get("type") == "llm":
            agent = LLMAgent(get_llm(a.get("provider")), a.get("context_files"))
        else:
            agent = ShellAgent(a["command"], int(a.get("timeout", 900)))
        s = cfg.spec
        constraints = s.get("constraints", [])
        writer: SpecWriter = (
            LLMSpecWriter(get_llm(s.get("provider")), constraints)
            if s.get("type") == "llm"
            else TemplateSpecWriter(constraints)
        )
        ap = cfg.approval
        approver: Approver
        if ap.get("type") == "file":
            approver = FileApprover(workdir / ap.get("directory", ".harness/approvals"))
        elif ap.get("type") == "auto-reject":
            approver = StaticApprover("rejected")
        else:
            approver = CLIApprover()
        return cls(
            agent,
            build_gates(cfg.gates),
            approver,
            writer,
            cfg.budget,
            cfg.ignore,
            workdir / cfg.audit_dir,
        )

    def run(self, ticket: Ticket, workdir: Path) -> RunResult:
        """Run one ticket. Returns a :class:`RunResult`; never raises for agent failures."""
        run_id = f"{ticket.id}-{uuid.uuid4().hex[:8]}"
        log = AuditLog(self.audit_dir / f"{run_id}.jsonl" if self.audit_dir else None, run_id)
        res = RunResult(ticket.id, "invalid")
        start = time.monotonic()
        log.emit("intake", ticket=ticket.__dict__)
        try:
            spec = self.spec_writer.write(ticket)
        except SpecError as e:
            res.notes.append(str(e))
            log.emit("spec_rejected", reason=str(e))
            return self._finish(res, log, start)
        log.emit("spec", spec=spec.__dict__)

        ignore = list(self.ignore)
        if self.audit_dir and self.audit_dir.resolve().is_relative_to(workdir.resolve()):
            rel = self.audit_dir.resolve().relative_to(workdir.resolve()).as_posix()
            ignore.append(f"{rel}/*")  # never count our own audit log as an agent change
        before = snapshot(workdir, ignore)
        for attempt in range(1, self.budget.max_attempts + 1):
            res.attempts = attempt
            out = self.agent.run(spec, workdir)
            res.tokens += out.tokens
            res.changes = diff(before, snapshot(workdir, ignore))
            log.emit(
                "attempt",
                n=attempt,
                ok=out.ok,
                summary=out.summary,
                tokens=out.tokens,
                files=res.changes.files,
                lines=res.changes.lines_changed,
            )
            ctx = GateContext(spec, res.changes, workdir)
            res.gates = [g.check(ctx) for g in self.gates]
            log.emit("gates", n=attempt, results=[g.__dict__ for g in res.gates])
            failed = [g for g in res.gates if g.blocking and not g.passed]
            if out.ok and not failed:
                break
            res.status = "blocked"
            spec.feedback = [f"agent: {out.summary}"] if not out.ok else []
            spec.feedback += [f"gate {g.name} failed: {g.detail}" for g in failed]
            if res.tokens >= self.budget.max_tokens or (
                time.monotonic() - start >= self.budget.max_seconds
            ):
                res.status = "budget-exceeded"
                res.notes.append("budget exhausted")
                log.emit("budget_exceeded", tokens=res.tokens)
                return self._finish(res, log, start)
        else:
            res.notes.append(f"gates still failing after {self.budget.max_attempts} attempts")
            return self._finish(res, log, start)

        decision = self.approver.decide(spec, res.changes, res.gates)
        log.emit("approval", decision=decision)
        res.status = {
            "approved": "released",
            "rejected": "rejected",
            "pending": "awaiting-approval",
        }[decision]
        return self._finish(res, log, start)

    @staticmethod
    def _finish(res: RunResult, log: AuditLog, start: float) -> RunResult:
        res.seconds = time.monotonic() - start
        log.emit("finished", result=res.to_dict())
        return res
