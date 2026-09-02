"""The randomized-withholding ledger, read as an outcome measure.

`policy.py` has been suppressing a random quarter of every retrieval's offered
nodes since 2026-07-30, logging each draw, and `sync.py` lands the draw on the
Trace it produced. That is a real randomization running on real work at zero
marginal model cost — and nothing has ever read it as an outcome (tracker #107).
This module is the first read.

**The outcome, and why this one first.** Of the four candidates ruled on in
consultation exchange `b73e25ff0268496d`, this is the one that needs no new judge
and no new instrumentation: *does a withheld node come back?* If suppressing a
node left a gap the session actually had to close, the session covers that ground
again — a later retrieval in the same session re-offers the node. If the node was
never going to matter, nothing brings it back. The contrast is against the **kept**
nodes of the same event, which is what makes it a measurement rather than a base
rate: kept and withheld were drawn from one offered set, against one query, by one
Bernoulli, so under the null they recur alike.

**Two things the corpus turned out to require, both measured 2026-09-01.**

*The offered list comes from the ledger, not the graph.* `sync.py` lands
`offered_count` and drops the ids, and a trace's RETURNS edges are a **superset** of
what the draw covered: a rendered response is assembled from more retrieval than the
one call `policy.apply` saw, and 277 of 738 traces return nodes that were never in
the draw. Reconstructing `offered` as RETURNS-plus-withheld would sweep those
uncovered nodes into the kept arm and dilute it. The ledger holds the real list, and
`policy_seed` joins the two halves — 738 of 738, with every kept node confirmed
returned and every withheld node confirmed absent.

*Recurrence is read against everything a later retrieval SURFACED, not only what it
returned.* The exchange named the returned set; returned is surfaced-minus-withheld,
so reading it there puts every recurrence through a second 0.25 coin. That
attenuates both arms alike rather than biasing either, but for nothing — a node
re-offered and suppressed again has still come back. The report carries the
exchange's original definition beside the primary, and the two differ by roughly the
withhold rate, which is the check that this reasoning is right.

**What this cannot see.** Recurrence is the ranker re-surfacing a node, which is
evidence the session returned to that ground — not evidence the candidate noticed
the gap, and not evidence the node would have helped. A session that re-asks
because it was stuck and one that re-asks because the topic simply continued are
the same row here.

**The falsifier for a null, and it has not been run.** A null here is consistent
with withholding changing nothing — and equally consistent with the measure being
blind to the thing it was built for. Recurrence needs the *same node id* to come
back, which needs a later query whose terms match it; a session that closes a gap
by asking in different words re-surfaces different nodes and scores as a miss in
both arms. The base recurrence rate is 33%, so the measure is not floored, but
that is an argument about sensitivity in general and not about this mechanism.
What would settle it: score the withheld node's *text* against later retrievals
rather than its id — outcome candidate (1)'s machinery in `b73e25ff0268496d`,
whose own weakest point is whether a judge's false-positive rate is symmetric
between text that was shown and text that was not.

Grounded in `b73e25ff0268496d` (the outcome layer and the cluster structure) and
`5bb4d93324c64f95` (one eligibility predicate shared by null pool and denominator).
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T

from thalamus.eval import policy as policy_mod
from thalamus.eval.rates import Rate

# Permutation draws. The attainable two-sided p floor is 1/(DRAWS+1), printed with
# the result rather than left for a reader to work out — a p that cannot go below
# its own floor is the first thing to check when one arrives just under .05.
DRAWS = 10_000
SEED = 20260901


@dataclass(frozen=True)
class Event:
    """One retrieval that carried a withholding draw."""

    trace_id: str
    session_id: str
    scope: str
    ts: str
    tool: str
    # The policy's own offered list, from the ledger. NOT reconstructible from the
    # graph: `sync.py` lands `offered_count` and drops the ids, and the trace's
    # RETURNS edges are a superset — a rendered response is assembled from more
    # than the one retrieval the policy saw, so 277 of 738 traces return nodes the
    # draw never covered. Rebuilding `offered` as RETURNS-plus-withheld would
    # therefore move uncovered nodes into the kept arm and silently dilute it.
    offered: tuple[str, ...]
    withheld: frozenset[str]
    # Everything the ranker surfaced on this trace, covered by the draw or not.
    # This is the universe recurrence is read against: a node that comes back
    # outside the policy's subset has still come back.
    surfaced: frozenset[str]

    @property
    def kept(self) -> tuple[str, ...]:
        return tuple(vid for vid in self.offered if vid not in self.withheld)

    @property
    def contested(self) -> bool:
        """Both arms present, so the event can contribute a within-event contrast.

        A singleton offer can never be contested: `policy.apply`'s never-withhold-
        everything rule strips the draw whenever `withheld == offered`, which for a
        one-node offer fires on every draw that comes up true. Its realized
        inclusion probability is 0, not the nominal rate — so it is excluded by the
        randomization mechanism itself rather than by anything about its outcome.
        """
        return bool(self.withheld) and bool(self.kept)


@dataclass(frozen=True)
class Arm:
    """One arm's recurrence, counted over nodes."""

    hits: int
    total: int


