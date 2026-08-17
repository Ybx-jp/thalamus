"""Confidence sequences — intervals that survive being looked at.

This project has a first-party demonstration of why it needs these. An earlier
campaign was peeked at: P(on>off) read 0.789 with exact p = 0.0154 at 19 arms, decayed
to 0.693 (p = 0.0589) by 23, and finished at 0.667 (p = 0.0849). Nothing went wrong
with the data. The error was reading a fixed-n interval at a moment chosen *because*
it looked interesting, which is not a coverage guarantee at all.

A confidence sequence is an interval valid at **every** t simultaneously: it may be
inspected continuously, and a campaign may stop the moment it excludes the null,
without spending the false-positive rate that repeated fixed-n testing does. The
practical payoff is budget — a run that has already answered its question can stop
rather than burning the pre-registered n.

The boundary here is Robbins' normal-mixture, the standard sub-Gaussian construction:

    radius(t) = σ · √( 2(tρ + 1) / (t²ρ) · log( √(tρ + 1) / α ) )

with σ = 1/2, which bounds any observation in [0, 1] (Hoeffding). `rho` sets where
the boundary is tightest — the sample size the design is *optimised* for, not a cap.
Being explicit about that is the point: the tuning is a pre-registered choice, and a
sequence retuned after seeing the data is a fixed-n test wearing a disguise.

Deliberately not implemented: a betting-style sequence, which is tighter. It needs a
wealth process and a bet schedule, both of which are choices this project would then
have to defend without the literature held to defend them. The mixture boundary is
looser and citable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Any observation in [0, 1] is (1/2)-sub-Gaussian.
SUB_GAUSSIAN_SIGMA = 0.5


@dataclass(frozen=True)
class SequenceState:
    """The interval as of observation t, and what it licenses."""

    n: int
    mean: float
    radius: float
    alpha: float
    rho: float

    @property
    def interval(self) -> tuple[float, float]:
        return (self.mean - self.radius, self.mean + self.radius)

    def excludes(self, null: float) -> bool:
        lo, hi = self.interval
        return null < lo or null > hi

    def within(self, null: float, margin: float) -> bool:
        """Is the whole interval inside a region of practical equivalence?

        The futility half of a stopping rule. Without it a sequence can only ever
        say "not yet" — and "the effect, if any, is smaller than we care about" is a
        result worth stopping for, not a failure to find one.
        """
        lo, hi = self.interval
        return null - margin <= lo and hi <= null + margin


def radius(n: int, *, alpha: float = 0.05, rho: float = 0.05, sigma: float = SUB_GAUSSIAN_SIGMA) -> float:
    """Robbins' normal-mixture boundary at time n. Infinite before any data."""
    if n <= 0:
        return float("inf")
    inner = (n * rho + 1) / (n * n * rho)
    return sigma * math.sqrt(2 * inner * math.log(math.sqrt(n * rho + 1) / alpha))


def track(
    observations: list[float], *, alpha: float = 0.05, rho: float = 0.05
) -> list[SequenceState]:
    """The whole sequence, one state per observation.

    Returned in full rather than as a final answer because the *path* is the
    artifact: a published campaign should show where its interval was when it
    stopped, and that it did not stop the one time it looked good.
    """
    states = []
    running = 0.0
    for index, value in enumerate(observations, start=1):
        running += value
        states.append(
            SequenceState(
                n=index,
                mean=running / index,
                radius=radius(index, alpha=alpha, rho=rho),
                alpha=alpha,
                rho=rho,
            )
        )
    return states


def paired_differences(treated: list[float], control: list[float]) -> list[float]:
    """Per-unit differences rescaled into [0, 1] so the boundary applies.

    A difference of two [0, 1] outcomes lives in [-1, 1]; (d + 1) / 2 maps it back,
    and a null of "no difference" becomes 0.5. Rescaling rather than doubling sigma
    keeps one boundary in the codebase instead of two that must agree.
    """
    return [(t - c + 1) / 2 for t, c in zip(treated, control, strict=True)]


NO_DIFFERENCE = 0.5


def decide(
    state: SequenceState, *, null: float, margin: float = 0.0, horizon: int | None = None
) -> str:
    """`effect`, `futile`, `horizon`, or `continue` — the pre-registered stopping rule.

    Order matters: an effect that also sits inside the equivalence margin is an
    effect too small to act on, so futility is checked first when a margin is set.
    """
    if margin and state.within(null, margin):
        return "futile"
    if state.excludes(null):
        return "effect"
    if horizon is not None and state.n >= horizon:
        return "horizon"
    return "continue"


def render(states: list[SequenceState], *, null: float, label: str = "effect") -> str:
    """A compact trace of the sequence, for a lab entry or an experiment page."""
    if not states:
        return "no observations"
    lines = [f"{label}: {len(states)} observation(s), null {null:g}"]
    marks = {1, len(states)} | {s.n for s in states if s.excludes(null)}
    for state in states:
        if state.n not in marks and state.n % max(1, len(states) // 8) != 0:
            continue
        lo, hi = state.interval
        flag = " ← excludes the null" if state.excludes(null) else ""
        lines.append(f"  n={state.n:<4} mean {state.mean:.3f}  [{lo:.3f}, {hi:.3f}]{flag}")
    return "\n".join(lines)
