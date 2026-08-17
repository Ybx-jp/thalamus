"""Did the room treatment actually occur? — the manipulation check for room arms.

A room is a launch fact: `--room` puts sessions in one and the schema stamps it.
Whether those sessions *collaborated* is a different question, and
the difference is the entire treatment. A room whose members never messaged each
other is a set of solo sessions wearing a room label, and an arm like that cannot
separate "rooms do not help" from "the room did not happen".

So this is a **manipulation check, not a score** — the same standing as the
consequence probes in `arms.py`, and for the same reason: it says whether the
intervention landed, never whether it worked. Nothing here should be reported as an
outcome, and a room that fails the check is grounds for excluding an arm rather than
for concluding anything about rooms.

Two topologies, from two ledgers, and the gap between them is the point:

- **Nominal** — who was *allowed* to talk. The pin ledger (`~/.thalamus/pins/`)
  records every session and the room it launched into, so a room's members are known
  including the ones that never said anything. Membership is what the guard permits,
  so the nominal graph is complete over those members.
- **Realized** — who actually *sent*. The guard ledger (`~/.thalamus/guards/`) writes
  one row per `SendMessage` decision carrying the room, the sender, the target and the
  verdict, so the permitted `roommate` rows are a directed edge list.

**A realized edge is a permitted send, not a delivery.** The room guard is
outbound-only and fires *before* the send, so a pass means the boundary allowed the
message — name resolution can still refuse it downstream, and nothing here
observes the receiver. Overcounting in that direction is the safe one for a
manipulation check: it can only make a room look more collaborative than it was, so a
room that fails the check on permitted sends did not collaborate under any reading.

Node identity inside a room is the **scope**, because members launch as
`<room>-<scope>` and that name is what both the guard's roommate pattern and the
sender's target string are built from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

GUARDS_DIR = Path.home() / ".thalamus" / "guards"
PINS_FILE = Path.home() / ".thalamus" / "pins" / "pins.jsonl"

# The guard's own name for the room-boundary rows, distinguishing them from the
# other guards sharing this ledger directory.
ROOM_GUARD = "room-boundary"

# Branch names the guard writes (harness/hooks/claude-code/room-guard.sh). Only
# `roommate` is an intra-room edge: `parent` is the spawning conversation and
# `subagent-id` an in-process subagent, neither of which is a peer session, and
# `outside-room` is by definition not one either.
ROOMMATE_BRANCH = "roommate"
OUTSIDE_BRANCH = "outside-room"


def peer_scope(target: str, room: str) -> str:
    """The scope a `SendMessage` target names, or "" if it does not name a member.

    Targets arrive as the launcher's window name, `<room>-<scope>`, and `SendMessage`
    wants a disambiguating ` [ref]` suffix on first contact (a whole arm has been lost
    to omitting it), so both forms have to normalize to the same peer.
    """
    name = target.strip()
    if name.endswith("]") and "[" in name:
        name = name[: name.rindex("[")].strip()
    prefix = f"{room}-"
    if not name.startswith(prefix):
        return ""
    return name[len(prefix) :]


@dataclass(frozen=True)
class RoomTopology:
    """One room's nominal membership against its realized sends."""

    room: str
    members: tuple[str, ...]
    """Scopes launched into this room, from the pin ledger. Silent members included —
    that they are countable while invisible in the guard ledger is the whole reason
    the nominal graph is read from a different ledger than the realized one."""

    edges: tuple[tuple[str, str, int], ...] = ()
    """`(sender_scope, peer_scope, permitted_sends)`, directed, self-edges dropped."""

    blocked: int = 0
    """Sends from inside this room the boundary refused. Not a realized edge, but
    evidence the members were *trying* to reach out — a room can fail the check with
    a high block count, and that means something different from silence."""

    unresolved: int = 0
    """Roommate-branch rows whose target did not parse to a member at all. Surfaced
    rather than dropped: a nonzero count means the realized graph is undercounted, and
    an undercount is exactly what would fake a failed manipulation check."""

    self_sends: int = 0
    """Rows whose target resolved to the sender's own scope. Excluded from the graph
    but counted apart from `unresolved`, because the two license opposite readings: a
    self-send is understood and correctly dropped, where an unparsed target means the
    edge list is missing something. Conflating them would make every self-send raise a
    lower-bound caveat the data does not support."""

    @property
    def occurred(self) -> bool:
        """Whether any member's message to another member was permitted.

        The bar is deliberately one edge. This asks whether the treatment happened at
        all, and graduating it into "enough collaboration" would smuggle an outcome
        judgement into a check whose entire value is that it makes none.
        """
        return bool(self.edges)

    @property
    def sends(self) -> int:
        return sum(count for _sender, _peer, count in self.edges)

    @property
    def reciprocated(self) -> int:
        """Member pairs that sent *both* ways.

        A one-way pair is a broadcast; a reciprocated pair is the exchange the room's
        fast tier was built for, so the two are worth telling apart before
        any dose-response reading is attempted.
        """
        directed = {(sender, peer) for sender, peer, _count in self.edges}
        return sum(1 for a, b in directed if a < b and (b, a) in directed)

    @property
    def density(self) -> float:
        """Connected member pairs over possible ones, direction ignored.

        Zero for a room of fewer than two members — a room of one has no pair to
        connect, so its manipulation check fails on the roster and never reaches the
        guard ledger. A run of exactly that shape was recorded as carrying no in-room
        control of its own.
        """
        possible = list(combinations(sorted(self.members), 2))
        if not possible:
            return 0.0
        linked = {
            (min(sender, peer), max(sender, peer)) for sender, peer, _count in self.edges
        }
        return len(linked & set(possible)) / len(possible)

    def note(self) -> str:
        """One line stating whether the treatment landed, and on what evidence."""
        if len(self.members) < 2:
            return (
                f"room `{self.room}`: NOT A ROOM — {len(self.members)} member, so no "
                "pair could collaborate; exclude rather than count as a room arm"
            )
        if not self.occurred:
            tried = f", {self.blocked} send(s) refused at the boundary" if self.blocked else ""
            return (
                f"room `{self.room}`: TREATMENT DID NOT OCCUR — {len(self.members)} "
                f"members, no permitted message between any two{tried}; this is a set "
                "of solo sessions wearing a room label"
            )
        parts = [
            f"room `{self.room}`: treatment occurred — {self.sends} permitted send(s) "
            f"over {len(self.edges)} directed pair(s) among {len(self.members)} members",
            f"density {self.density:.2f}",
            f"{self.reciprocated} reciprocated pair(s)",
        ]
        if self.unresolved:
            parts.append(
                f"{self.unresolved} target(s) unresolved, so the graph is a lower bound"
            )
        return "; ".join(parts)