@dataclass(frozen=True)
class Report:
    events: int
    landed_withheld: int
    landed_offered: int
    singleton_events: int
    uncontested_events: int
    terminal_events: int
    eligible_events: int
    sessions: int
    withheld: Arm
    kept: Arm
    returned_withheld: Arm
    returned_kept: Arm
    session_differences: dict[str, float]
    statistic: float
    p_value: float
    p_floor: float
    null_sd: float
    detectable: float
    draws: int
    unjoined_events: int
    scope: str

    def render(self) -> str:
        lines = [
            f"Randomized withholding, read as recurrence — scope `{self.scope}`",
            f"  {self.events} events carrying a draw; {self.landed_withheld} nodes "
            f"withheld of {self.landed_offered} offered",
        ]
        if self.unjoined_events:
            lines.append(
                f"  ! {self.unjoined_events} trace(s) with no matching ledger row "
                "for their policy_seed — dropped. Expected to be zero; a nonzero "
                "count means the ledger and the graph have drifted apart"
            )
        lines.append(
            f"  excluded: {self.singleton_events} singleton-offer "
            f"(withholding impossible by construction), "
            f"{self.uncontested_events} uncontested (one arm empty), "
            f"{self.terminal_events} with no later retrieval in the session"
        )
        lines.append(
            f"  eligible: {self.eligible_events} events across {self.sessions} sessions"
        )
        lines.append("")
        for label, arm in (
            ("withheld nodes recurring", self.withheld),
            ("kept nodes recurring", self.kept),
        ):
            lines.append("  " + Rate(
                label=label,
                hits=arm.hits,
                total=arm.total,
                null=None,
                null_reason=(
                    "the other arm is the null — this rate alone says nothing, "
                    "and the pair is what the permutation test reads"
                ),
                interval=None,
                interval_reason=(
                    "reported as the paired session-level difference below, which "
                    "is the clustered unit; a per-arm interval would ignore that "
                    "the two arms share an event"
                ),
                unit="nodes",
            ).render())
        lines.append("")
        lines.append(
            f"  session-level difference (withheld − kept), mean over "
            f"{self.sessions} sessions: {self.statistic:+.3f}"
        )
        lines.append(
            f"  two-sided within-event permutation p = {self.p_value:.4f} "
            f"({self.draws:,} draws; attainable floor {self.p_floor:.4f})"
        )
        lines.append(
            f"  the null distribution's SD is {self.null_sd:.3f}, so this design "
            f"detects a difference of about {self.detectable:+.3f} "
            f"({100 * self.detectable:.1f}pp) at 80% power — anything smaller is "
            f"below the box and is not claimed either way"
        )
        lines.append(
            "  ^ the label permuted is withheld-vs-kept, within each event, with "
            "the event's withheld count held fixed — the exchangeable unit the "
            "randomization actually created. Nothing is permuted across events or "
            "across sessions."
        )
        lines.append("")
        lines.append(
            f"  on the exchange's original definition (recurrence in a later "
            f"event's RETURNED set): withheld "
            f"{self.returned_withheld.hits}/{self.returned_withheld.total}, kept "
            f"{self.returned_kept.hits}/{self.returned_kept.total}"
        )
        return "\n".join(lines)


