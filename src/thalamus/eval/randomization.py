"""Randomization inference over clusters — the test that survives having few of them.

The anchored problem ([docs/11](../../../docs/11-related-work.md), feed
`cluster-inference`): with one or a few *treated clusters*, cluster-robust t- and Wald
tests over-reject severely, cluster-robust standard errors are biased **downward**, and
the wild cluster bootstrap — normally the fix — fails in the same corner. The held
recommendation is randomization inference, which "can sometimes yield reliable results
even when the number of clusters is small and/or the number of treated clusters is
small" (`scope:eval-methodology:claim:f78faf28b3f82a65`).

RI tests the **sharp null of no treatment effect** — not "no effect on average", but
"no effect on any unit". Under that null every cluster's outcome is the number it would
have shown under either assignment, so the treatment labels are arbitrary: re-deal
them, recompute the statistic, and the observed value's rank in that distribution *is*
the p-value. No standard error is estimated, which is exactly why nothing here inherits
the downward bias that breaks the alternatives.

**The thing this module exists to say out loud.** The reference distribution has one
entry per possible assignment, so an exact p-value cannot be smaller than
`1 / n_assignments`. With few clusters that is a hard floor no effect size and no
amount of within-room data can lower:

    3 rooms, 1 treated  →   3 assignments → smallest possible p = 0.333
    6 rooms, 3 treated  →  20 assignments → smallest possible p = 0.100
    8 rooms, 4 treated  →  70 assignments → smallest possible p = 0.029

So **seven rooms split 3/4 is the smallest campaign that can produce p ≤ 0.05 at all**
(eight, if the split is even), and a perfectly clean six-room separation still reads
p = 0.10. That is arithmetic from the definition above, not a further empirical claim —
and it is a question to settle before spending anything, which is what `feasible()` is
for.

**Scope of the guarantee.** An RI p-value is exact at *one* look. Recomputing it as
each room lands is the peeking failure lab/023 demonstrated first-hand. Anytime-valid
monitoring comes from `sequential.py`'s confidence sequence, and the two are reported
side by side rather than merged: a sequential *randomization* test is a real
construction this project does not hold the literature for, and combining them here
would be inventing a guarantee rather than citing one.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Sequence

# Enumerate the assignment space exactly up to this many; sample beyond it. Exactness
# is preferable and cheap in the regime this module is for — the few-cluster corner is
# precisely where the space is small.
EXACT_LIMIT = 200_000

Statistic = Callable[[Sequence[float], Sequence[float]], float]


def difference_in_means(treated: Sequence[float], control: Sequence[float]) -> float:
    """The default statistic. Signed, so the test is two-sided by default.

    docs/04 requires a signed two-sided outcome: a metric that can only count wins
    cannot observe harms, and correlated error inside a room is the most plausible way
    a room makes things worse.
    """
    if not treated or not control:
        return 0.0
    return sum(treated) / len(treated) - sum(control) / len(control)


def n_assignments(n_clusters: int, n_treated: int) -> int:
    """How many ways the treatment could have been dealt."""
    if n_clusters < 0 or not 0 <= n_treated <= n_clusters:
        return 0
    return math.comb(n_clusters, n_treated)


def min_attainable_p(n_clusters: int, n_treated: int, *, draws: int | None = None) -> float:
    """The smallest **two-sided** p-value this design can produce, before any data.

    Not simply `1 / n_assignments`. A two-sided test counts assignments whose statistic
    is at least as extreme *in absolute value*, and in a **balanced** design every
    assignment's complement is also an assignment, producing the negated
    difference-in-means. The most extreme value therefore always arrives as a ± pair
    and the floor is `2 / n_assignments`.

    Unbalanced designs have no complement inside the space (the complement of a
    2-of-7 split is a 5-of-7 split, which is not a candidate assignment), so their
    floor stays at `1 / n_assignments`. That makes an unbalanced design's *floor*
    lower than a balanced one's at the same cluster count — a fact about the
    arithmetic, not a recommendation, since balance is what buys power once the floor
    is cleared.
    """
    total = n_assignments(n_clusters, n_treated)
    if total <= 0:
        return 1.0
    if draws is not None and total > EXACT_LIMIT:
        return min(1.0, 2.0 / (draws + 1))
    balanced = n_treated * 2 == n_clusters
    return min(1.0, (2.0 if balanced else 1.0) / total)


@dataclass(frozen=True)
class Feasibility:
    """Whether a campaign shape can reject at all, answered before it is run."""

    n_clusters: int
    n_treated: int
    alpha: float
    assignments: int
    floor: float
    """Smallest attainable p-value. Compare against alpha, not against a hoped effect."""

    @property
    def possible(self) -> bool:
        return self.floor <= self.alpha

    def note(self) -> str:
        shape = f"{self.n_clusters} cluster(s), {self.n_treated} treated"
        if self.assignments <= 0:
            return f"{shape}: not a design — no valid assignment"
        if self.possible:
            return (
                f"{shape}: {self.assignments} assignment(s), smallest attainable "
                f"p = {self.floor:.3f} ≤ α = {self.alpha:g} — can reject if the effect is there"
            )
        return (
            f"{shape}: {self.assignments} assignment(s), smallest attainable "
            f"p = {self.floor:.3f} > α = {self.alpha:g} — CANNOT REJECT AT ANY EFFECT SIZE; "
            "add clusters or balance the allocation, no amount of within-cluster data helps"
        )


def feasible(n_clusters: int, n_treated: int, *, alpha: float = 0.05) -> Feasibility:
    """Can this many clusters, split this way, ever produce a significant result?

    Worth running before a campaign rather than after: the answer depends only on the
    design, so a shape that cannot reject is knowable while it is still free to change.
    """
    total = n_assignments(n_clusters, n_treated)
    return Feasibility(
        n_clusters=n_clusters,
        n_treated=n_treated,
        alpha=alpha,
        assignments=total,
        floor=min_attainable_p(n_clusters, n_treated),
    )


def smallest_design(*, alpha: float = 0.05, limit: int = 64) -> tuple[int, int]:
    """Fewest clusters, and the split, whose floor clears `alpha`. `(0, 0)` if none.

    Reported so a campaign's minimum size is a number rather than an intuition. The
    winning split is often *odd* — at α = 0.05 the answer is 7 clusters split 3/4,
    which beats 8 split 4/4 only because an unbalanced space has no complement and so
    no ± pair at the extreme. Balance still buys power above the floor, so this is the
    smallest design that can reject, not the best design of that size.
    """
    for total in range(2, limit + 1):
        clearing = [t for t in range(1, total) if min_attainable_p(total, t) <= alpha]
        if clearing:
            # Among splits that clear the floor, the most balanced one — the floor is
            # a necessary condition and balance is what buys power once it is met, so
            # returning the first split found would recommend the weakest of them.
            return (total, min(clearing, key=lambda t: (abs(t * 2 - total), t)))
    return (0, 0)


@dataclass(frozen=True)
class RandomizationTest:
    """One look: the observed statistic against its re-randomization distribution."""

    observed: float
    p_value: float
    assignments: int
    exact: bool
    """True when every assignment was enumerated; False when the space was sampled."""

    floor: float
    n_clusters: int
    n_treated: int

    @property
    def at_floor(self) -> bool:
        """Whether the p-value is the smallest the design could have produced.

        Worth flagging: a p-value sitting exactly on the floor means the observed
        assignment was the most extreme one available, which is as much signal as the
        design can carry — and it is *not* evidence that a larger effect would have
        produced a smaller number.
        """
        return self.p_value <= self.floor + 1e-12

    def note(self) -> str:
        how = "exact" if self.exact else f"sampled ({self.assignments} draws)"
        line = (
            f"randomization inference: statistic {self.observed:+.4f}, "
            f"p = {self.p_value:.4f} ({how}, {self.n_clusters} clusters, "
            f"{self.n_treated} treated)"
        )
        if self.at_floor:
            line += f" — at the design floor of {self.floor:.3f}; no shape-preserving effect reads lower"
        return line


def randomization_test(
    outcomes: Sequence[float],
    treated: Sequence[bool],
    *,
    statistic: Statistic = difference_in_means,
    draws: int = 10_000,
    seed: int = 20260809,
) -> RandomizationTest:
    """Two-sided RI p-value for a cluster-level outcome vector.

    One entry per **cluster**, never per session: the whole reason for this module is
    that the cluster is the unit the treatment was assigned to, and feeding it sessions
    would reintroduce the inflated n that cluster-robust methods exist to correct.

    The observed assignment is counted in both numerator and denominator, which is what
    makes the p-value exact rather than merely unbiased — and what puts the floor at
    `1 / n_assignments` instead of 0.
    """
    values = list(outcomes)
    flags = list(treated)
    if len(values) != len(flags):
        raise ValueError("outcomes and treated must describe the same clusters")

    total_clusters = len(values)
    treated_count = sum(1 for flag in flags if flag)
    space = n_assignments(total_clusters, treated_count)
    floor = min_attainable_p(total_clusters, treated_count)

    if total_clusters == 0 or treated_count in (0, total_clusters):
        # No contrast exists: every cluster is on the same side.
        return RandomizationTest(
            observed=0.0, p_value=1.0, assignments=max(space, 0), exact=True,
            floor=1.0, n_clusters=total_clusters, n_treated=treated_count,
        )

    def stat_for(indices: frozenset[int]) -> float:
        arm = [values[i] for i in range(total_clusters) if i in indices]
        rest = [values[i] for i in range(total_clusters) if i not in indices]
        return statistic(arm, rest)

    observed_indices = frozenset(i for i, flag in enumerate(flags) if flag)
    observed = stat_for(observed_indices)

    exact = space <= EXACT_LIMIT
    if exact:
        reference = [
            stat_for(frozenset(combo))
            for combo in combinations(range(total_clusters), treated_count)
        ]
    else:
        rng = random.Random(seed)
        indices = list(range(total_clusters))
        reference = [observed]
        for _ in range(draws):
            rng.shuffle(indices)
            reference.append(stat_for(frozenset(indices[:treated_count])))
        floor = 1.0 / (draws + 1)

    extreme = sum(1 for value in reference if abs(value) >= abs(observed) - 1e-12)
    return RandomizationTest(
        observed=observed,
        p_value=extreme / len(reference),
        assignments=len(reference),
        exact=exact,
        floor=floor,
        n_clusters=total_clusters,
        n_treated=treated_count,
    )


def monitor(
    outcomes: Sequence[float],
    treated: Sequence[bool],
    *,
    paired: bool = False,
    alpha: float = 0.05,
    rho: float = 0.05,
) -> str:
    """Anytime-valid monitoring of the same cluster-level outcomes, via `sequential`.

    This is the half that may be looked at repeatedly. The RI p-value above is exact at
    one look and inflates if recomputed as rooms land; the confidence sequence is valid
    at every t simultaneously, so it is what a campaign actually watches.

    Two shapes, because a room design is usually not paired:

    - `paired=True` — each cluster contributes a treated and a control observation (the
      same task run both ways). Differences rescale into [0, 1] and the null is 0.5.
    - `paired=False` — clusters are either treated or not, so there is no difference to
      take per cluster. Each arm gets its own sequence and both intervals are shown.
      **Non-overlap is a conservative signal, not a test of the difference**: two
      intervals can overlap while the difference still excludes zero, so this direction
      of error costs power and never buys false confidence.

    Observations must already lie in [0, 1] — the Robbins boundary here is built on
    that bound (`sequential.SUB_GAUSSIAN_SIGMA`), and feeding it an unbounded outcome
    would silently violate the sub-Gaussian assumption the radius rests on.
    """
    from thalamus.eval import sequential

    arm = [value for value, flag in zip(outcomes, treated, strict=True) if flag]
    rest = [value for value, flag in zip(outcomes, treated, strict=True) if not flag]
    if not arm or not rest:
        return "no contrast — every cluster is on one side"

    if paired:
        if len(arm) != len(rest):
            return "paired monitoring needs one treated and one control observation per cluster"
        states = sequential.track(
            sequential.paired_differences(arm, rest), alpha=alpha, rho=rho
        )
        return sequential.render(states, null=sequential.NO_DIFFERENCE, label="paired difference")

    treated_states = sequential.track(arm, alpha=alpha, rho=rho)
    control_states = sequential.track(rest, alpha=alpha, rho=rho)
    lo_t, hi_t = treated_states[-1].interval
    lo_c, hi_c = control_states[-1].interval
    separated = hi_t < lo_c or hi_c < lo_t
    return "\n".join([
        f"treated  n={treated_states[-1].n:<3} mean {treated_states[-1].mean:.3f}  [{lo_t:.3f}, {hi_t:.3f}]",
        f"control  n={control_states[-1].n:<3} mean {control_states[-1].mean:.3f}  [{lo_c:.3f}, {hi_c:.3f}]",
        (
            "intervals are disjoint — conservative evidence of a difference"
            if separated
            else "intervals overlap — no conclusion, and overlap is weaker evidence "
            "against an effect than a direct interval on the difference would be"
        ),
    ])


def render(
    test: RandomizationTest, feasibility: Feasibility | None = None, sequence: str = ""
) -> str:
    """The pair, reported together and never merged.

    The confidence sequence carries the anytime-valid guarantee; the RI p-value carries
    exactness at one look. Presenting a single number would imply a joint guarantee
    neither one gives.
    """
    lines = []
    if feasibility is not None:
        lines.append(f"  design: {feasibility.note()}")
    lines.append(f"  {test.note()}")
    if sequence:
        lines.append("  anytime-valid monitoring (exact at every look, unlike the p-value above):")
        lines.extend(f"    {line}" for line in sequence.splitlines())
    return "\n".join(lines)
