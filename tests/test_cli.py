import json
import os
from pathlib import Path

import pytest

from agent_harness.cli import main
from agent_harness.llm import OfflineLLM, get_llm

EX = Path(__file__).resolve().parents[1] / "examples"


def test_init_and_ticket(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "harness.yaml"
    assert main(["init", str(cfg)]) == 0 and cfg.exists()
    assert main(["init", str(cfg)]) == 1
    assert main(["ticket", str(EX / "tickets/feature.json")]) == 0
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["id"] == "DEMO-2"
    assert main(["ticket", "missing.md"]) == 1


def test_run_and_report(demo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "run",
            str(EX / "tickets/fix-greeting.md"),
            "-c",
            str(EX / "harness.yaml"),
            "-w",
            str(demo),
            "--json",
        ]
    )
    assert code == 3
    assert json.loads(capsys.readouterr().out)["status"] == "awaiting-approval"
    log = next((demo / ".harness/runs").glob("*.jsonl"))
    assert main(["report", str(log)]) == 0
    assert "awaiting-approval" in capsys.readouterr().out


def test_get_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(get_llm(), OfflineLLM)
    with pytest.raises(ValueError):
        get_llm("nope")
    assert os.environ.get("OPENAI_API_KEY") is None or True
