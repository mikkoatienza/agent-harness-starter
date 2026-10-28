"""Command-line interface: ``agent-harness``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_harness import __version__
from agent_harness.audit import read_log
from agent_harness.config import SAMPLE_CONFIG, load_config
from agent_harness.intake import IntakeError, load_ticket
from agent_harness.models import ChangeSet, GateResult, RunResult
from agent_harness.report import to_markdown
from agent_harness.runner import Harness

EXIT = {"released": 0, "awaiting-approval": 3}


def main(argv: list[str] | None = None) -> int:
    """Entry point. Exit codes: 0 released, 3 awaiting approval, 1 otherwise."""
    ap = argparse.ArgumentParser(prog="agent-harness", description=__doc__)
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a ticket through the harness")
    r.add_argument("ticket", help="path to .md/.json ticket or gh:owner/repo#N")
    r.add_argument("-c", "--config", type=Path, default=None)
    r.add_argument("-w", "--workdir", type=Path, default=Path.cwd())
    r.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    i = sub.add_parser("init", help="write a sample harness.yaml")
    i.add_argument("path", type=Path, nargs="?", default=Path("harness.yaml"))
    rep = sub.add_parser("report", help="render a Markdown report from a run log")
    rep.add_argument("log", type=Path)
    t = sub.add_parser("ticket", help="parse a ticket and print it as JSON")
    t.add_argument("ticket")
    a = ap.parse_args(argv)

    if a.cmd == "init":
        if a.path.exists():
            print(f"{a.path} already exists", file=sys.stderr)
            return 1
        a.path.write_text(SAMPLE_CONFIG)
        print(f"wrote {a.path}")
        return 0
    if a.cmd == "ticket":
        try:
            print(json.dumps(load_ticket(a.ticket).__dict__, indent=2))
        except IntakeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    if a.cmd == "report":
        fin = [e for e in read_log(a.log) if e["event"] == "finished"]
        if not fin:
            print("no finished event in log", file=sys.stderr)
            return 1
        d = fin[-1]["result"]
        res = RunResult(
            d["ticket_id"],
            d["status"],
            d["attempts"],
            d["tokens"],
            d["seconds"],
            [GateResult(**g) for g in d["gates"]],
            ChangeSet(modified=d["files"], lines_changed=d["lines_changed"]),
            d["notes"],
        )
        print(to_markdown(res))
        return 0

    try:
        ticket = load_ticket(a.ticket)
    except IntakeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    harness = Harness.from_config(load_config(a.config), a.workdir.resolve())
    result = harness.run(ticket, a.workdir.resolve())
    print(json.dumps(result.to_dict(), indent=2) if a.json else to_markdown(result))
    return EXIT.get(result.status, 1)


if __name__ == "__main__":
    sys.exit(main())
