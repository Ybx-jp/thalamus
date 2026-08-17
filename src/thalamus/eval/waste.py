"""Token waste, with the interval it needs and the correction it needs more.

`eval report` prints "33% wasted". Two things are wrong with quoting that number.

**It has no interval, and the obvious interval is too narrow.** Verdicts inside one
session share an output window, a topic and an operator, so they are not independent
draws. The primary sampling unit is the *session*: measured ICC ≈ 0.26 with a design
effect near 4 on this corpus, which makes a verdict-level interval about half the
width it should be. The estimator here is a ratio of totals with sessions as PSUs and
a delete-one-session jackknife.

**And sampling error is the smaller problem.** The estimand is defined by a `used`
flag whose chance level is ~57%. Correcting for that gives a very
different sentence: not "a third of injected tokens are wasted" but "at most about a
tenth of injected tokens are *demonstrably earned*, and the rest is not distinguishable
from topic overlap". Both are reported, because the uncorrected figure is the one the
tooling has been printing and the corrected one is what it means.

The per-node price is `injected_chars // returned_count`: the graph records the size
of the whole render, not of each node in it, so a 40-token thread and a 400-token claim
in the same retrieval are priced identically. That is a known defect of the denominator
and is reported as a bias direction rather than silently inherited.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

CHARS_PER_TOKEN = 4


@dataclass
class SessionTotals:
    session_id: str
    injected: float = 0.0
    wasted: float = 0.0
    earned: float = 0.0
    traces: int = 0
    verdicts: int = 0


@dataclass
class WasteEstimate:
    ratio: float
    se: float
    ci: tuple[float, float]
    sessions: int
    traces: int
    verdicts: int
    injected_tokens: float
    wasted_tokens: float
    icc: float
    design_effect: float
    naive_se: float
    per_session: list[SessionTotals] = field(default_factory=list)

    @property
    def half_width(self) -> float:
        return (self.ci[1] - self.ci[0]) / 2

    def sessions_needed(self, target_half_width: float) -> int:
        """Sessions required for a target ±half-width, at this variance.

        Scales as 1/√n from the measured jackknife SE, so it inherits every
        assumption in it — most importantly that future sessions look like these.
        The frame is a census of the tap, so this is a superpopulation statement
        about sessions the operator has not had yet, not a design-based one.
        """
        if self.se <= 0 or target_half_width <= 0:
            return 0
        target_se = target_half_width / 1.96
        return max(1, math.ceil(self.sessions * (self.se / target_se) ** 2))


def per_session_totals(cases, verdicts: dict[str, dict[str, bool]]) -> list[SessionTotals]:
    """Injected / earned / wasted tokens per session, from the per-node share."""
    totals: dict[str, SessionTotals] = {}
    for case in cases:
        row = totals.setdefault(case.session_id, SessionTotals(session_id=case.session_id))
        judged = verdicts.get(case.trace_id, {})
        if not judged:
            continue
        share = (case.injected_chars / case.returned_count) if case.returned_count else 0.0
        row.traces += 1
        for _node_id, used in judged.items():
            row.verdicts += 1
            row.injected += share / CHARS_PER_TOKEN
            if used:
                row.earned += share / CHARS_PER_TOKEN
            else:
                row.wasted += share / CHARS_PER_TOKEN
    return sorted(totals.values(), key=lambda r: -r.wasted)


def estimate(cases, verdicts: dict[str, dict[str, bool]]) -> WasteEstimate:
    """Ratio-of-totals waste with a delete-one-session jackknife interval."""
    rows = per_session_totals(cases, verdicts)
    injected = sum(r.injected for r in rows)
    wasted = sum(r.wasted for r in rows)
    ratio = wasted / injected if injected else 0.0
    n = len(rows)

    if n < 2 or injected <= 0:
        return WasteEstimate(
            ratio=ratio, se=0.0, ci=(0.0, 1.0), sessions=n,
            traces=sum(r.traces for r in rows), verdicts=sum(r.verdicts for r in rows),
            injected_tokens=injected, wasted_tokens=wasted, icc=0.0, design_effect=1.0,
            naive_se=0.0, per_session=rows,
        )

    # Delete-one-session jackknife: each pseudo-value is the ratio with one PSU
    # removed, so the spread across sessions — not across verdicts — sets the SE.
    pseudo = []
    for row in rows:
        rest_w = wasted - row.wasted
        rest_i = injected - row.injected
        if rest_i > 0:
            pseudo.append(rest_w / rest_i)
    mean = sum(pseudo) / len(pseudo)
    se = math.sqrt((n - 1) / n * sum((p - mean) ** 2 for p in pseudo))

    icc, deff, naive = _clustering(cases, verdicts, rows)
    return WasteEstimate(
        ratio=ratio,
        se=se,
        ci=(max(0.0, ratio - 1.96 * se), min(1.0, ratio + 1.96 * se)),
        sessions=n,
        traces=sum(r.traces for r in rows),
        verdicts=sum(r.verdicts for r in rows),
        injected_tokens=injected,
        wasted_tokens=wasted,
        icc=icc,
        design_effect=deff,
        naive_se=naive,
        per_session=rows,
    )


def _clustering(cases, verdicts, rows) -> tuple[float, float, float]:
    """ICC of per-trace waste within session, the design effect, and the naive SE.

    Reported so the difference between the honest interval and the tempting one is
    a number on the page rather than a methodological assertion.
    """
    by_session: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        judged = verdicts.get(case.trace_id, {})
        if not judged:
            continue
        share = (case.injected_chars / case.returned_count) if case.returned_count else 0.0
        by_session[case.session_id].append(
            sum(share / CHARS_PER_TOKEN for used in judged.values() if not used)
        )

    values = [v for group in by_session.values() for v in group]
    if len(values) < 2 or len(by_session) < 2:
        return 0.0, 1.0, 0.0
    grand = sum(values) / len(values)
    k = len(by_session)
    between = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in by_session.values()) / (k - 1)
    within_df = len(values) - k
    within = (
        sum((v - sum(g) / len(g)) ** 2 for g in by_session.values() for v in g) / within_df
        if within_df > 0
        else 0.0
    )
    sizes = [len(g) for g in by_session.values()]
    m0 = (sum(sizes) - sum(s * s for s in sizes) / sum(sizes)) / (k - 1)
    icc = (between - within) / (between + (m0 - 1) * within) if (between + (m0 - 1) * within) else 0.0
    icc = max(0.0, min(1.0, icc))
    mean_size = sum(sizes) / k
    deff = 1 + (mean_size - 1) * icc

    # The interval someone would get by treating every verdict as an independent
    # draw: a binomial SE on the waste share. It is the wrong estimator — that is
    # the point of printing it — so it must be the *narrow* one, and if it ever
    # comes out wider than the clustered SE the clustering calculation is broken,
    # not the data.
    n_verdicts = sum(r.verdicts for r in rows)
    total_injected = sum(r.injected for r in rows)
    share = (sum(r.wasted for r in rows) / total_injected) if total_injected else 0.0
    naive = math.sqrt(share * (1 - share) / n_verdicts) if n_verdicts else 0.0
    return icc, deff, naive


def chance_corrected(rate_used: float, null_used: float) -> float:
    """Share of injected tokens that is *not* demonstrably earned.

    1 − κ, where κ = (p − p̄₀)/(1 − p̄₀). The uncorrected waste figure counts every
    node the judge called used as earned, and the judge calls ~57% of *unrelated*
    nodes used. This is the same arithmetic applied to the token-weighted rate.
    """
    headroom = 1.0 - null_used
    if headroom <= 1e-9:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (rate_used - null_used) / headroom))


def token_weighted_rate(cases, verdicts: dict[str, dict[str, bool]]) -> float:
    """The used-rate weighted by injected tokens rather than by node count."""
    used = total = 0.0
    for case in cases:
        judged = verdicts.get(case.trace_id, {})
        share = (case.injected_chars / case.returned_count) if case.returned_count else 0.0
        for _node_id, is_used in judged.items():
            total += share
            if is_used:
                used += share
    return used / total if total else 0.0


def token_weighted_null(cases, null_by_case: dict[str, list[int]]) -> float:
    """The permuted null, weighted by injected tokens rather than node count.

    The correction has to be applied on the same scale as the estimand: a
    token-weighted waste figure corrected by a node-weighted null would be mixing
    two denominators, and the nodes that dominate the token budget are not the ones
    that dominate the count.
    """
    used = total = 0.0
    for case in cases:
        counts = null_by_case.get(case.trace_id)
        if not counts:
            continue
        share = (case.injected_chars / case.returned_count) if case.returned_count else 0.0
        used += share * counts[0]
        total += share * counts[1]
    return used / total if total else 0.0
