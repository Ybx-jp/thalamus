"""The close ledger — proposals live here, and only approvals reach the graph.

A thread is closed on the operator's authority, and the authority arrives on one of
three surfaces: a CLI verb, the console on a phone, or the operator saying "close that"
to a session. All three write the same two rows, so no surface has a private path into
the graph and the audit does not have to know which one was used.

**A proposal is a ledger row and never a vertex.** That is the load-bearing choice, and
it is not about tidiness: an open Thread is already served into every consultation brief
and every `memory_open_threads` page, so a pending-close vertex would be *more* of
exactly the noise the close mechanism exists to remove — the surface would grow a second
population of half-real workitems that no session can act on. Keeping proposals out of
the graph also makes propose-here/approve-there work with nothing but an append: the
phone reads the same file the session wrote.

The shape is borrowed verbatim from `harness/quick.py`, where the same problem was
already solved — *"The fork answers; it does not close. Acceptance is the launcher's,
after the ledger row is checked."* An agent proposes; the approval is a separate act by
a separate party, recorded before the write it authorizes.

**What this cannot do.** It cannot authenticate the operator, and it does not pretend
to. The console binds loopback with no auth of its own, and a session proposing a close
runs Bash at the operator's uid. So a close is *attributable* — the row names the
surface and what evidence of approval exists — and forgery is caught by corroborating
the ledger against the graph afterwards (`thalamus thread audit`), not prevented at the
write. A schema that recorded `approved: true` would be claiming a guarantee nothing
here provides.
"""

from __future__ import annotations

import fcntl
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

CLOSES_DIR = Path.home() / ".thalamus" / "closes"
LEDGER_FILE = CLOSES_DIR / "closes.jsonl"

PROPOSED = "proposed"
APPROVED = "approved"
REJECTED = "rejected"

# Where the operator's approval was given. Recorded rather than inferred: the three
# surfaces have genuinely different evidence available, and collapsing them would make
# the weakest one look like the strongest.
SURFACES = ("cli", "console", "session")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_rows(path: Path | None = None) -> list[dict]:
    """Every ledger row in write order, malformed lines skipped.

    Write order, not timestamp order: a proposal and its approval can share a second,
    and the question this ledger answers — was it proposed before it was approved — is
    exactly the one sorting by the tied field would get wrong.
    """
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
            if isinstance(record, dict) and record.get("event"):
                rows.append(record)
    return rows


def _append(row: dict, path: Path | None = None) -> dict:
    """Append one row under an exclusive lock, and return it."""
    ledger = path or LEDGER_FILE
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return row


def propose(
    thread_id: str,
    scope: str,
    basis: str,
    disposition: str,
    rationale: str,
    proposed_by: str = "",
    path: Path | None = None,
) -> dict:
    """Record a proposed close. Writes a ledger row and **nothing to the graph**.

    `basis` is demanded here rather than at approval because the proposer is the party
    that has the evidence in hand. An operator approving on a phone three hours later
    is not going to reconstruct it, and a proposal that arrives without one is asking
    to be rubber-stamped.
    """
    return _append(
        {
            "event": PROPOSED,
            "ref": secrets.token_hex(8),
            "thread_id": thread_id,
            "scope": scope,
            "basis": basis,
            "disposition": disposition,
            "rationale": rationale,
            "proposed_by": proposed_by,
            "ts": _now(),
        },
        path,
    )


def pending(path: Path | None = None) -> list[dict]:
    """Proposals with no approval or rejection after them, oldest first."""
    rows = read_rows(path)
    settled = {
        row.get("ref") for row in rows if row.get("event") in (APPROVED, REJECTED)
    }
    return [
        row
        for row in rows
        if row.get("event") == PROPOSED and row.get("ref") not in settled
    ]


def find_proposal(ref: str, path: Path | None = None) -> dict | None:
    """The proposal a ref names, whether or not it has since been settled."""
    for row in read_rows(path):
        if row.get("event") == PROPOSED and row.get("ref") == ref:
            return row
    return None


def approve(
    ref: str,
    surface: str,
    approver_evidence: str,
    approved_by: str = "operator",
    path: Path | None = None,
) -> dict:
    """Record the operator's approval of a proposal.

    The row is written **before** the graph edge, and that order is deliberate: a close
    whose ledger row is missing cannot be corroborated afterwards, while a row whose
    edge is missing is a visible, repairable failure. The failure that leaves no trace
    is the one worth designing against.
    """
    if surface not in SURFACES:
        raise ValueError(f"unknown approval surface `{surface}` — one of {SURFACES}")
    proposal = find_proposal(ref, path)
    if proposal is None:
        raise ValueError(f"no proposal `{ref}` in the close ledger")
    return _append(
        {
            "event": APPROVED,
            "ref": ref,
            "thread_id": proposal["thread_id"],
            "scope": proposal["scope"],
            "surface": surface,
            "approver_evidence": approver_evidence,
            "approved_by": approved_by,
            "ts": _now(),
        },
        path,
    )


def reject(ref: str, reason: str = "", path: Path | None = None) -> dict:
    """Record that the operator declined a proposed close.

    Kept as a row rather than a deletion because a rejected proposal is the only
    negative evidence the basis-finders will ever get: precision cannot be measured
    from approvals alone.
    """
    proposal = find_proposal(ref, path)
    if proposal is None:
        raise ValueError(f"no proposal `{ref}` in the close ledger")
    return _append(
        {
            "event": REJECTED,
            "ref": ref,
            "thread_id": proposal["thread_id"],
            "scope": proposal["scope"],
            "reason": reason,
            "ts": _now(),
        },
        path,
    )


def approvals(path: Path | None = None) -> list[dict]:
    """Every approval row — what a graph-side close must be corroborated against."""
    return [row for row in read_rows(path) if row.get("event") == APPROVED]
