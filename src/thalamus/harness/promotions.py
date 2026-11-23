"""The promotion ledger — the operator moving an autonomous thread into their queue.

An autonomous run's threads are listed apart from the operator's queue
(`reader.recall_open_threads(autonomous=True)`) until the operator promotes one. The
promotion is a row here, written before the graph is touched, for the reason the close
ledger gives (harness/closes.py): a graph change whose row is missing cannot be
corroborated afterwards, while a row whose graph write failed is a visible, repairable
gap. It carries the same attribution and the same limit — it names the surface and the
kind of evidence that the operator approved, and it cannot authenticate the operator.

**Promotion moves a thread; it does not vouch for it.** The thread keeps its tier and
its autonomous marker, so a promoted thread still renders as an unattended run's record
and still informs rather than instructs. Promotion changes where it is listed and
nothing else.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from thalamus.harness.ledger_io import locked_ledger, write_row

PROMOTIONS_DIR = Path.home() / ".thalamus" / "promotions"
LEDGER_FILE = PROMOTIONS_DIR / "promotions.jsonl"

PROMOTED = "promoted"

# Where the operator gave the promotion, as for closes (closes.SURFACES).
SURFACES = ("cli", "console", "session")

DEFAULT_EVIDENCE = {
    "cli": "cli:tty",
    "console": "console:unattributed",
    "session": "session:unattributed",
}


def read_rows(path: Path | None = None) -> list[dict]:
    """Every promotion row in write order, malformed lines skipped."""
    ledger = path or LEDGER_FILE
    if not ledger.is_file():
        return []
    rows: list[dict] = []
    with ledger.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("event") == PROMOTED:
                rows.append(record)
    return rows


def promote(
    thread_id: str,
    scope: str,
    surface: str,
    approver_evidence: str = "",
    notes: str = "",
    path: Path | None = None,
) -> tuple[dict, bool]:
    """Record the operator's promotion of one thread, once.

    Returns `(row, created)`. A thread already promoted returns its existing row with
    `created` False and writes nothing; the caller still writes the graph, which is how
    a failed graph write is repaired.
    """
    if surface not in SURFACES:
        raise ValueError(f"unknown promotion surface `{surface}` — one of {SURFACES}")
    with locked_ledger(path or LEDGER_FILE) as handle:
        for existing in read_rows(path):
            if existing.get("thread_id") == thread_id and existing.get("scope") == scope:
                return existing, False
        row = {
            "event": PROMOTED,
            "ref": f"pr-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "thread_id": thread_id,
            "scope": scope,
            "surface": surface,
            "approver_evidence": approver_evidence or DEFAULT_EVIDENCE[surface],
            "notes": notes,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        write_row(handle, row)
    return row, True
