"""Redirect a session's distillation scope before it distills — `thalamus rescope`.

The pin is an OS process, so it cannot be changed mid-flight. But the
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
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thalamus.contract.manifest import available_scopes
from thalamus.contract.ontology import MAIN_SCOPE, vid

PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# The harness exports the live session id into every child process (measured
# 2026-07-28 on the running session). It is the authoritative answer to "which
# session am I", and the only one: a session cannot otherwise tell, and a guess
# has a measured cost — an agent inferred its id from a subagent task path,
# drew a well-formed UUID belonging to a *different, same-scope* session, and
# reasoned confidently about the wrong subject.
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"


def current_session_id(env: dict[str, str] | None = None) -> str | None:
    """The session this process is running inside, or None.

    Deliberately NOT falling back to "the most recent ledger entry for this cwd":
    concurrent sessions share a working directory routinely (two ran in this
    repo the night this guard was written), so that heuristic reintroduces exactly
    the wrong-subject failure it would be papering over. No answer beats a
    plausible wrong one.
    """
    return (env if env is not None else os.environ).get(SESSION_ID_ENV) or None


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
    # Who performed the correction, not just who it was performed on. The two
    # spurious rows a wrong-subject rescope left on another session's ledger were
    # indistinguishable from operator intent precisely because nothing recorded
    # their author; with this field that mistake reads as "session X edited
    # session Y" at a glance.
    by = current_session_id()
    if by:
        row["by_session"] = by
        if by != session_id:
            row["cross_session"] = True
    if already:
        row["forked_from"] = already

    if not dry_run:
        path = pins_file or PINS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    return row


def run(session: str | None, scope: str, reason: str = "", dry_run: bool = False,
        allow_distilled: bool = False, other_session: bool = False) -> int:
    try:
        if session:
            session_id = resolve_session(session)
            # The guard the wrong-subject failure needed. An explicitly-passed id
            # that differs from the live one is the exact shape of that failure: an
            # agent holding a plausible UUID from a file path, a transcript, or a
            # recalled memory, acting on it with confidence. This is checked
            # mechanically rather than asked of the caller — the harness knows which
            # session is running, so the override is *detected*, not self-declared,
            # and a caller who is wrong about its own identity cannot assert its way
            # past it.
            live = current_session_id()
            if live and session_id != live and not other_session:
                print(
                    f"Refused: you passed session {session_id[:8]}, but this process is "
                    f"running inside {live[:8]}.\n"
                    f"  If you meant this session, drop the argument — it defaults to the "
                    f"live one.\n"
                    f"  If you really mean to rescope a DIFFERENT session, pass "
                    f"--other-session to say so deliberately.\n"
                    f"  Before you do: is {session_id[:8]} an id you were told, or one you "
                    f"inferred from a path, a transcript, or a recalled memory? Inferring it "
                    f"has already cost a real, adjacent, same-scope session two "
                    f"rows it never earned."
                )
                return 1
            if live and session_id != live:
                print(f"CAUTION: rescoping {session_id[:8]}, which is NOT this session "
                      f"({live[:8]}). Recorded as cross_session in the ledger.")
        else:
            session_id = current_session_id()
            if not session_id:
                print(f"Refused: no session given and ${SESSION_ID_ENV} is not set, so the "
                      f"current session cannot be identified. Pass the id explicitly — but "
                      f"do not guess it.")
                return 1
            print(f"session: {session_id[:8]} (from ${SESSION_ID_ENV})")
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
