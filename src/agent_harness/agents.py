"""Agent runners: anything that edits a workdir to satisfy a spec."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Protocol

from agent_harness.llm import LLM
from agent_harness.models import AgentResult, Spec


class Agent(Protocol):
    """Edits files in ``workdir`` to satisfy ``spec``."""

    def run(self, spec: Spec, workdir: Path) -> AgentResult:
        """Perform one attempt."""
        ...


class ShellAgent:
    """Run any CLI agent or script as a subprocess.

    The spec is written to ``<workdir>/.harness/spec.md`` and its path is exported
    as ``HARNESS_SPEC``. ``{spec}`` in the command is replaced with that path.
    """

    def __init__(self, command: str, timeout: int = 900) -> None:
        self.command = command
        self.timeout = timeout

    def run(self, spec: Spec, workdir: Path) -> AgentResult:
        spec_path = workdir / ".harness" / "spec.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec.to_markdown())
        cmd = shlex.split(self.command.replace("{spec}", str(spec_path)))
        env = {**os.environ, "HARNESS_SPEC": str(spec_path)}
        try:
            p = subprocess.run(
                cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            return AgentResult(False, f"timed out after {self.timeout}s")
        tokens = 0
        m = re.search(r"HARNESS_TOKENS=(\d+)", p.stdout)
        if m:
            tokens = int(m.group(1))
        return AgentResult(p.returncode == 0, f"exit {p.returncode}", tokens, p.stdout + p.stderr)


FILE_BLOCK = re.compile(r"^=== FILE: (?P<path>[^\n]+) ===\n(?P<body>.*?)^=== END ===", re.M | re.S)


class LLMAgent:
    """Single-shot LLM agent that returns whole files.

    The model sees the spec plus the listed context files and must answer with
    ``=== FILE: path ===`` ... ``=== END ===`` blocks. Paths outside ``workdir``
    are refused. Good for small tasks; use a ShellAgent for a full coding agent.
    """

    SYSTEM = (
        "You are a careful software engineer. Return complete file contents only in "
        "blocks of the form:\n=== FILE: relative/path ===\n<content>\n=== END ==="
    )

    def __init__(self, llm: LLM, context_files: list[str] | None = None) -> None:
        self.llm = llm
        self.context_files = context_files or []

    def run(self, spec: Spec, workdir: Path) -> AgentResult:
        ctx = []
        for rel in self.context_files:
            p = workdir / rel
            if p.exists():
                ctx.append(f"=== FILE: {rel} ===\n{p.read_text()}=== END ===")
        prompt = spec.to_markdown() + "\n\n## Current files\n" + "\n".join(ctx)
        out = self.llm.complete(prompt, system=self.SYSTEM, max_tokens=4096)
        root = workdir.resolve()
        written = []
        for m in FILE_BLOCK.finditer(out.text):
            target = (workdir / m.group("path").strip()).resolve()
            if not target.is_relative_to(root):
                return AgentResult(False, f"refused path outside workdir: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(m.group("body"))
            written.append(m.group("path").strip())
        tokens = out.input_tokens + out.output_tokens
        return AgentResult(bool(written), f"wrote {len(written)} file(s)", tokens, out.text)
