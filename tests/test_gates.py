from pathlib import Path

import pytest

from agent_harness.gates import (
    CommandGate,
    DiffScopeGate,
    GateContext,
    SecretScanGate,
    SizeGate,
    build_gates,
    register_gate,
)
from agent_harness.models import ChangeSet, GateResult, Spec

SPEC = Spec("T", "goal", "", ["a"])


def ctx(cs: ChangeSet, wd: Path = Path(".")) -> GateContext:
    return GateContext(SPEC, cs, wd)


def test_secret_scan_detects_and_allows() -> None:
    key = "AKIA" + "ABCDEFGHIJKLMNOP"
    cs = ChangeSet(added=["a.py"], contents={"a.py": f"k = '{key}'"})
    assert not SecretScanGate().check(ctx(cs)).passed
    assert SecretScanGate(allow=["a.py"]).check(ctx(cs)).passed


def test_secret_scan_generic_assignment() -> None:
    cs = ChangeSet(added=["c.py"], contents={"c.py": 'password = "hunter2hunter2"'})
    assert "generic-assignment" in SecretScanGate().check(ctx(cs)).detail


def test_scope_allow_and_deny() -> None:
    g = DiffScopeGate(allow=["src/*"], deny=["src/secrets/*"])
    assert g.check(ctx(ChangeSet(modified=["src/a.py"]))).passed
    assert not g.check(ctx(ChangeSet(modified=["README.md"]))).passed
    assert not g.check(ctx(ChangeSet(modified=["src/secrets/x"]))).passed


def test_size_limits() -> None:
    assert SizeGate(2, 10).check(ctx(ChangeSet(modified=["a"], lines_changed=3))).passed
    assert not SizeGate(2, 10).check(ctx(ChangeSet(modified=["a"], lines_changed=30))).passed
    assert not SizeGate().check(ctx(ChangeSet())).passed  # empty change is not a change


def test_command_gate(tmp_path: Path) -> None:
    assert CommandGate("ok", "python -c 'pass'").check(ctx(ChangeSet(), tmp_path)).passed
    bad = CommandGate("bad", "python -c 'import sys; sys.exit(2)'").check(
        ctx(ChangeSet(), tmp_path)
    )
    assert not bad.passed
    missing = CommandGate("m", "definitely-not-a-binary-xyz").check(ctx(ChangeSet(), tmp_path))
    assert not missing.passed


def test_build_from_config_and_custom_gate() -> None:
    class Always:
        name = "always"

        def check(self, c: GateContext) -> GateResult:
            return GateResult(self.name, True)

    register_gate("always", lambda c: Always())
    gates = build_gates([{"type": "size"}, {"type": "always"}, {"type": "secrets"}])
    assert [g.name for g in gates] == ["size", "always", "secret-scan"]
    with pytest.raises(ValueError):
        build_gates([{"type": "nope"}])
