"""Ticket intake from Markdown, JSON or GitHub issues."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from agent_harness.models import Ticket

_ACCEPT_HEADING = re.compile(r"^#{1,6}\s*(acceptance( criteria)?|done when)\s*$", re.I)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(?:\[[ xX]\]\s*)?(.+?)\s*$")


class IntakeError(ValueError):
    """Raised when a ticket cannot be parsed."""


def parse_markdown(text: str, ticket_id: str = "") -> Ticket:
    """Parse a Markdown ticket.

    Supports optional YAML front matter (``id``, ``title``, ``labels``), a ``# Title``
    heading, and an ``## Acceptance criteria`` section of bullet or checkbox items.
    """
    meta: dict[str, Any] = {}
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    title = str(meta.get("title", ""))
    body_lines: list[str] = []
    acceptance: list[str] = []
    in_accept = False
    for line in text.splitlines():
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        if line.lstrip().startswith("#"):
            in_accept = bool(_ACCEPT_HEADING.match(line.strip()))
            if in_accept:
                continue
        m = _BULLET.match(line)
        if in_accept and m:
            acceptance.append(m.group(1))
        elif not in_accept:
            body_lines.append(line)
    if not title:
        raise IntakeError("ticket has no title")
    return Ticket(
        id=str(meta.get("id") or ticket_id or _slug(title)),
        title=title,
        body="\n".join(body_lines).strip(),
        acceptance=acceptance,
        labels=[str(x) for x in meta.get("labels", [])],
        source="markdown",
    )


def parse_json(data: dict[str, Any]) -> Ticket:
    """Build a ticket from a JSON object with ``id``, ``title``, ``body``, ``acceptance``."""
    try:
        return Ticket(
            id=str(data["id"]),
            title=str(data["title"]),
            body=str(data.get("body", "")),
            acceptance=[str(a) for a in data.get("acceptance", [])],
            labels=[str(x) for x in data.get("labels", [])],
            source="json",
        )
    except KeyError as e:
        raise IntakeError(f"missing field {e}") from e


def from_github_issue(repo: str, number: int, token: str | None = None) -> Ticket:
    """Fetch a GitHub issue and parse its body as a Markdown ticket.

    Uses ``GITHUB_TOKEN`` from the environment when ``token`` is not given.
    """
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{number}",
        headers={"Accept": "application/vnd.github+json"},
    )
    tok = token or os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        issue = json.load(r)
    return issue_to_ticket(repo, issue)


def issue_to_ticket(repo: str, issue: dict[str, Any]) -> Ticket:
    """Convert a GitHub issue API object into a ticket."""
    md = f"# {issue['title']}\n\n{issue.get('body') or ''}"
    t = parse_markdown(md, ticket_id=f"{repo.replace('/', '-')}-{issue['number']}")
    t.labels = [lb["name"] for lb in issue.get("labels", []) if isinstance(lb, dict)]
    t.source = "github"
    return t


def load_ticket(ref: str) -> Ticket:
    """Load a ticket from a path (``.md``/``.json``) or ``gh:owner/repo#123``."""
    m = re.fullmatch(r"gh:([\w.-]+/[\w.-]+)#(\d+)", ref)
    if m:
        return from_github_issue(m.group(1), int(m.group(2)))
    p = Path(ref)
    if not p.exists():
        raise IntakeError(f"no such ticket: {ref}")
    if p.suffix == ".json":
        return parse_json(json.loads(p.read_text()))
    return parse_markdown(p.read_text(), ticket_id=p.stem)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]
