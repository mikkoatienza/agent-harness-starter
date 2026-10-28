import json, sys
from .pipeline import load_ticket, run, stub_agent

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m harness <ticket.json> [--approve]")
    rec = run(load_ticket(sys.argv[1]), stub_agent, reviewer=lambda s, c: "--approve" in sys.argv)
    print(json.dumps({"ticket": rec.ticket_id, "final_stage": rec.stage, "events": rec.events}, indent=2))
