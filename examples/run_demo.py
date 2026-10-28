"""End-to-end demo: copy the demo project, run the harness, approve via file, run again.

python examples/run_demo.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agent_harness.config import load_config
from agent_harness.intake import load_ticket
from agent_harness.report import to_markdown
from agent_harness.runner import Harness

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "demo_project"
        shutil.copytree(HERE / "demo_project", work)
        shutil.copytree(HERE / "agents", Path(tmp) / "agents")
        cfg = load_config(HERE / "harness.yaml")
        ticket = load_ticket(str(HERE / "tickets" / "fix-greeting.md"))

        first = Harness.from_config(cfg, work).run(ticket, work)
        print(to_markdown(first))  # awaiting-approval after a retry

        (work / ".harness/approvals/DEMO-1.approved").touch()  # a reviewer signs off
        shutil.copy(HERE / "demo_project/src/greet.py", work / "src/greet.py")
        second = Harness.from_config(cfg, work).run(ticket, work)
        print(to_markdown(second))  # released


if __name__ == "__main__":
    main()
