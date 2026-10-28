"""Render a run result as a Markdown report."""

from __future__ import annotations

from agent_harness.models import RunResult


def to_markdown(r: RunResult) -> str:
    """Human-readable summary suitable for a PR comment or chat message."""
    icon = {"released": "✅", "awaiting-approval": "⏳"}.get(r.status, "❌")
    lines = [
        f"## {icon} {r.ticket_id}: {r.status}",
        "",
        f"- Attempts: {r.attempts}",
        f"- Tokens: {r.tokens}",
        f"- Duration: {r.seconds:.1f}s",
        f"- Files: {', '.join(r.changes.files) or 'none'} ({r.changes.lines_changed} lines)",
        "",
    ]
    if r.gates:
        lines += ["| Gate | Result | Detail |", "|---|---|---|"]
        for g in r.gates:
            res = "pass" if g.passed else ("FAIL" if g.blocking else "warn")
            detail = g.detail.replace("\n", " ").replace("|", "\\|")[:120]
            lines.append(f"| {g.name} | {res} | {detail} |")
        lines.append("")
    lines += [f"> {n}" for n in r.notes]
    return "\n".join(lines).rstrip() + "\n"
