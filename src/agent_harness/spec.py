"""Spec writers: turn a ticket into an explicit spec."""

from __future__ import annotations

import re
from typing import Protocol

from agent_harness.llm import LLM
from agent_harness.models import Spec, Ticket


class SpecError(ValueError):
    """The ticket is not ready to be worked on."""


class SpecWriter(Protocol):
    """Produces a :class:`Spec` from a :class:`Ticket`."""

    def write(self, ticket: Ticket) -> Spec:
        """Return a spec or raise :class:`SpecError`."""
        ...


class TemplateSpecWriter:
    """Deterministic spec writer. Rejects tickets with no acceptance criteria."""

    def __init__(self, constraints: list[str] | None = None) -> None:
        self.constraints = constraints or []

    def write(self, ticket: Ticket) -> Spec:
        if not ticket.acceptance:
            raise SpecError(f"ticket {ticket.id} has no acceptance criteria")
        return Spec(ticket.id, ticket.title, ticket.body, list(ticket.acceptance), self.constraints)


class LLMSpecWriter:
    """Ask a model to propose acceptance criteria when the ticket has none.

    The model must answer with bullet points; anything else is ignored. If no
    criteria come back the ticket is rejected rather than guessed at.
    """

    PROMPT = (
        "Write 2-5 concrete, testable acceptance criteria for this ticket. "
        "Answer only with '- ' bullet lines.\n\nTitle: {title}\n\n{body}"
    )

    def __init__(self, llm: LLM, constraints: list[str] | None = None) -> None:
        self.llm = llm
        self.base = TemplateSpecWriter(constraints)

    def write(self, ticket: Ticket) -> Spec:
        if ticket.acceptance:
            return self.base.write(ticket)
        out = self.llm.complete(self.PROMPT.format(title=ticket.title, body=ticket.body)).text
        crit = [m.group(1).strip() for m in re.finditer(r"^\s*[-*]\s+(.+)$", out, re.M)]
        if not crit:
            raise SpecError(f"could not derive acceptance criteria for {ticket.id}")
        ticket.acceptance = crit
        return self.base.write(ticket)
