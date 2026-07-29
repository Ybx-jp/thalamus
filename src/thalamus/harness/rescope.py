"""Redirect a session's distillation scope before it distills — `thalamus rescope`.

The pin is an OS process (docs/07), so it cannot be changed mid-flight. But the
*routing decision* it encodes can be wrong for an ordinary reason: the operator
opened a pinned window and then did main-plane work in it. Without a supported
path, the only fix is hand-editing the tier-0 pin ledger, which is how this
command came to exist (2026-07-28).

**How it works.** `session-end.sh` resolves the distillation scope **ledger-first**
and reads `select(.session_id == $sid) | .scope | tail -1` — last row wins. The
ledger is append-only, so a correction is an *append*, never an edit: the original
pin record survives, and the correction sits beside it carrying the true `agent`
it was launched under plus a reason. That is the difference between an audit log
that can be corrected and one that can be rewritten.

**The refusal that matters.** Vertex IDs include scope
(`contract.ontology.vid` — `scope:main:session:abc`), so once a session has
distilled, changing its scope does not *move* the Session vertex; a later
extraction mints a **second** vertex under the new scope and leaves the first
holding a stale half of the transcript. Rescoping is therefore only meaningful
*before* distillation, and this command refuses afterwards rather than letting
the operator fork a session's identity. That refusal is not hypothetical: the
session that prompted this command was itself already distilled under its pin
from an earlier segment, and a hand-appended row would have forked it.

**Prior work.** Treating the ledger as part of the auditable operative state
rather than as scratch config follows the persistent-state framing in
*Always-OnAgents* (arXiv 2606.30306), which models an always-on agent's operative
state as including "task ledgers, permissions, credentials, commitments,
provenance and audit records" — not just retrievable memories. The
correct-by-appending stance, and the refusal that keeps a correction from
silently becoming a fork, are an **instantiation** of the "provenance-aware,
auditable, and *recoverable*" property surveyed in *From Agent Traces to Trust*
(arXiv 2606.04990): recoverability here means the mistake is repairable and the
repair is itself on the record. Neither source prescribes this mechanism; the
ledger-tail convention is local.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thalamus.contract.manifest import available_scopes
from thalamus.contract.ontology import MAIN_SCOPE, vid

PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"


class RescopeRefused(RuntimeError):
    """Raised instead of writing a correction that would fork a session."""


@dataclass
class LedgerRow:
    session_id: str
    scope: str
    ts: str


def read_rows(session_id: str, pins_file: Path | None = None) -> list[LedgerRow]:
    """Every ledger row for a session, in file order (last wins downstream)."""
    path = pins_file or PINS_FILE
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn line must not hide the rest of the ledger
        if d.get("session_id") == session_id:
            rows.append(LedgerRow(session_id, d.get("scope", MAIN_SCOPE), d.get("ts", "")))
    return rows


def resolve_session(prefix: str, pins_file: Path | None = None) -> str:
    """Expand a session-id prefix, the way `extract --session` accepts one."""
    path = pins_file or PINS_FILE
    if not path.is_file():
        raise RescopeRefused(f"no pin ledger at {path}")
    ids = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            sid = json.loads(line).get("session_id", "")
        except json.JSONDecodeError:
            continue
        if sid.startswith(prefix) and sid not in ids:
            ids.append(sid)
    if not ids:
        raise RescopeRefused(f"no session in the ledger matching `{prefix}`")
    if len(ids) > 1:
        raise RescopeRefused(f"`{prefix}` is ambiguous: {', '.join(i[:8] for i in ids)}")
    return ids[0]


def distilled_scopes(session_id: str, g=None) -> list[str]:
    """Scopes this session already has a Session vertex in.

    Non-empty means rescoping can no longer move anything — see the module
    docstring. Connects lazily so the rest of the module stays testable without
    a live graph.
    """
    from thalamus.substrate.writer import close_connection, connect

    own = g is None
    g = g or connect()
    try:
        scopes = [MAIN_SCOPE, *available_scopes()]
        found = []
        for scope in scopes:
            if g.V(vid("Session", session_id, scope=scope)).has_next():
                found.append(scope)
        return found
    finally:
        if own:
            close_connection(g)


def rescope(session_id: str, scope: str, reason: str = "", agent: str = "",
            pins_file: Path | None = None, dry_run: bool = False,
            allow_distilled: bool = False, g=None) -> dict:
    """Append a correction row. Refuses if it could not take effect cleanly."""
    valid = {MAIN_SCOPE, *available_scopes()}
    if scope not in valid:
        raise RescopeRefused(
            f"unknown scope `{scope}`. Available: {', '.join(sorted(valid))}")

    rows = read_rows(session_id, pins_file)
    if not rows:
        raise RescopeRefused(
            f"session {session_id[:8]} is not in the pin ledger — nothing to correct")

    current = rows[-1].scope
    if current == scope:
        raise RescopeRefused(
            f"session {session_id[:8]} already resolves to `{scope}`; no correction needed")

    already = distilled_scopes(session_id, g=g)
    if already and not allow_distilled:
        raise RescopeRefused(
            f"session {session_id[:8]} has already distilled into "
            f"{', '.join(f'`{s}`' for s in already)}. Vertex IDs include scope, so a "
            f"correction now would not move that Session vertex — the next extraction "
            f"would mint a second one under `{scope}` and leave the first holding a "
            f"stale half of the transcript. Rescope only takes effect before "
            f"distillation. (--allow-distilled overrides, and forks the session.)")

    row = {
        "event": "rescope",
        "session_id": session_id,
        "scope": scope,
        "agent": agent,
        "cwd": "",
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": reason or f"operator redirected distillation from `{current}` to `{scope}`",
    }
    if already:
        row["forked_from"] = already

    if not dry_run:
        path = pins_file or PINS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    return row


def run(session: str, scope: str, reason: str = "", dry_run: bool = False,
        allow_distilled: bool = False) -> int:
    try:
        session_id = resolve_session(session)
        row = rescope(session_id, scope, reason=reason, dry_run=dry_run,
                      allow_distilled=allow_distilled)
    except RescopeRefused as exc:
        print(f"Refused: {exc}")
        return 1
    verb = "would append" if dry_run else "appended"
    print(f"{verb} rescope: {session_id[:8]} -> `{scope}`")
    print(f"  reason: {row['reason']}")
    if row.get("forked_from"):
        print(f"  WARNING: forked from already-distilled {row['forked_from']}")
    if not dry_run:
        print("\nTakes effect at SessionEnd (ledger-first resolution). "
              "The original pin record is retained — the ledger is append-only.")
    return 0