def load_events(g, *, scope: str = "", ledger_base=None) -> tuple[list[Event], int]:
    """Every Trace that carried a withholding draw, joined to its ledger row.

    Two halves, and each holds something the other does not. The graph knows which
    session a draw belonged to (`sync.py` fills that in from the tap; the ledger's
    own `session_id` is blank on every row by design) and what the retrieval
    surfaced. The ledger knows which nodes were offered, which the graph reduced to
    a count. The join key is `policy_seed`, unique across the ledger.

    A trace with no ledger row is counted as unjoined and dropped — measured at 0
    of 738 on 2026-09-01, so the tally exists to notice the day that changes rather
    than to absorb a known loss.
    """
    ledger = policy_mod.load(ledger_base)
    by_seed = {record.seed: record for record in ledger.values()}
    query = g.V().has_label("Trace").has("policy_seed")
    if scope:
        query = query.has("scope", scope)
    rows = (
        query
        .project("id", "session", "scope", "ts", "tool", "seed", "withheld",
                 "oc", "returned")
        .by(T.id)
        .by("session_id")
        .by("scope")
        .by("ts")
        .by(__.coalesce(__.values("tool"), __.constant("")))
        .by("policy_seed")
        .by("withheld")
        .by("offered_count")
        .by(__.out("RETURNS").id_().dedup().fold())
        .to_list()
    )
    events, unjoined = [], 0
    for row in rows:
        record = by_seed.get(row["seed"])
        if record is None or len(record.offered) != row["oc"]:
            unjoined += 1
            continue
        withheld = frozenset(record.withheld)
        events.append(Event(
            trace_id=row["id"],
            session_id=row["session"],
            scope=row["scope"],
            ts=row["ts"],
            tool=row["tool"],
            offered=tuple(record.offered),
            withheld=withheld,
            surfaced=frozenset(row["returned"]) | withheld,
        ))
    return events, unjoined


def _by_session(events: list[Event]) -> dict[str, list[Event]]:
    sessions: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        sessions[event.session_id].append(event)
    for group in sessions.values():
        group.sort(key=lambda e: e.ts)
    return dict(sessions)


def _later_universes(group: list[Event]) -> tuple[list[set[str]], list[set[str]]]:
    """For each position in a session, what every LATER retrieval surfaced/returned.

    Built once per session by scanning backwards, so an eligibility test and an
    outcome lookup are both set membership rather than a rescan.

    Two universes because the choice matters and is worth being able to compare.
    `surfaced` is the ranker's full output and is the primary: it asks whether the
    node came back, full stop. `returned` is what the later retrieval actually
    rendered, which is the exchange's original wording — but a node re-offered and
    then withheld a second time counts as absent there, so it reads recurrence
    through another 0.25 coin.

    Events sharing a timestamp are ordered by the sort's stability rather than by
    anything real; at second resolution on this corpus no session has a tie.
    """
    surfaced_after: list[set[str]] = [set() for _ in group]
    returned_after: list[set[str]] = [set() for _ in group]
    running_surfaced: set[str] = set()
    running_returned: set[str] = set()
    for index in range(len(group) - 1, -1, -1):
        surfaced_after[index] = set(running_surfaced)
        returned_after[index] = set(running_returned)
        running_surfaced |= group[index].surfaced
        running_returned |= group[index].surfaced - group[index].withheld
    return surfaced_after, returned_after


@dataclass(frozen=True)
class _Cell:
    """One eligible event, reduced to what the permutation actually varies.

    Recurrence is a property of the *node* and the session's later retrievals —
    permuting the withheld label does not change whether a node came back, only
    which arm it counts toward. So the flags are computed once and a draw is a
    choice of `k` positions out of `n`, which is what makes 10,000 draws cheap.
    """

    n: int
    k: int
    hits: tuple[int, ...]
    total_hits: int
    withheld_ix: tuple[int, ...]


def _statistic(cells: dict[str, list[_Cell]],
               labels: dict[str, list[tuple[int, ...]]]) -> float:
    """Mean over sessions of (withheld recurrence − kept recurrence).

    The session is the unit because interference is within-session and not across
    it: a withheld node that prompts a clarifying exchange can change what a later
    event in the same conversation offers, but not what another conversation does.
    Sessions are weighted equally rather than by event count — a 92-event session
    and a 2-event one are one cluster each, which is the point of clustering.
    """
    diffs = []
    for sid, group in cells.items():
        w_hits = w_total = k_hits = k_total = 0
        for cell, chosen in zip(group, labels[sid]):
            picked = sum(cell.hits[i] for i in chosen)
            w_hits += picked
            k_hits += cell.total_hits - picked
            w_total += cell.k
            k_total += cell.n - cell.k
        if w_total and k_total:
            diffs.append(w_hits / w_total - k_hits / k_total)
    return sum(diffs) / len(diffs) if diffs else 0.0


def recurrence_report(g, *, scope: str = "main", draws: int = DRAWS,
                      seed: int = SEED) -> Report:
    """The whole measurement, from the graph to a p-value.

    `scope` defaults to `main` — 80% of the corpus, and the population the claim is
    honestly about. Routing is scope-pure (pins are per-session), so pooling across
    scopes mixes task populations that were never exchangeable; pass `scope=""` for
    the pooled exploratory read.
    """
    events, unjoined = load_events(g, scope=scope)
    return analyse(events, scope=scope, draws=draws, seed=seed, unjoined=unjoined)


