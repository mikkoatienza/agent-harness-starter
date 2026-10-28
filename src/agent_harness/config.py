"""YAML configuration for the harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Budget:
    """Limits across all attempts for a ticket."""

    max_attempts: int = 3
    max_tokens: int = 200_000
    max_seconds: float = 1800.0


@dataclass
class HarnessConfig:
    """Top-level settings, usually loaded from ``harness.yaml``."""

    agent: dict[str, Any] = field(default_factory=lambda: {"type": "shell", "command": "true"})
    spec: dict[str, Any] = field(default_factory=lambda: {"type": "template"})
    gates: list[dict[str, Any]] = field(default_factory=list)
    approval: dict[str, Any] = field(default_factory=lambda: {"type": "cli"})
    budget: Budget = field(default_factory=Budget)
    ignore: list[str] = field(default_factory=list)
    audit_dir: str = ".harness/runs"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HarnessConfig:
        """Build from a parsed mapping; unknown keys raise ``ValueError``."""
        known = set(cls.__dataclass_fields__)
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        d = dict(d)
        if "budget" in d:
            d["budget"] = Budget(**d["budget"])
        return cls(**d)


def load_config(path: Path | None) -> HarnessConfig:
    """Load ``path`` or return defaults when it is ``None``."""
    if path is None:
        return HarnessConfig()
    return HarnessConfig.from_dict(yaml.safe_load(path.read_text()) or {})


SAMPLE_CONFIG = """\
# agent-harness configuration
agent:
  type: shell                 # shell | llm
  command: "my-agent --spec {spec}"
  # type: llm
  # provider: anthropic       # offline | openai | anthropic (or LLM_PROVIDER env var)
  # context_files: [src/app.py]
spec:
  type: template              # template | llm
  constraints:
    - Do not change public APIs unless the ticket asks for it
gates:
  - {type: size, max_files: 15, max_lines: 400}
  - {type: scope, allow: ["src/*", "tests/*", "docs/*"], deny: [".github/*"]}
  - {type: secrets}
  - {type: command, name: lint, run: "ruff check ."}
  - {type: command, name: tests, run: "pytest -q"}
approval:
  type: cli                   # cli | file | auto-reject
  # directory: .harness/approvals
budget:
  max_attempts: 3
  max_tokens: 200000
  max_seconds: 1800
audit_dir: .harness/runs
"""
