"""The run ledger, and the durability idiom no current writer in this repo has.

Two existing writers each get half of it right and neither gets both:
`harness/ceremonies.py:157-173` takes an exclusive `flock` and never syncs;
`eval/rescore.py:371-378` syncs and never locks. This one does both.

The rule that matters more than either, and that comes from a live defect:
**derive nothing from the file you are appending to.** `ceremonies.py`'s docstring
claims its lock is held across read-then-append, but `_append` locks a single write
while `start()` computes `next_index()` through its own unlocked read — so the race the
docstring says is prevented is live, and the audit's `duplicate-occasion` finding
detects it after the fact rather than preventing it. A run id derived by counting rows
would reproduce that bug exactly. `uuid4` needs no read at all, which is why it is used
here in preference to a sequence number that would read better in a report.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .model import CaseResult, Outcome

LEDGER_DIR = Path.home() / ".thalamus" / "qe"
LEDGER_PATH = LEDGER_DIR / "runs.jsonl"


def repo_rev(repo_root: Path) -> str:
    """The commit the suite ran against, or `unknown`.

    Stamped into every row because a known-red expectation is only meaningful relative
    to a revision: "this defect is unfixed" is a claim about a tree, and a row that
    cannot name its tree cannot be audited later.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        rev = out.stdout.strip()
        return rev or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def dirty(repo_root: Path) -> bool:
    """Is the tree dirty? Recorded, not refused.

    A dirty tree does not invalidate a run — most runs during development are dirty —
    but a red result against uncommitted changes is not evidence about the revision it
    names, and the row has to say so or a later reader will treat it as though it were.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass(frozen=True)
class RunHeader:
    run_id: str
    started_at: str
    tier: str
    rev: str
    dirty: bool
    expectations_sha: str


def new_header(tier: str, rev: str, tree_dirty: bool, expectations_sha: str) -> RunHeader:
    return RunHeader(
        run_id=uuid.uuid4().hex[:12],
        started_at=datetime.now(UTC).isoformat(),
        tier=tier,
        rev=rev,
        dirty=tree_dirty,
        expectations_sha=expectations_sha,
    )


def _row(header: RunHeader, result: CaseResult, verdict: str) -> dict:
    finding = result.finding
    return {
        "run_id": header.run_id,
        "at": datetime.now(UTC).isoformat(),
        "rev": header.rev,
        "dirty": header.dirty,
        "expectations_sha": header.expectations_sha,
        "tier": result.tier.value,
        "case": result.name,
        "outcome": result.outcome.value,
        # The verdict is the RECONCILED reading — outcome against expectation. Kept
        # distinct from `outcome` on purpose: "failed" and "failed as expected" are two
        # states, and collapsing them into one field is the defect class this suite is
        # named for.
        "verdict": verdict,
        "failure_class": finding.failure_class.value if finding else None,
        "witness": finding.witness if finding else "",
        "site": finding.site if finding else "",
        "summary": finding.summary if finding else result.detail,
        "missing_substrate": [s.value for s in result.missing],
        "duration_s": round(result.duration_s, 3),
    }


def append(header: RunHeader, rows: list[tuple[CaseResult, str]]) -> Path:
    """Append every row of one run under a single exclusive lock, then fsync.

    One lock for the whole run rather than one per row: a run is the unit a reader
    reconstructs, and interleaving two concurrent runs' rows costs nothing to prevent
    here. The directory is fsynced too — a durable file in an unsynced directory can
    still vanish, which is the half of the idiom `eval/rescore.py` omits.
    """
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(_row(header, r, v), sort_keys=True) + "\n" for r, v in rows)

    fd = os.open(LEDGER_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    dir_fd = os.open(LEDGER_DIR, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return LEDGER_PATH


def summarize(rows: list[tuple[CaseResult, str]]) -> dict[str, int]:
    """Counts by verdict, plus the denominator.

    `_report_capabilities` (`cli.py:2032`) states the reason this includes skips: a
    checker printing only OK reports a green light over an unknown denominator, and
    "nothing was wrong" and "nothing was asked" become the same output.
    """
    counts: dict[str, int] = {}
    for _result, verdict in rows:
        counts[verdict] = counts.get(verdict, 0) + 1
    counts["total"] = len(rows)
    counts["skipped"] = sum(1 for r, _ in rows if r.outcome is Outcome.SKIPPED)
    return counts
