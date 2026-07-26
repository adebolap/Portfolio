"""Append-only audit trail for compliance visibility.

Records *that* a file was processed and *what categories of thing* were
found in it - never the matched values themselves, since the whole point of
this tool is to keep that content from leaking anywhere it doesn't need to.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / ".drive_stripper" / "audit.log"


def log_event(
    log_path: Path,
    operation: str,
    source: Path,
    destination: Path | None = None,
    mode: str | None = None,
    categories: tuple[str, ...] | None = None,
    matches_by_label: dict[str, int] | None = None,
    mapping_path: Path | None = None,
) -> None:
    """Append one JSON record describing an operation. Never logs matched values."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "source": str(source),
        "destination": str(destination) if destination else None,
        "mode": mode,
        "categories": list(categories) if categories else "all",
        "matches_by_label": matches_by_label or {},
        "mapping_path": str(mapping_path) if mapping_path else None,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def read_events(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    with log_path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]
