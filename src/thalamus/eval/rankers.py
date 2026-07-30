"""The ranker ledger: which ranking dials were in force when a trace was taken.

Retrieval-utility numbers are only comparable across a window if the ranker was the
same across it. lab/007 turned the match-floor dial, predicted a fan-out and
wasted-share effect over "the next ten synced sessions", and the prediction went
twenty-two lab entries unverified — partly because nothing recorded which traces ran
under which ranker, so by the time anyone looked the window could not be cut. A window
that straddles a dial change is not a measurement of either setting (lab/029).

**Why a ledger rather than a stamp at sync time.** `thalamus eval sync` can run days
after the retrieval it lands, on a checkout whose ranker has since changed. Reading the
fingerprint out of the currently-installed code at sync time would confidently
attribute old traces to the new ranker — the exact failure the record exists to
prevent. So the fingerprint is written when the *server that will do the ranking*
starts, and sync joins each event back to the entry in force at its timestamp.

This is the pin ledger's idiom (`harness/pin.py`, `~/.thalamus/pins/pins.jsonl`):
append-only, one line per process, ledger-first beats env-at-read-time.

Traces older than the ledger get `unknown`, never a guess — the same discipline
`injected_chars` already follows for traces synced before layer 1b existed.
"""

from __future__ import annotations

import json
import logging
import os
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RANKERS_DIR = Path.home() / ".thalamus" / "rankers"
LEDGER_NAME = "rankers.jsonl"

UNKNOWN = "unknown"


@dataclass(frozen=True)
class RankerRecord:
    ts: datetime
    fingerprint: str


def ledger_path(base: Path | None = None) -> Path:
    return (base or RANKERS_DIR) / LEDGER_NAME


def record_ranker(
    fingerprint: str, base: Path | None = None, now: datetime | None = None
) -> None:
    """Append this process's ranker fingerprint to the ledger.

    Idempotent against the common case: if the ledger's most recent entry already
    names this fingerprint, nothing is written. Every MCP server start would
    otherwise add a line, and the ledger would grow without recording anything new
    — the join only needs the points where the fingerprint *changed*.

    Never raises. A ledger that cannot be written costs an audit; an exception here
    would cost the server its startup.
    """
    stamp = now or datetime.now(timezone.utc)
    try:
        path = ledger_path(base)
        existing = _read(path)
        if existing and existing[-1].fingerprint == fingerprint:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "ts": stamp.isoformat(),
                "fingerprint": fingerprint,
                "pid": os.getpid(),
                "version": 1,
            }
        )
        with path.open("a") as handle:
            handle.write(line + "\n")
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Could not record ranker fingerprint: %s", exc)


def load_ledger(base: Path | None = None) -> list[RankerRecord]:
    """Every recorded ranker change, oldest first."""
    return _read(ledger_path(base))


def _read(path: Path) -> list[RankerRecord]:
    if not path.is_file():
        return []
    records: list[RankerRecord] = []
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(str(row["ts"]))
                fingerprint = str(row["fingerprint"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("Unparseable ranker ledger line in %s", path.name)
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            records.append(RankerRecord(ts=ts, fingerprint=fingerprint))
    records.sort(key=lambda record: record.ts)
    return records


class RankerLedger:
    """Point-in-time lookup: which ranker was in force at a given instant."""

    def __init__(self, records: list[RankerRecord] | None = None):
        self._records = sorted(records or [], key=lambda record: record.ts)
        self._stamps = [record.ts for record in self._records]

    @classmethod
    def load(cls, base: Path | None = None) -> RankerLedger:
        return cls(load_ledger(base))

    def at(self, when: datetime | None) -> str:
        """The fingerprint in force at `when`, or `unknown`.

        A trace taken before the first ledger entry is genuinely unattributable —
        the ranker of that era was never recorded — so it reports `unknown` rather
        than borrowing the oldest known fingerprint.
        """
        if when is None or not self._records:
            return UNKNOWN
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        index = bisect_right(self._stamps, when)
        if index == 0:
            return UNKNOWN
        return self._records[index - 1].fingerprint
