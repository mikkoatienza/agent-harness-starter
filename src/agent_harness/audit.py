"""Append-only JSONL audit log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLog:
    """Writes one JSON object per event. ``path=None`` keeps events in memory only."""

    def __init__(self, path: Path | None = None, run_id: str = "") -> None:
        self.path, self.run_id = path, run_id
        self.events: list[dict[str, Any]] = []
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **data: Any) -> None:
        """Record an event with a UTC timestamp."""
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        self.events.append(rec)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")


def read_log(path: Path) -> list[dict[str, Any]]:
    """Load events from a JSONL file."""
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
