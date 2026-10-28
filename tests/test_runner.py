from pathlib import Path

import pytest

from agent_harness.agents import LLMAgent, ShellAgent
from agent_harness.approval import CLIApprover, FileApprover, StaticApprover
from agent_harness.audit import read_log
from agent_harness.config import Budget, HarnessConfig, load_config
from agent_harness.gates import CommandGate, SizeGate
from agent_harness.intake import load_ticket
from agent_harness.llm import OfflineLLM
from agent_harness.models import AgentResult, Spec, Ticket
from agent_harness.report import to_markdown
from agent_harness.runner import Harness
from agent_harness.spec import LLMSpecWriter, SpecError, TemplateSpecWriter

EX = Path(__file__).resolve().parents[1] / "examples"
TESTS = CommandGate("tests", "python -m pytest -q -p no:cacheprovider tests")
TICKET = Ticket("DEMO-1", "Fix greeting", acceptance=["greet('Ada') == 'Hello, Ada!'"])
AGENT = ShellAgent("python ../agents/fix_greeting_agent.py")


def test_retry_with_feedback_then_release(demo: Path) -> None:
    h = Harness(AGENT, [SizeGate(), TESTS], StaticApprover("approved"), audit_dir=demo / "runs")
    r = h.run(TICKET, demo)
    assert r.status == "released"
    assert r.attempts == 2  # first attempt fails tests, feedback fixes it
    assert r.changes.files == ["src/greet.py"]
    log = read_log(next((demo / "runs").glob("*.jsonl")))
    assert [e["event"] for e in log].count("attempt") == 2
    assert log[-1]["event"] == "finished"


def test_blocked_after_max_attempts(demo: Path) -> None:
    h = Harness(
        ShellAgent("python -c 'pass'"),
        [TESTS],
        StaticApprover("approved"),
        budget=Budget(max_attempts=2),
    )
    r = h.run(TICKET, demo)
    assert r.status == "blocked" and r.attempts == 2


def test_token_budget(demo: Path) -> None:
    agent = ShellAgent("python -c \"print('HARNESS_TOKENS=999')\"")
    h = Harness(agent, [TESTS], StaticApprover("approved"), budget=Budget(max_tokens=500))
    r = h.run(TICKET, demo)
    assert r.status == "budget-exceeded" and r.tokens == 999


def test_spec_rejected_without_criteria(demo: Path) -> None:
    r = Harness(AGENT, [], StaticApprover("approved")).run(Ticket("X", "vague"), demo)
    assert r.status == "invalid"


def test_file_approval_flow(demo: Path) -> None:
    appr = demo / "appr"
    h = Harness(AGENT, [TESTS], FileApprover(appr))
    assert h.run(TICKET, demo).status == "awaiting-approval"
    assert (appr / "DEMO-1.request.json").exists()
    (appr / "DEMO-1.rejected").touch()
    assert h.run(TICKET, demo).status == "rejected"


def test_cli_approver() -> None:
    from agent_harness.models import ChangeSet

    out: list[str] = []
    a = CLIApprover(ask=lambda _: "y", show=out.append)
    assert a.decide(Spec("T", "g", "", ["a"]), ChangeSet(modified=["f"]), []) == "approved"
    assert (
        CLIApprover(ask=lambda _: "", show=out.append).decide(
            Spec("T", "g", "", ["a"]), ChangeSet(), []
        )
        == "rejected"
    )


def test_llm_agent_offline(tmp_path: Path) -> None:
    reply = "=== FILE: src/x.py ===\nX = 1\n=== END ==="
    agent = LLMAgent(OfflineLLM(lambda p: reply))
    res = agent.run(Spec("T", "g", "", ["a"]), tmp_path)
    assert res.ok and (tmp_path / "src/x.py").read_text() == "X = 1\n"


def test_llm_agent_refuses_escape(tmp_path: Path) -> None:
    reply = "=== FILE: ../evil.py ===\nboom\n=== END ==="
    res = LLMAgent(OfflineLLM(lambda p: reply)).run(Spec("T", "g", "", ["a"]), tmp_path)
    assert not res.ok and not (tmp_path.parent / "evil.py").exists()


def test_llm_spec_writer() -> None:
    w = LLMSpecWriter(OfflineLLM(lambda p: "- returns 200\n- logs request"))
    assert w.write(Ticket("T", "Add health check")).acceptance == ["returns 200", "logs request"]
    with pytest.raises(SpecError):
        LLMSpecWriter(OfflineLLM(lambda p: "no bullets")).write(Ticket("T", "x"))
    with pytest.raises(SpecError):
        TemplateSpecWriter().write(Ticket("T", "x"))


def test_from_config_matches_example(demo: Path) -> None:
    cfg = load_config(EX / "harness.yaml")
    ticket = load_ticket(str(EX / "tickets/fix-greeting.md"))
    r = Harness.from_config(cfg, demo).run(ticket, demo)
    assert r.status == "awaiting-approval"
    md = to_markdown(r)
    assert "DEMO-1" in md and "| tests | pass |" in md


def test_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError):
        HarnessConfig.from_dict({"agnet": {}})


def test_agent_result_failure_feeds_back(demo: Path) -> None:
    calls: list[Spec] = []

    class Flaky:
        def run(self, spec: Spec, workdir: Path) -> AgentResult:
            calls.append(spec)
            return AgentResult(False, "crashed")

    Harness(Flaky(), [], StaticApprover("approved"), budget=Budget(max_attempts=2)).run(
        TICKET, demo
    )
    assert calls[-1].feedback == ["agent: crashed"]
