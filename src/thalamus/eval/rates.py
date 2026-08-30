"""A rate you cannot render bare.

The figure "50% wasted" left a report as a point estimate on n=5, travelled into
a design doc and a skill, and stayed there for weeks before it was withdrawn. The
caveat line added afterwards fixed one call site and left every other rate
renderable exactly the way that one had been.

So the fix is structural rather than editorial: a `Rate` cannot be *constructed*
without saying what its null is and what its interval is — or, when the statistic
genuinely does not exist for that rate, saying so in words that then travel with
the number. Forcing a null onto a rate that has none would manufacture rigor
instead of adding it, which is why a reason is a first-class answer and not an
escape hatch. The established shape is "n/a **with a reason**, never dropped".

Two refusals are built in:

- Below `MIN_N` the percentage is suppressed and the counts render instead. The
  cutoff is travel control, not statistics — a fraction resists being quoted out
  of context in a way "50%" does not. Nothing measured says 20 is the right
  number; it is above every campaign size this project runs (6-10 arms), which
  is deliberate: campaign rates should be read as counts and tested with the
  exact paired test the corpus already uses, not as
  percentages.
- A zero denominator renders "n/a", never 0%.

Falsifier for the floor, not run: nobody has measured whether readers actually
quote fractions less often than percentages.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Below this, render the counts and refuse the percentage. See the module docstring
# — this is a convention about how numbers travel, not a statistical threshold.
MIN_N = 20


def wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — behaves at the small n and extreme p a 40-label
    sample can produce, where the normal approximation does not."""
    if total == 0:
        return (0.0, 1.0)
    p = hits / total
    d = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def percentile_ci(values: list[float], alpha: float = 0.05) -> tuple[float, float]:
    """Empirical percentile interval over bootstrap draws."""
    if not values:
        return (0.0, 1.0)
    ordered = sorted(values)
    lo = ordered[max(0, int(len(ordered) * alpha / 2) - 1)]
    hi = ordered[min(len(ordered) - 1, int(len(ordered) * (1 - alpha / 2)))]
    return (lo, hi)

def session_bootstrap(
    groups: Mapping[str, Sequence[tuple[int, int]]],
    *,
    draws: int = 2000,
    seed: int = 20260730,
) -> tuple[float, float] | None:
    """Resample **sessions**, not verdicts, for a clustered rate's interval.

    Verdicts inside one session are not independent draws: they share an output
    window, a topic and an operator. Resampling the sessions is the correction; a
    scalar design effect applied to an independence-assuming interval is an
    approximation of this, and it was applied here at a cluster size it was never
    measured for — the ICC was estimated over retrievals per session and the rate
    it widened is counted over returned nodes, which cluster harder.

    `groups` maps a session to its (hits, total) pairs. Returns None when there are
    fewer than two sessions, because an interval over one cluster is not one.
    """
    if len(groups) < 2:
        return None
    rng = random.Random(seed)
    sessions = list(groups)
    rates = []
    for _ in range(draws):
        hits = total = 0
        for _ in sessions:
            for h, t in groups[sessions[rng.randrange(len(sessions))]]:
                hits += h
                total += t
        if total:
            rates.append(hits / total)
    return percentile_ci(rates) if rates else None


class BareRateError(ValueError):
    """Raised when a rate is built with neither a statistic nor a reason for its absence."""


@dataclass(frozen=True)
class Rate:
    """A proportion together with what is needed to read it.

    `null` is the rate a system with no signal would produce — the judge calls ~59%
    of *unrelated* tokens used, so "60% used" and "no signal" are the same number.
    `interval` bounds sampling error. Either may be `None`, but only with a reason:
    the four rates this project reports are four different shapes and some have no
    meaningful null at all (attribution rate has none, and a miss rate's finding was
    the stratum rather than the system).
    """

    label: str
    hits: float
    total: float
    null: float | None = None
    null_reason: str = ""
    interval: tuple[float, float] | None = None
    interval_reason: str = ""
    # Stated limits that travel with the number rather than living in a comment.
    note: str = ""
    unit: str = ""
    floor: int = MIN_N

    def __post_init__(self) -> None:
        if self.null is None and not self.null_reason.strip():
            raise BareRateError(
                f"rate `{self.label}` has no null and no reason for not having one. "
                "Give a null model, or say in words why this rate has none — a bare "
                "percentage is what travelled into docs and a skill."
            )
        if self.interval is None and not self.interval_reason.strip():
            raise BareRateError(
                f"rate `{self.label}` has no interval and no reason for not having "
                "one. Give bounds, or say why they are unavailable."
            )

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    def render(self) -> str:
        """One line, self-describing. Never a naked percentage."""
        unit = f" {self.unit}" if self.unit else ""
        counts = f"{self.hits:,.0f}/{self.total:,.0f}{unit}"
        value = self.value
        if value is None:
            return f"{self.label}: n/a — no observations"
        if self.total < self.floor:
            return (
                f"{self.label}: {counts} — no rate rendered (n<{self.floor}); "
                "read the counts, and test with the exact paired test rather than "
                "quoting a percentage"
            )

        parts = [f"{self.label}: {counts} ({100.0 * value:.0f}%)"]
        if self.interval is not None:
            lo, hi = self.interval
            parts.append(f"95% CI [{100 * lo:.0f}%, {100 * hi:.0f}%]")
        else:
            parts.append(f"no interval — {self.interval_reason}")
        if self.null is not None:
            verdict = "above" if value > self.null else "at or below"
            parts.append(f"null {100 * self.null:.0f}% ({verdict} chance)")
        else:
            parts.append(f"no null — {self.null_reason}")
        line = "; ".join(parts)
        return f"{line}\n    ^ {self.note}" if self.note else line
