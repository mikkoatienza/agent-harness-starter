import json
from pathlib import Path

import pytest

from agent_harness.intake import IntakeError, issue_to_ticket, load_ticket, parse_markdown

EX = Path(__file__).resolve().parents[1] / "examples" / "tickets"


def test_markdown_front_matter_and_checkboxes() -> None:
    t = load_ticket(str(EX / "fix-greeting.md"))
    assert t.id == "DEMO-1"
    assert t.labels == ["bug"]
    assert t.acceptance == ['`greet("Ada")` returns `Hello, Ada!`', "Existing tests pass"]
    assert "Acceptance" not in t.body


def test_markdown_without_criteria() -> None:
    t = load_ticket(str(EX / "vague.md"))
    assert t.id == "vague" and t.acceptance == []


def test_json() -> None:
    t = load_ticket(str(EX / "feature.json"))
    assert t.id == "DEMO-2" and len(t.acceptance) == 2


def test_json_missing_field(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"title": "no id"}))
    with pytest.raises(IntakeError):
        load_ticket(str(p))


def test_missing_title() -> None:
    with pytest.raises(IntakeError):
        parse_markdown("just text")


def test_missing_file() -> None:
    with pytest.raises(IntakeError):
        load_ticket("nope.md")


def test_github_issue_conversion() -> None:
    issue = {
        "number": 7,
        "title": "Crash on empty input",
        "body": "Steps...\n\n### Acceptance criteria\n1. No crash\n2. Clear error",
        "labels": [{"name": "bug"}],
    }
    t = issue_to_ticket("acme/app", issue)
    assert t.id == "acme-app-7"
    assert t.acceptance == ["No crash", "Clear error"]
    assert t.labels == ["bug"] and t.source == "github"
