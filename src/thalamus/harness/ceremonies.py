"""The ceremony ledger — what a room records while it can still be recorded.

Capture is now-or-never and analysis never is, so this module is the first thing built
of the room lifecycle and deliberately not the most interesting one. It writes the four records
that make later analysis *possible at all* — the ones no amount of care after the fact
can reconstruct:

1. **A ceremony occasion**, written at ceremony **start**, so an aborted ceremony still
   leaves a row. A ceremony that only writes on success cannot be distinguished from one
   that never ran.
2. **Non-occurrence.** A skipped retrospective is a row. Otherwise a skip is
   indistinguishable from an unlogged ceremony and the only naturally-occurring
   ablation in the design is lost.
3. **A stable `deliverable_id`**, minted once and carried across every revision. Nothing
   in a finished graph tells you two artifacts at two times were one deliverable.
4. **The assignment and its seed, written before the ceremony runs.** A
   randomization-inference reference distribution is the set of assignments that *could
   have* happened; unrecorded in advance, that set does not exist
   (`eval/randomization.py`).

**Nothing here is an outcome.** The ledger records that an occasion happened, to whom,
under which arm — never whether it worked. Room-level inference is descriptive forever
at this corpus size, and a capture layer that started
scoring things would be manufacturing the outcome it was built to make honest.

## One file, and an `event` on every row

All four records share `~/.thalamus/ceremonies/ceremonies.jsonl` for a reason item 4
supplies: the assignment must be provably *prior* to the occasion it assigns, and a
single append-only file orders its rows by position rather than only by a timestamp
two writers could tie on.

Sharing a ledger is exactly what went wrong in the pin ledger, where `pin-engaged.sh`'s
`{event: "engaged"}` rows carried none of the launch fields and last-row-wins read a
correctly-launched fork as having met no obligation. The fix
generalises rather than argues against sharing: **every row here carries `event` from
row one**, and every reader filters on it before reading anything else. A row kind that
cannot be told apart from another is the defect; two kinds in one file is not.

## And three that make the analysis honest rather than possible

5. **A commitment** — the room's forecast about a deliverable, which converts a
   self-report into something falsifiable.
6. **A resolution**, written by tooling and never by a member. The asymmetry is the
   whole value: a forecaster cannot Goodhart a resolution it does not control. Nothing
   here can stop a member running the verb, so the obligation is made *checkable* —
   the row names its resolver and `audit()` reports one that sat in the room.
7. **The out-of-room comparator**, named while the room is still running. Position in
   the file catches one named afterwards, exactly as it does for item 4.

## What this module does not do

There is no dispatch, no ceremony *conduct*, and no promotion path. Those are the rest
of the room lifecycle and they can be added later without losing anything; these
cannot.

**Nothing here attributes cost.** Burn per occasion is a join between these rows'
timestamps and the harness transcripts (`eval/cost.py`), because a room member is one
session that sits in many occasions — a field on this side could only ever name one.
"""

from __future__ import annotations

import fcntl
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CEREMONIES_DIR = Path.home() / ".thalamus" / "ceremonies"
LEDGER_FILE = CEREMONIES_DIR / "ceremonies.jsonl"

# Findings the operator has read and accepted as permanent. Deliberately a *second*
# file: the ledger is append-only and its rows are evidence, so the way to stop an
# audit failing is never to write a row asserting something that did not happen.
#
# This changes the exit code and nothing else. `LedgerAudit.clean()` still reports
# the defect, `note()` still prints it, and an acknowledgement names one finding
# exactly — so the same defect arising in a different room is a new finding and
# fails again. Acknowledging is how a permanent, already-understood finding stops
# drowning the next real one; it is not how a finding is disposed of.
ACK_FILE = CEREMONIES_DIR / "acknowledged.jsonl"

# The surviving ceremonies of the lifecycle's filter, and a closed set on purpose. The
# lifecycle's whole discipline is that a ceremony must earn its place against a
# constraint agent sessions actually have — three were cut — so a kind arriving by
# typo is not a new ceremony, it is a silently forked occasion counter. `retrospective`
# stays separate from `close` because it is the one whose *non-occurrence* the design
# most wants countable.
CEREMONY_KINDS = ("open", "review", "acceptance", "retrospective", "close")

# Row kinds. `assigned` precedes `start`; `end` and `skipped` are terminal.
EVENT_ASSIGNED = "assigned"
EVENT_START = "start"
EVENT_END = "end"
EVENT_SKIPPED = "skipped"
EVENT_DELIVERABLE = "deliverable"
EVENT_REVISION = "revision"
EVENT_COMMITMENT = "commitment"
EVENT_RESOLUTION = "resolution"
EVENT_COMPARATOR = "comparator"