def _iter_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                rows.append(record)
    return rows


def room_members(pins_file: Path | None = None) -> dict[str, set[str]]:
    """Room → the scopes launched into it, from the pin ledger.

    A session appears once per launch, so a scope relaunched into the same room is one
    member and not two. Rooms are keyed by the ledger's own `room` value; a blank one
    is a session that worked alone and is not a room at all.
    """
    members: dict[str, set[str]] = {}
    for record in _iter_rows(pins_file or PINS_FILE):
        room = str(record.get("room") or "")
        scope = str(record.get("scope") or "")
        if room and scope:
            members.setdefault(room, set()).add(scope)
    return members


def room_topologies(
    *, pins_file: Path | None = None, guards_base: Path | None = None
) -> list[RoomTopology]:
    """Every room the pin ledger knows, with its realized sends attached.

    Driven from the **pin** ledger, not the guard ledger, and that direction is the
    design: a room that never produced a single guard row is precisely the room this
    check exists to catch, and starting from the guard ledger would make it invisible.
    """
    members = room_members(pins_file)
    directory = guards_base or GUARDS_DIR

    counts: dict[str, dict[tuple[str, str], int]] = {}
    blocked: dict[str, int] = {}
    unresolved: dict[str, int] = {}
    selves: dict[str, int] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.jsonl")):
            for record in _iter_rows(path):
                if record.get("guard") != ROOM_GUARD:
                    continue
                room = str(record.get("room") or "")
                if not room:
                    continue
                branch = str(record.get("branch") or "")
                if branch == OUTSIDE_BRANCH:
                    blocked[room] = blocked.get(room, 0) + 1
                    continue
                if branch != ROOMMATE_BRANCH or record.get("verdict") != "pass":
                    continue
                sender = str(record.get("scope") or "")
                peer = peer_scope(str(record.get("target") or ""), room)
                # Both ends must be known members. The prefix alone is not membership
                # — `alpha-typo` parses as cleanly as `alpha-architect` — and admitting
                # an unrecognized peer would add a node the roster never had, inflating
                # the edge set against a density denominator drawn from the members.
                roster = members.get(room, set())
                if not sender or not peer or peer not in roster or sender not in roster:
                    unresolved[room] = unresolved.get(room, 0) + 1
                    continue
                if sender == peer:
                    selves[room] = selves.get(room, 0) + 1
                    continue
                edges = counts.setdefault(room, {})
                edges[(sender, peer)] = edges.get((sender, peer), 0) + 1

    topologies = []
    for room in sorted(members):
        edges = counts.get(room, {})
        topologies.append(
            RoomTopology(
                room=room,
                members=tuple(sorted(members[room])),
                edges=tuple(
                    (sender, peer, count) for (sender, peer), count in sorted(edges.items())
                ),
                blocked=blocked.get(room, 0),
                unresolved=unresolved.get(room, 0),
                self_sends=selves.get(room, 0),
            )
        )
    return topologies


def render(topologies: list[RoomTopology]) -> str:
    """The check, one line per room, with the roll-up that gates a campaign."""
    if not topologies:
        return (
            "Rooms: none in the pin ledger. Nothing to check — a room arm cannot be "
            "interpreted until one exists."
        )
    lines = [f"Rooms ({len(topologies)}):"]
    lines.extend(f"  {topology.note()}" for topology in topologies)
    landed = sum(1 for topology in topologies if topology.occurred)
    lines.append(
        f"  treatment occurred in {landed}/{len(topologies)} room(s) — arms from the "
        "rest are not room arms and should be excluded before analysis, not after"
    )
    return "\n".join(lines)
