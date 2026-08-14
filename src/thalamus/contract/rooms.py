"""What a room can establish about its own members, per harness — a third record.

`boundaries.py` answers "does this boundary bind here"; `pinning.py` answers "can a
session be pinned here, and to what extent". This answers a third question that was
being carried inside the second one's answer: **what can a dispatcher establish about a
member before it writes to it.**

The split exists because one row was two-thirds true. `room.peer_roster` bundled three
capabilities that Claude Code happens to ship in one artifact — `sessions/<pid>.json`
carries identity, liveness (`pid` + `procStart`) and `status` together — and reading
that fusion as one property is what let a gate pass vacuously: dispatch was permitted
when a *roster* existed, and tmux supplies a roster, while the thing the gate was
protecting against is the *readiness* half and was undiminished by it. Bundle only
where the states genuinely co-vary, never where one half can die alone.

The gate that replaces it: **`room.peer_delivery` may be PROVIDED only where
`room.peer_readiness` is.** Under it, a harness that can enumerate and address members
but cannot say whether one is holding an approval modal is refused — and refused
*naming this row*, which is a materially better artifact than "no live members", a
message that tells an operator to relaunch sessions that are running fine.
"""

from __future__ import annotations

from dataclasses import dataclass

from thalamus.contract.boundaries import Evidence, Provision
from thalamus.contract.probes import Condition

COMPONENTS: dict[str, str] = {
    "room.peer_identity": "who is a member of this room, enumerable before a send",
    "room.peer_liveness": "whether that member's process is still there",
    "room.peer_readiness": "whether it is safe to send — nothing is holding an approval modal",
    "room.peer_delivery": "a message can be put in front of a member at all",
}

# Which component each other one may not outrank. `peer_delivery` gated on
# `peer_readiness` is the correction the roster split produced; the other two are
# preconditions of it in the ordinary way — you cannot ask whether a member you cannot
# name is ready.
GATES: dict[str, str] = {
    "room.peer_delivery": "room.peer_readiness",
    "room.peer_readiness": "room.peer_identity",
    "room.peer_liveness": "room.peer_identity",
}


@dataclass(frozen=True)
class RoomRow:
    component: str
    harness: str
    state: Provision
    evidence: Evidence
    note: str

    @property
    def label(self) -> str:
        return f"{self.component} on {self.harness}"


_CLAUDE = Evidence(
    kind="source-read",
    at="2026-08-13",
    where="`$CLAUDE_CONFIG_DIR/sessions/<pid>.json` carries name, pid/procStart and "
          "status; `harness/quick.live_sessions` reads all three",
    verified_against="quick.py",
    conditions=(),
    reask="free",
)

_TMUX = Evidence(
    kind="source-read",
    at="2026-08-13",
    where="`harness/panes.py` recovers room, scope and address from "
          "`#{pane_start_command}`, which `pin._with_room` writes and which survives "
          "`respawn-window`; liveness is `#{pane_dead}`",
    verified_against="panes.py",
    conditions=(),
    reask="free",
)

_BRACKET = Evidence(
    kind="live-session",
    at="2026-08-13",
    where="`beforeShellExecution` fires before Cursor's own approval modal — probe hook "
          "logged 11:01:15, modal still unanswered 11:01:20 (lab/065 §5) — so "
          "`hooks/cursor/readiness-*.sh` bracket the interval a modal can occupy and "
          "`harness/readiness.py` reads the descriptor they write",
    verified_against="cursor/2026.08.11-e8db854",
    conditions=(Condition.INTERACTIVE,),
    reask="live-session",
)


ROOM_ROWS: tuple[RoomRow, ...] = (
    RoomRow("room.peer_identity", "claude", Provision.PROVIDED, _CLAUDE,
            "The harness registers each session, so enumerating the directory is "
            "enumerating membership."),
    RoomRow("room.peer_liveness", "claude", Provision.PROVIDED, _CLAUDE,
            "`pid` + `procStart` against `/proc`, which distinguishes a live session "
            "from a recycled pid."),
    RoomRow("room.peer_readiness", "claude", Provision.PROVIDED, _CLAUDE,
            "`status` is written by the session from inside its own event loop — a "
            "fact about a conversation, not a reading of a screen."),
    RoomRow("room.peer_delivery", "claude", Provision.PROVIDED, _CLAUDE,
            "`tmux send-keys` to the pane the pin ledger records."),

    RoomRow("room.peer_identity", "cursor", Provision.PROVIDED, _TMUX,
            "Not the vendor's, and stronger on one axis for it: the control plane is "
            "ours, so this is the one channel here whose evidence cannot go stale "
            "against a vendor build. It also answers for `main`, which carries no "
            "`--agent` and is invisible to the descriptor roster."),
    RoomRow("room.peer_liveness", "cursor", Provision.PROVIDED, _TMUX,
            "Asked of the pane rather than inferred from the start command being "
            "readable: a dead process leaves its start command behind."),
    RoomRow("room.peer_readiness", "cursor", Provision.PROVIDED, _BRACKET,
            "A descriptor our own hooks bracket, not a vendor field and not a screen "
            "scrape. **Its coverage is shell and MCP calls only** — a workspace-trust "
            "dialog, a model picker or a file-write approval is outside the bracket, "
            "and is caught only where the screen read happens to see it. Partial "
            "coverage on a safety gate is stated here rather than discovered: what is "
            "bracketed is enumerated, and a member publishing no descriptor at all is "
            "refused rather than assumed idle."),
    RoomRow("room.peer_delivery", "cursor", Provision.PROVIDED, _BRACKET,
            "`tmux send-keys` to the pane, permitted by the gate above rather than by "
            "the roster's existence."),
)


def check_rooms() -> list[tuple[RoomRow, str, str]]:
    """Re-ask what can be re-asked, and enforce the gate. Returns (row, outcome, detail).

    The gate is checked here rather than trusted to a reviewer because its failure mode
    is silence: a row promoted to PROVIDED without its precondition reads exactly like
    one that earned it, and the promotion that mattered was of the row whose absence was
    the whole objection.
    """
    states = {(row.component, row.harness): row.state for row in ROOM_ROWS}
    results = []
    for row in ROOM_ROWS:
        gated_on = GATES.get(row.component)
        if gated_on and row.state is Provision.PROVIDED:
            precondition = states.get((gated_on, row.harness))
            if precondition is not Provision.PROVIDED:
                results.append((
                    row, "drift",
                    f"declared PROVIDED while `{gated_on}` on {row.harness} is "
                    f"{precondition.value if precondition else 'undeclared'} — the gate "
                    f"exists because this row passing on the strength of a roster is "
                    f"how a dispatcher was permitted into a member holding a modal",
                ))
                continue
        if row.evidence.reask != "free":
            results.append((row, "unprobeable",
                            f"needs a live session against {row.evidence.verified_against}"))
            continue
        results.append((row, "confirmed", ""))
    return results