def analyse(events: list[Event], *, scope: str = "main", draws: int = DRAWS,
            seed: int = SEED, unjoined: int = 0) -> Report:
    """Events to a verdict. Split from the load so it can be driven without a graph."""
    landed_withheld = sum(len(e.withheld) for e in events)
    landed_offered = sum(len(e.offered) for e in events)
    singleton = sum(1 for e in events if len(e.offered) == 1)
    uncontested = sum(1 for e in events if len(e.offered) > 1 and not e.contested)

    sessions = _by_session(events)
    cells: dict[str, list[_Cell]] = defaultdict(list)
    observed_labels: dict[str, list[tuple[int, ...]]] = defaultdict(list)
    eligible_rows: list[tuple[Event, set[str]]] = []
    returned_rows: list[tuple[Event, set[str]]] = []
    terminal = 0
    for sid, group in sessions.items():
        surfaced_after, returned_after = _later_universes(group)
        for index, event in enumerate(group):
            if not event.contested:
                continue
            if not surfaced_after[index]:
                terminal += 1
                continue
            later = surfaced_after[index]
            flags = tuple(int(vid in later) for vid in event.offered)
            withheld_ix = tuple(i for i, vid in enumerate(event.offered)
                                if vid in event.withheld)
            cells[sid].append(_Cell(
                n=len(event.offered), k=len(withheld_ix), hits=flags,
                total_hits=sum(flags), withheld_ix=withheld_ix,
            ))
            observed_labels[sid].append(withheld_ix)
            eligible_rows.append((event, later))
            returned_rows.append((event, returned_after[index]))

    def tally(rows, arm_is_withheld: bool) -> Arm:
        hits = total = 0
        for event, later in rows:
            pool = event.withheld if arm_is_withheld else set(event.kept)
            for vid in pool:
                total += 1
                hits += vid in later
        return Arm(hits, total)

    withheld_arm = tally(eligible_rows, True)
    kept_arm = tally(eligible_rows, False)

    cells = dict(cells)
    observed_labels = dict(observed_labels)
    observed = _statistic(cells, observed_labels)
    differences = {
        sid: _statistic({sid: group}, {sid: observed_labels[sid]})
        for sid, group in cells.items()
    }

    # The conditional randomization distribution, exactly: the draws were iid
    # Bernoulli per offered node, so given the realized count `k` every k-subset of
    # the offered set was equally likely. Sampling k positions uniformly is
    # therefore the real null, not an approximation of it — and conditioning on k
    # also disposes of the never-withhold-everything correction, which only ever
    # removes the k == n outcome that a contested event does not have.
    rng = random.Random(seed)
    extreme = 0
    null_draws: list[float] = []
    positions = {sid: [list(range(cell.n)) for cell in group]
                 for sid, group in cells.items()}
    for _ in range(draws):
        permuted = {
            sid: [tuple(rng.sample(positions[sid][i], group[i].k))
                  for i in range(len(group))]
            for sid, group in cells.items()
        }
        drawn = _statistic(cells, permuted)
        null_draws.append(drawn)
        if abs(drawn) >= abs(observed):
            extreme += 1
    p_value = (extreme + 1) / (draws + 1)
    # A null with no magnitude attached is not a finding. The permutation
    # distribution's own spread is what says how big an effect this design could
    # have caught: at two-sided .05 and 80% power the detectable difference is
    # about (1.96 + 0.84) standard deviations of it (Gelman & Carlin's retrodesign
    # question asked of the exact null rather than of a normal approximation to it).
    mean = sum(null_draws) / len(null_draws) if null_draws else 0.0
    variance = (sum((d - mean) ** 2 for d in null_draws) / (len(null_draws) - 1)
                if len(null_draws) > 1 else 0.0)
    null_sd = variance ** 0.5
    detectable = 2.80 * null_sd

    return Report(
        events=len(events),
        landed_withheld=landed_withheld,
        landed_offered=landed_offered,
        singleton_events=singleton,
        uncontested_events=uncontested,
        terminal_events=terminal,
        eligible_events=len(eligible_rows),
        sessions=len(cells),
        withheld=withheld_arm,
        kept=kept_arm,
        returned_withheld=tally(returned_rows, True),
        returned_kept=tally(returned_rows, False),
        session_differences=differences,
        statistic=observed,
        p_value=p_value,
        p_floor=1 / (draws + 1),
        null_sd=null_sd,
        detectable=detectable,
        draws=draws,
        unjoined_events=unjoined,
        scope=scope or "all (pooled)",
    )