# How a commitment came out. A closed set because the primary endpoint counts these,
# and free text would make the count a judgement call made once, at write time, by
# whoever happened to be resolving.
RESOLUTION_OUTCOMES = ("appeared", "absent", "superseded")

# The out-of-room arms. `room` is the treatment, so it is not a comparator for itself.
COMPARATOR_ARMS = ("solo", "ticket")

# The draw algorithm, versioned in every assignment row. A seed replays an assignment
# only against the procedure that consumed it, so changing the deal without changing
# this name would silently invalidate every earlier row's reference distribution while
# leaving it looking replayable.
PROCEDURE = "blocked-shuffle-v1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "deliverable"


def read_rows(path: Path | None = None) -> list[dict]:
    """Every ledger row in write order, malformed lines skipped.

    Order is load-bearing rather than incidental: `audit()` decides whether an
    assignment preceded its occasion by position, so a reader that sorted these by
    timestamp would answer item 4's question with the field two concurrent writers are
    most likely to tie on.
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
    """Append one row under an exclusive lock, and return it.

    The lock is held across read-then-append, not just the write, because
    `occasion_index` is computed from the rows already present: two ceremonies opening
    in one room at once would otherwise both read the same count and claim the same
    occasion. Sessions run concurrently in this checkout by design, so that race is the
    expected case rather than the exotic one.
    """
    ledger = path or LEDGER_FILE
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return row


def occasion_id(room: str, kind: str, index: int) -> str:
    """The occasion's name, and the key item 8 puts on a session record.

    Readable and derivable rather than random: `eval/cost.py` attributes burn per
    ceremony by this string, and an operator reading a cost table should be able to see
    which occasion a row is without joining back to the ledger.
    """
    return f"{room}:{kind}:{index}"


def next_index(room: str, kind: str, rows: list[dict] | None = None,
                path: Path | None = None) -> int:
    """The next occasion number for one (room, kind), counting from 1.

    **A skipped ceremony consumes an index.** The counter numbers *occasions* — the
    moments the ceremony was due — not the times it ran, so a room whose third
    retrospective was skipped has no fourth-that-is-really-third. Renumbering around
    skips would erase the non-occurrence item 2 exists to preserve.
    """
    records = rows if rows is not None else read_rows(path)
    seen = sum(
        1
        for row in records
        if row.get("event") in (EVENT_START, EVENT_SKIPPED)
        and row.get("room") == room
        and row.get("ceremony_kind") == kind
    )
    return seen + 1


# --- 4. The assignment, written before the ceremony runs ----------------------------


def assignment_space(units: int, counts: tuple[int, ...]) -> int:
    """How many ways this many units could have been dealt into these arm sizes.

    The multinomial coefficient — the size of the reference distribution for one block.
    Reported at assignment time rather than at analysis time because it is a property of
    the design, knowable while the design is still free to change
    (`randomization.feasible` makes the same argument for the two-arm case).
    """
    if units < 0 or any(count < 0 for count in counts) or sum(counts) != units:
        return 0
    total = math.factorial(units)
    for count in counts:
        total //= math.factorial(count)
    return total


def draw(units: list[str], arms: list[str], counts: list[int], seed: int) -> dict[str, str]:
    """Deal units to arms deterministically from a seed. `PROCEDURE`'s definition.

    Sorted first, then shuffled, so the result depends on the *set* of units and the
    seed and not on the order the caller happened to pass them in — otherwise two
    replays of the same recorded assignment could disagree while both looking faithful.
    """
    if len(arms) != len(counts):
        raise ValueError("every arm needs a count")
    if sum(counts) != len(units):
        raise ValueError(
            f"counts sum to {sum(counts)} but there are {len(units)} unit(s) — an "
            "assignment that does not deal every unit has no reference distribution"
        )
    if len(set(units)) != len(units):
        raise ValueError("units must be distinct — a repeated unit is assigned twice")

    pool = sorted(units)
    random.Random(seed).shuffle(pool)
    assignment: dict[str, str] = {}
    cursor = 0
    for arm, count in zip(arms, counts, strict=True):
        for unit in pool[cursor : cursor + count]:
            assignment[unit] = arm
        cursor += count
    return assignment


def record_assignment(
    room: str,
    kind: str,
    units: list[str],
    arms: list[str],
    counts: list[int],
    seed: int,
    *,
    prereg_id: str = "",
    path: Path | None = None,
) -> dict:
    """Write the assignment for one room's next occasions, before any of them run.

    The row carries what a reference distribution needs and a seed alone does not: the
    eligible units *as they stood at assignment time*, the arm sizes, the block, and the
    procedure that consumed the seed. A unit added after this row is not in the space,
    which is the correct and uncomfortable reading — hence writing it late is a design
    error the audit reports rather than a bookkeeping slip.

    The block is the room. The lifecycle restricts permutation so a deliverable is never
    swapped across rooms, and since a row assigns within one room, the restriction is
    structural here rather than a rule analysis has to remember to apply.
    """
    if kind not in CEREMONY_KINDS:
        raise ValueError(f"unknown ceremony kind `{kind}` — one of {CEREMONY_KINDS}")
    assignment = draw(units, arms, counts, seed)
    return _append(
        {
            "event": EVENT_ASSIGNED,
            "room": room,
            "ceremony_kind": kind,
            "units": sorted(units),
            "arms": list(arms),
            "counts": list(counts),
            "assignment": assignment,
            "assignment_seed": seed,
            "procedure": PROCEDURE,
            "block": room,
            "space": assignment_space(len(units), tuple(counts)),
            "prereg_id": prereg_id,
            "ts": _now(),
        },
        path,
    )


# --- 1. The occasion, written at start ----------------------------------------------


def start(
    room: str,
    kind: str,
    *,
    participant_scopes: list[str] | None = None,
    deliverable_ids: list[str] | None = None,
    arm: str = "",
    prereg_id: str = "",
    path: Path | None = None,
) -> dict:
    """Open an occasion. Returns the row, whose `occasion_id` is the handle for it.

    Written before the ceremony does anything, which is the whole point: an occasion
    that crashes, is abandoned, or is interrupted mid-flight has still left the row that
    says it was attempted, and `audit()` reports it as unfinished rather than as absent.

    `arm` is not defaulted from the assignment record on purpose. This field records
    what the occasion *realized*; the assignment records what it was *supposed* to
    realize, and silently copying one into the other would make the disagreement between
    them — the only evidence that a randomization was not honoured — unobservable.
    """
    if kind not in CEREMONY_KINDS:
        raise ValueError(f"unknown ceremony kind `{kind}` — one of {CEREMONY_KINDS}")
    ledger = path or LEDGER_FILE
    index = next_index(room, kind, path=ledger)
    return _append(
        {
            "event": EVENT_START,
            "room": room,
            "ceremony_kind": kind,
            "occasion_index": index,
            "occasion_id": occasion_id(room, kind, index),
            "participant_scopes": sorted(participant_scopes or []),
            "deliverable_ids": sorted(deliverable_ids or []),
            "arm": arm,
            "assignment_seed": "",
            "prereg_id": prereg_id,
            "ts_start": _now(),
        },
        ledger,
    )


def end(occasion: str, *, outcome: str = "", path: Path | None = None) -> dict:
    """Close an occasion with a second row. The ledger is append-only.

    `ts_end` arrives as its own row rather than as a mutation of the start row because a
    file that is rewritten in place can lose the very rows an abort was supposed to
    leave behind — and because two readers of a mutable ledger can disagree about what
    it said. The pairing is by `occasion_id`.

    `outcome` says how the occasion ended, never how well it went. Scoring lives outside
    the capture layer.
    """
    return _append(
        {
            "event": EVENT_END,
            "occasion_id": occasion,
            "outcome": outcome,
            "ts_end": _now(),
        },
        path,
    )


# --- 2. Non-occurrence ---------------------------------------------------------------


def skip(room: str, kind: str, *, reason: str = "", path: Path | None = None) -> dict:
    """Record that a due ceremony did **not** happen.

    This is the row that makes the design's only naturally-occurring ablation readable.
    Rooms will skip ceremonies — for cost, for irrelevance, because nobody triggered one
    — and the difference between "skipped" and "ran but was never logged" is invisible
    unless the skip writes. `reason` is free text and analysis should not lean on it;
    the row's existence is the datum.
    """
    if kind not in CEREMONY_KINDS:
        raise ValueError(f"unknown ceremony kind `{kind}` — one of {CEREMONY_KINDS}")
    ledger = path or LEDGER_FILE
    index = next_index(room, kind, path=ledger)
    return _append(
        {
            "event": EVENT_SKIPPED,
            "room": room,
            "ceremony_kind": kind,
            "occasion_index": index,
            "occasion_id": occasion_id(room, kind, index),
            "reason": reason,
            "ts": _now(),
        },
        ledger,
    )


# --- 3. The stable deliverable id ----------------------------------------------------


def mint_deliverable(
    room: str,
    title: str,
    *,
    owner_scope: str = "",
    occasion: str = "",
    path: Path | None = None,
) -> dict:
    """Mint a deliverable's permanent id at planning time.

    The id is `<room>:<slug>` and never changes, including when the title does: the
    title describes the deliverable, the id *is* it. Collisions inside a room take a
    numeric suffix, so minting twice under one name produces two deliverables rather
    than quietly merging them into one — a false merge is the error that cannot be
    detected later, since the two revision histories would be interleaved beyond
    separation.
    """
    ledger = path or LEDGER_FILE
    rows = read_rows(ledger)
    taken = {
        str(row.get("deliverable_id"))
        for row in rows
        if row.get("event") == EVENT_DELIVERABLE
    }
    base = f"{room}:{_slug(title)}"
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return _append(
        {
            "event": EVENT_DELIVERABLE,
            "room": room,
            "deliverable_id": candidate,
            "title": title,
            "owner_scope": owner_scope,
            "occasion_id": occasion,
            "ts": _now(),
        },
        ledger,
    )


def record_revision(
    deliverable: str,
    *,
    artifact: str = "",
    occasion: str = "",
    author_scope: str = "",
    path: Path | None = None,
) -> dict:
    """Attach a revision to an existing deliverable id.

    The row is what carries identity across time. `artifact` is whatever names this
    revision concretely — a path, a commit, a vertex id — and is deliberately untyped
    here, because the fate of a commitment is resolved by tooling against git and the
    graph and pinning the format now would decide that later question
    early.
    """
    return _append(
        {
            "event": EVENT_REVISION,
            "deliverable_id": deliverable,
            "artifact": artifact,
            "occasion_id": occasion,
            "author_scope": author_scope,
            "ts": _now(),
        },
        path,
    )


def commit(
    room: str,
    deliverable: str,
    commitment_text: str,
    *,
    owner_scope: str = "",
    predicted_artifact: str = "",
    resolve_by: str = "",
    occasion: str = "",
    path: Path | None = None,
) -> dict:
    """Record one forecast: what this deliverable will have done by when.

    This is the row that converts a self-report into something falsifiable. The room
    says what it expects to be true later; `resolve()` — run by tooling, against git
    and the graph — says what actually was. The asymmetry is the point: **a forecaster
    cannot Goodhart a resolution it does not control**, which is why the deliverables
    report is a commitment list rather than a narrative, and why no LLM judge over the
    room's own prose can stand in for it.

    `predicted_artifact` and `resolve_by` are what make the forecast resolvable at all.
    A commitment with neither is a sentence about intent, so both are recorded even
    when empty and the audit can see which rooms wrote unresolvable forecasts.
    """
    return _append(
        {
            "event": EVENT_COMMITMENT,
            "room": room,
            "deliverable_id": deliverable,
            "owner_scope": owner_scope,
            "commitment_text": commitment_text,
            "predicted_artifact": predicted_artifact,
            "resolve_by": resolve_by,
            "occasion_id": occasion,
            "ts": _now(),
        },
        path,
    )


def resolve(
    deliverable: str,
    outcome: str,
    *,
    resolver: str,
    evidence: str,
    room: str = "",
    occasion: str = "",
    path: Path | None = None,
) -> dict:
    """Record what became of a commitment. **Written by tooling, never by a member.**

    `resolver` names what did the checking and `evidence` is what it checked — a path,
    a commit, a vertex id. Both are required rather than defaulted: a resolution with
    no evidence is the room grading its own homework in a format that looks like a
    measurement, which is worse than no row at all.

    The prohibition is enforced by being *checkable* rather than by being stated.
    Nothing here can stop a member running this verb, so the row records who resolved
    it and `audit()` names any resolution whose resolver is a scope that sat in the
    room it resolves.
    """
    if outcome not in RESOLUTION_OUTCOMES:
        raise ValueError(
            f"unknown outcome `{outcome}` — one of {RESOLUTION_OUTCOMES}"
        )
    if not resolver.strip():
        raise ValueError("a resolution must name its resolver")
    if not evidence.strip():
        raise ValueError(
            "a resolution must carry evidence — an unevidenced resolution is a "
            "self-report wearing a measurement's shape"
        )
    return _append(
        {
            "event": EVENT_RESOLUTION,
            "room": room,
            "deliverable_id": deliverable,
            "outcome": outcome,
            "resolver": resolver,
            "evidence": evidence,
            "occasion_id": occasion,
            "ts": _now(),
        },
        path,
    )


def record_comparator(
    room: str,
    arm: str,
    reference: str,
    *,
    basis: str = "",
    path: Path | None = None,
) -> dict:
    """Name the out-of-room unit this room will be read against, while it can still count.

    A comparator chosen after the outcomes are known is not a comparison — the choice
    absorbs the result. So this row is written at open, and `audit()` reads *position*
    to catch one written after the room closed, the same way item 4's assignment check
    does.

    `reference` identifies the unit concretely (a session id, a ticket id); `basis`
    says why it is comparable. The arms are solo and ticket, because `room` is the
    treatment and cannot be a comparator for itself.
    """
    if arm not in COMPARATOR_ARMS:
        raise ValueError(
            f"unknown comparator arm `{arm}` — one of {COMPARATOR_ARMS}; `room` is the "
            "treatment and cannot compare against itself"
        )
    return _append(
        {
            "event": EVENT_COMPARATOR,
            "room": room,
            "arm": arm,
            "reference": reference,
            "basis": basis,
            "ts": _now(),
        },
        path,
    )


def outstanding(rows: list[dict] | None = None,
                path: Path | None = None) -> list[dict]:
    """Commitment rows with no resolution yet, in write order.

    Deliberately *not* an audit finding. The audit names defects that could not be
    reconstructed later, and an unresolved commitment is the ordinary state of a
    forecast whose horizon has not arrived — it stays resolvable for as long as the
    row exists, which is the whole design.

    Resolution is matched on `deliverable_id`, following the lifecycle's commitment
    shape,
    so one resolution settles every commitment made about that deliverable. Two
    forecasts about one deliverable that could come out differently need two
    deliverables, and minting is cheap for exactly that reason.
    """
    records = rows if rows is not None else read_rows(path)
    resolved = {
        str(row.get("deliverable_id"))
        for row in records
        if row.get("event") == EVENT_RESOLUTION
    }
    return [
        row
        for row in records
        if row.get("event") == EVENT_COMMITMENT
        and str(row.get("deliverable_id")) not in resolved
    ]


def deliverables(room: str = "", rows: list[dict] | None = None,
                 path: Path | None = None) -> dict[str, list[dict]]:
    """Deliverable id → its revision rows in order, for one room or all of them."""
    records = rows if rows is not None else read_rows(path)
    minted = {
        str(row.get("deliverable_id")): []
        for row in records
        if row.get("event") == EVENT_DELIVERABLE
        and (not room or row.get("room") == room)
    }
    for row in records:
        if row.get("event") == EVENT_REVISION:
            key = str(row.get("deliverable_id"))
            if key in minted:
                minted[key].append(row)
    return minted


# --- The audit that makes the four worth writing -------------------------------------


FINDING_LABELS = {
    "unassigned": "occasion(s) with an arm but no prior assignment — no reference "
                  "distribution exists for these",
    "late-assignment": "occasion(s) assigned after they started",
    "arm-mismatch": "occasion(s) whose realized arm contradicts the assignment",
    "unminted": "deliverable id(s) used but never minted",
    "orphan-end": "end row(s) for an occasion that never started",
    "duplicate-occasion": "duplicated occasion id(s)",
    "unaccounted": "ceremony(s) a closed room neither held nor skipped — the record "
                   "cannot say whether these happened",
    "member-resolution": "resolution(s) written by a member of the room being resolved "
                         "— the forecaster does not get to grade the forecast",
    "uncompared": "closed room(s) with no out-of-room comparator named while it counted",
    "late-comparator": "room(s) whose comparator was named after they closed",
}


@dataclass(frozen=True)
class LedgerAudit:
    """What the ledger says about its own completeness.

    Every finding here is a defect the ledger can still name *today* and could not
    reconstruct later, which is the same standard that put items 1–4 first.
    """

    occasions: int = 0
    skipped: int = 0
    unfinished: tuple[str, ...] = ()
    """Occasions with a start and no end. Not an error — an aborted ceremony leaving a
    row is the behaviour item 1 was built for — but a live room with a growing count
    here is a ceremony that never closes."""

    unassigned: tuple[str, ...] = ()
    """Occasions carrying an arm whose deliverables were never assigned in advance. The
    sharp one: post-hoc assignment does not merely weaken the inference, it means the
    reference distribution does not exist."""

    late_assignments: tuple[str, ...] = ()
    """Occasions whose assignment row was written *after* their start row. Detected by
    position in the file, which is why the four record kinds share one ledger."""

    arm_mismatches: tuple[str, ...] = ()
    """Occasions whose realized arm contradicts the arm its deliverable was dealt. A
    randomization not honoured, and unreadable from either record alone."""

    unminted: tuple[str, ...] = ()
    """Deliverable ids referenced by an occasion or a revision but never minted."""

    orphan_ends: tuple[str, ...] = ()
    """End rows naming an occasion that never started."""

    duplicate_occasions: tuple[str, ...] = ()
    """Occasion ids claimed more than once — the shape a lost lock would produce."""

    member_resolutions: tuple[str, ...] = ()
    """Resolutions whose resolver sat in the room being resolved. The forecast's whole
    value is that the forecaster does not control the resolution, so this is the one
    finding here that voids a *result* rather than a record."""

    uncompared: tuple[str, ...] = ()
    """Closed rooms that never named an out-of-room comparator. Nothing later supplies
    one: a comparator picked once the outcomes are visible has absorbed them."""

    late_comparators: tuple[str, ...] = ()
    """Rooms whose comparator row was written after the room closed — detected by
    position, like `late_assignments`, and for the same reason."""

    unaccounted: tuple[str, ...] = ()
    """`<room>:<kind>` for a ceremony a closed room neither held nor skipped. Every
    other finding here reads rows that exist; this one reads the absence, which is the
    only defect in the list a ledger cannot show you by being read. A skip row makes a
    non-occurrence into the ablation it is, so a kind with neither row is not a room
    that declined a ceremony — it is a room whose record cannot say whether it did."""

    def clean(self) -> bool:
        return not (
            self.unassigned
            or self.late_assignments
            or self.arm_mismatches
            or self.unminted
            or self.orphan_ends
            or self.duplicate_occasions
            or self.unaccounted
            or self.member_resolutions
            or self.uncompared
            or self.late_comparators
        )

    def findings(self) -> tuple[tuple[str, str], ...]:
        """`(category, item)` for every defect, in the order `note()` prints them.

        The category is part of the key rather than decoration: `uncompared` and
        `unaccounted` can both name the same room, and an acknowledgement that
        covered both because they share a room name would retire a finding nobody
        read.
        """
        found: list[tuple[str, str]] = []
        for category, items in self._categories():
            found.extend((category, item) for item in items)
        return tuple(found)

    def _categories(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return (
            ("unassigned", self.unassigned),
            ("late-assignment", self.late_assignments),
            ("arm-mismatch", self.arm_mismatches),
            ("unminted", self.unminted),
            ("orphan-end", self.orphan_ends),
            ("duplicate-occasion", self.duplicate_occasions),
            ("unaccounted", self.unaccounted),
            ("member-resolution", self.member_resolutions),
            ("uncompared", self.uncompared),
            ("late-comparator", self.late_comparators),
        )

    def note(self, acknowledged: dict[str, str] | None = None) -> str:
        seen = acknowledged or {}
        lines = [
            f"Ceremony ledger: {self.occasions} occasion(s), {self.skipped} recorded "
            f"non-occurrence(s), {len(self.unfinished)} unfinished"
        ]
        for category, items in self._categories():
            if not items:
                continue
            lines.append(f"  {len(items)} {FINDING_LABELS[category]}:")
            for item in sorted(items):
                key = f"{category}:{item}"
                if key in seen:
                    # Still printed, and printed first-class. A finding that stops
                    # being shown is a finding nobody will ever revisit.
                    lines.append(f"    {item}  [acknowledged — {seen[key]}]")
                else:
                    lines.append(f"    {item}")
        if self.clean():
            lines.append("  clean — every occasion is assigned in advance and accounted for")
        elif not self.unacknowledged(seen):
            lines.append(
                "  every finding above is acknowledged — the ledger is unchanged and "
                "still holds them; only the exit code is discharged"
            )
        return "\n".join(lines)

    def unacknowledged(self, acknowledged: dict[str, str] | None = None
                       ) -> tuple[tuple[str, str], ...]:
        """Findings with no acknowledgement — what the exit code is allowed to read."""
        seen = acknowledged or {}
        return tuple(
            (category, item)
            for category, item in self.findings()
            if f"{category}:{item}" not in seen
        )


def audit(rows: list[dict] | None = None, path: Path | None = None) -> LedgerAudit:
    """Read the ledger against its own obligations.

    Ordering is read from the file, not from timestamps: `late_assignments` asks whether
    the assignment was written before the occasion, and a second-resolution timestamp
    ties routinely on rows a script writes back to back.
    """
    records = rows if rows is not None else read_rows(path)

    started: dict[str, int] = {}
    duplicates: list[str] = []
    ended: set[str] = set()
    orphan_ends: list[str] = []
    minted: set[str] = set()
    used: dict[str, None] = {}
    assigned_at: dict[tuple[str, str, str], int] = {}
    assignment_arm: dict[tuple[str, str, str], str] = {}
    occasions: list[dict] = []
    skipped = 0
    accounted: dict[str, set[str]] = {}
    closed_rooms: set[str] = set()
    closed_at: dict[str, int] = {}
    deliverable_room: dict[str, str] = {}
    participants: dict[str, set[str]] = {}
    compared_at: dict[str, int] = {}
    resolutions: list[tuple[str, str, str]] = []

    for position, row in enumerate(records):
        event = row.get("event")
        if event == EVENT_DELIVERABLE:
            minted.add(str(row.get("deliverable_id")))
            deliverable_room[str(row.get("deliverable_id"))] = str(row.get("room"))
        elif event == EVENT_COMMITMENT:
            used.setdefault(str(row.get("deliverable_id")), None)
        elif event == EVENT_COMPARATOR:
            compared_at.setdefault(str(row.get("room")), position)
        elif event == EVENT_RESOLUTION:
            used.setdefault(str(row.get("deliverable_id")), None)
            resolutions.append(
                (
                    str(row.get("deliverable_id")),
                    str(row.get("room") or ""),
                    str(row.get("resolver") or ""),
                )
            )
        elif event == EVENT_REVISION:
            used.setdefault(str(row.get("deliverable_id")), None)
        elif event == EVENT_ASSIGNED:
            mapping = row.get("assignment")
            if isinstance(mapping, dict):
                for unit, arm in mapping.items():
                    key = (str(row.get("room")), str(row.get("ceremony_kind")), str(unit))
                    assigned_at[key] = position
                    assignment_arm[key] = str(arm)
        elif event == EVENT_SKIPPED:
            skipped += 1
            accounted.setdefault(str(row.get("room")), set()).add(
                str(row.get("ceremony_kind"))
            )
        elif event == EVENT_START:
            key = str(row.get("occasion_id"))
            if key in started:
                duplicates.append(key)
            started[key] = position
            occasions.append(row)
            kind = str(row.get("ceremony_kind"))
            accounted.setdefault(str(row.get("room")), set()).add(kind)
            participants.setdefault(str(row.get("room")), set()).update(
                str(scope) for scope in (row.get("participant_scopes") or [])
            )
            if kind == "close":
                closed_at.setdefault(str(row.get("room")), position)
                # Close is when the record becomes final. Before it, a missing ceremony
                # is `not yet`; demanding one from a live room would report every room
                # mid-flight as defective.
                closed_rooms.add(str(row.get("room")))
            for deliverable in row.get("deliverable_ids") or []:
                used.setdefault(str(deliverable), None)
        elif event == EVENT_END:
            key = str(row.get("occasion_id"))
            if key not in started:
                orphan_ends.append(key)
            ended.add(key)

    unassigned: list[str] = []
    late: list[str] = []
    mismatched: list[str] = []
    for row in occasions:
        arm = str(row.get("arm") or "")
        if not arm:
            # An occasion with no arm is not in an experiment, and demanding an
            # assignment for it would report every ordinary ceremony as a defect.
            continue
        room = str(row.get("room"))
        kind = str(row.get("ceremony_kind"))
        keys = [
            (room, kind, str(unit)) for unit in (row.get("deliverable_ids") or [])
        ]
        known = [key for key in keys if key in assigned_at]
        if not known:
            unassigned.append(str(row.get("occasion_id")))
            continue
        start_position = started.get(str(row.get("occasion_id")), 0)
        if any(assigned_at[key] > start_position for key in known):
            late.append(str(row.get("occasion_id")))
        if any(assignment_arm[key] != arm for key in known):
            mismatched.append(str(row.get("occasion_id")))

    unaccounted = [
        f"{room}:{kind}"
        for room in closed_rooms
        for kind in CEREMONY_KINDS
        if kind not in accounted.get(room, set())
    ]

    member_resolutions = [
        f"{deliverable} by `{resolver}`"
        for deliverable, stated_room, resolver in resolutions
        if resolver
        and resolver in participants.get(
            stated_room or deliverable_room.get(deliverable, ""), set()
        )
    ]
    uncompared = [room for room in closed_rooms if room not in compared_at]
    late_comparators = [
        room
        for room, position in compared_at.items()
        if room in closed_at and position > closed_at[room]
    ]

    return LedgerAudit(
        member_resolutions=tuple(sorted(set(member_resolutions))),
        uncompared=tuple(sorted(set(uncompared))),
        late_comparators=tuple(sorted(set(late_comparators))),
        occasions=len(occasions),
        skipped=skipped,
        unaccounted=tuple(sorted(unaccounted)),
        unfinished=tuple(sorted(key for key in started if key not in ended)),
        unassigned=tuple(sorted(set(unassigned))),
        late_assignments=tuple(sorted(set(late))),
        arm_mismatches=tuple(sorted(set(mismatched))),
        unminted=tuple(sorted(key for key in used if key and key not in minted)),
        orphan_ends=tuple(sorted(set(orphan_ends))),
        duplicate_occasions=tuple(sorted(set(duplicates))),
    )


def load_acknowledged(path: Path | None = None) -> dict[str, str]:
    """`<category>:<item>` -> reason, last write wins.

    Machine-local by construction: it sits beside the ledger under `~/.thalamus`,
    which is not the repository, so acknowledging a finding on one box never
    discharges it on another. That is the intended blast radius — the ledger it
    describes is local too.
    """
    store = path or ACK_FILE
    if not store.is_file():
        return {}
    seen: dict[str, str] = {}
    for line in store.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("finding"):
            seen[str(row["finding"])] = str(row.get("reason") or "no reason given")
    return seen


def acknowledge(finding: str, *, reason: str, rows: list[dict] | None = None,
                ledger: Path | None = None, path: Path | None = None) -> dict:
    """Accept one named finding as permanent, discharging only the exit code.

    Refused unless the finding is currently reported. An acknowledgement written
    ahead of the defect it names would pre-approve a class of failure, which is the
    one thing this must not become — the point is to retire an understood finding so
    the next unread one is visible, not to make the audit quiet.
    """
    if not reason.strip():
        raise ValueError(
            "an acknowledgement must carry a reason — the finding stays in the "
            "report, and an unexplained one is worse than a red exit code"
        )
    report = audit(rows, ledger)
    live = {f"{category}:{item}" for category, item in report.findings()}
    if finding not in live:
        raise ValueError(
            f"`{finding}` is not a current finding — nothing to acknowledge. "
            f"Run `thalamus ceremony audit` to see the exact keys."
        )
    store = path or ACK_FILE
    store.parent.mkdir(parents=True, exist_ok=True)
    row = {"finding": finding, "reason": reason.strip(), "ts": _now()}
    with store.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(row) + "\n")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return row


def render(rows: list[dict] | None = None, path: Path | None = None) -> str:
    """The ledger as a room-by-room reading, with the audit under it."""
    records = rows if rows is not None else read_rows(path)
    if not records:
        return (
            "Ceremony ledger: empty. No occasion has been recorded — and an occasion "
            "not recorded while it happened cannot be recovered afterwards."
        )

    per_room: dict[str, list[dict]] = {}
    for row in records:
        if row.get("event") in (EVENT_START, EVENT_SKIPPED):
            per_room.setdefault(str(row.get("room")), []).append(row)

    ended = {
        str(row.get("occasion_id"))
        for row in records
        if row.get("event") == EVENT_END
    }
    lines = []
    for room in sorted(per_room):
        held = per_room[room]
        lines.append(f"room `{room}` — {len(held)} occasion(s):")
        for row in held:
            key = str(row.get("occasion_id"))
            if row.get("event") == EVENT_SKIPPED:
                reason = f" — {row.get('reason')}" if row.get("reason") else ""
                lines.append(f"  {key:32} SKIPPED{reason}")
                continue
            scopes = ", ".join(row.get("participant_scopes") or []) or "no participants"
            arm = f" [arm {row.get('arm')}]" if row.get("arm") else ""
            state = "" if key in ended else "  UNFINISHED"
            lines.append(f"  {key:32} {scopes}{arm}{state}")
        held_deliverables = deliverables(room, records)
        for deliverable, revisions in sorted(held_deliverables.items()):
            lines.append(f"  {deliverable:32} {len(revisions)} revision(s)")
    lines.append("")
    lines.append(audit(records).note())
    return "\n".join(lines)
