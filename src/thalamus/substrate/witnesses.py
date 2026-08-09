"""How many *independent* groundings a set of asserting sessions is — docs/09 §Scope.

A claim asserted by N sessions is not evidence from N witnesses whenever those
sessions were correlated, and the artifact is undetectable after the fact: nothing
in a finished graph separates three sessions that independently agreed from three
that were forked from one another. `room` and `forked_from` are stamped at write
time precisely so this layer has something to read.

The resolution docs/09 settles on is **two readings over one write path**, not a
second field — `N` ("how often was this said", the bag semiring) alongside
`PosBool(X)` ("how many independent groundings", idempotent and absorptive). Both
are reported; neither replaces the other.

The two axes are deliberately **not** symmetric, and the asymmetry is the whole
design:

- **A fork collapses.** `forked_from` records that a session inherited its parent's
  context rather than reaching its own conclusions, so it is a mapping over the
  parent's material and its agreement corroborates nothing. That is the
  event-as-source modeling the session-as-source schema otherwise lacks, available
  here only because the dependence is recorded rather than inferred.
- **A room does not.** A room hosts many turns, so it is not an event identifier;
  collapsing by it would trade a false-count error for a false-collapse error.
  Room-mates are *flagged* as correlated and left counted. Membership makes
  correlation plausible, where a fork parent makes it certain.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Witness:
    """One session that asserted a claim, with the two axes that can correlate it."""

    session_id: str
    room: str = ""
    forked_from: str = ""


@dataclass(frozen=True)
class Corroboration:
    """The two readings, plus the rooms that make the count worth distrusting."""

    asserted: int
    """N — how often this was said. Every asserting session, correlated or not."""

    independent: int
    """PosBool(X) — distinct groundings, after fork chains collapse into their root."""

    rooms: tuple[str, ...] = ()
    """Rooms holding more than one of these witnesses. Flagged, never collapsed."""

    @property
    def correlated(self) -> bool:
        """Whether anything here should stop a reader treating `asserted` as agreement."""
        return self.independent < self.asserted or bool(self.rooms)

    def note(self) -> str:
        """One line for a human or an agent reading a recall, or "" when there is
        nothing to say.

        Empty in the ordinary case on purpose: recall output is charged against the
        reader's context (lab/006-007), so an independence line that fires on every
        uncorrelated claim would cost every session to inform almost none.
        """
        if not self.correlated:
            return ""
        parts = []
        if self.independent < self.asserted:
            forks = self.asserted - self.independent
            parts.append(
                f"{self.independent} independent grounding"
                f"{'s' if self.independent != 1 else ''} — "
                f"{forks} of these forked from another and corroborate nothing"
            )
        if self.rooms:
            named = ", ".join(f"`{r}`" for r in self.rooms)
            parts.append(
                f"witnesses shared room {named}, so they may be one conversation "
                "rather than separate agreement"
            )
        return "; ".join(parts)


def corroboration(witnesses: list[Witness]) -> Corroboration:
    """Read a set of asserting sessions both ways.

    Fork collapse is transitive but **closed over the given set**: a session whose
    parent is not itself a witness stands as its own grounding, even if that parent
    forked from one that is. Walking outside the set would mean asserting a
    dependence between two sessions on the strength of a third that never made the
    claim — an inference, where every other input here is a record. A gap in the
    chain therefore costs a collapse rather than inventing one.
    """
    by_id = {w.session_id: w for w in witnesses if w.session_id}
    ids = set(by_id)

    def root(session_id: str, seen: frozenset[str] = frozenset()) -> str:
        """The earliest ancestor of this session that is also a witness here."""
        parent = by_id[session_id].forked_from
        # A cycle cannot arise from the launcher (a fork's parent always predates
        # it), so this guards against a hand-edited or corrupted ledger rather than
        # a real shape — but an infinite loop in a recall path is not an acceptable
        # way to find that out.
        if not parent or parent not in ids or parent in seen:
            return session_id
        return root(parent, seen | {session_id})

    independent = {root(session_id) for session_id in ids}

    counts: dict[str, int] = {}
    for witness in by_id.values():
        if witness.room:
            counts[witness.room] = counts.get(witness.room, 0) + 1
    shared = tuple(sorted(room for room, n in counts.items() if n > 1))

    return Corroboration(
        asserted=len(witnesses),
        independent=len(independent) if ids else len(witnesses),
        rooms=shared,
    )
