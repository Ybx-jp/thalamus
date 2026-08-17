"""
Rate-rendering tests.

Interfaces: thalamus.eval.rates — Rate, wilson_interval, widen
Infrastructure: none
Scope: a rate cannot be rendered — or even constructed — without a null and an
interval, or stated reasons for their absence.

Grounding: "50% wasted" left a report as a point estimate over n=5, travelled into
a design doc and a skill, and stayed for weeks before it was withdrawn. The caveat
line added afterwards fixed one call site and left every other rate as renderable
as that one had been. `publish.py` established the shape this enforces: "n/a with a
reason, never dropped".
"""

import pytest

from thalamus.eval.rates import BareRateError, MIN_N, Rate, widen, wilson_interval


def test_a_rate_with_no_null_and_no_reason_cannot_be_built():
    """
    Scenario: Someone adds a new percentage to a report the way the waste figure
    was added

    Verifications:
    - construction fails, so the bare rate never reaches a render path
    - the error says what to supply

    This is the structural half of the fix. A caveat line is editorial and travels
    only as far as the author remembers to write it; a constructor that refuses is
    the same rule applied to every rate that will ever exist.
    """
    with pytest.raises(BareRateError) as exc:
        Rate(label="used", hits=5, total=10, interval=(0.2, 0.8))

    assert "no null" in str(exc.value)
    assert "travelled into docs and a skill" in str(exc.value)


def test_a_rate_with_no_interval_and_no_reason_cannot_be_built():
    """The same refusal on the other axis — bounds, or a reason there are none."""
    with pytest.raises(BareRateError):
        Rate(label="used", hits=5, total=10, null=0.5)


def test_a_reason_is_a_first_class_answer_not_an_escape_hatch():
    """
    Scenario: A rate that genuinely has no null — attribution rate has none, and a
    miss rate's finding turned out to be the stratum rather than the system

    Verifications:
    - the reason satisfies the constructor
    - the reason is rendered next to the number, so it travels with it

    Forcing a null onto a rate that has none would manufacture rigor rather than add
    it. What must not happen is the absence being silent.
    """
    rate = Rate(
        label="attributed", hits=30, total=100,
        null=None, null_reason="attribution has no chance baseline to correct against",
        interval=(0.21, 0.40),
    )

    rendered = rate.render()
    assert "no null — attribution has no chance baseline" in rendered
    assert "(30%)" in rendered


def test_below_the_floor_the_counts_render_and_the_percentage_does_not():
    """
    Scenario: A campaign arm reports 5 of 6

    Verifications:
    - no percentage appears
    - the fraction does
    - the reader is pointed at the exact paired test rather than a percentage

    The cutoff is travel control, not statistics: a fraction resists being quoted out
    of context in a way "83%" does not, and every campaign this project runs is 6-10
    arms. The corpus convention for that regime is the exact paired test, which is
    exact where an interval is approximate.
    """
    rate = Rate(
        label="rung>=3", hits=5, total=6,
        null=None, null_reason="n/a",
        interval=None, interval_reason="n/a",
    )

    rendered = rate.render()
    assert "5/6" in rendered
    assert "%" not in rendered.split("n<")[0]
    assert f"n<{MIN_N}" in rendered
    assert "exact paired test" in rendered


def test_an_empty_denominator_is_n_a_never_zero_percent():
    """
    Scenario: A window with no observations

    0% and "nothing measured" are different claims, and rendering the first for the
    second is how an absence becomes a finding.
    """
    rate = Rate(
        label="used", hits=0, total=0,
        null=None, null_reason="n/a", interval=None, interval_reason="n/a",
    )

    assert rate.render() == "used: n/a — no observations"
    assert rate.value is None


def test_a_complete_rate_renders_its_number_with_both_instruments():
    """
    Scenario: A rate that has everything

    Verifications:
    - percentage, interval and null all render
    - the null verdict states which side of chance the figure falls on

    "60% used" and "no signal" are the same number when the judge calls ~59% of
    unrelated tokens used, so the side of the null is the part that carries meaning.
    """
    rate = Rate(
        label="used", hits=66, total=100,
        null=0.59, interval=(0.56, 0.75),
    )

    rendered = rate.render()
    assert "66/100 (66%)" in rendered
    assert "95% CI [56%, 75%]" in rendered
    assert "null 59% (above chance)" in rendered


def test_a_rate_at_or_below_its_null_says_so():
    """A figure below chance must not read as a finding."""
    rate = Rate(label="wasted", hits=31, total=100, null=0.41, interval=(0.22, 0.41))

    assert "at or below chance" in rate.render()


def test_the_design_effect_widens_an_interval_rather_than_a_footnote_mentioning_it():
    """
    Scenario: Verdicts cluster in sessions (waste.py measured ICC ~0.26, design
    effect ~4)

    Verifications:
    - the widened interval is centred where the original was
    - it is wider by sqrt(design effect)
    - a design effect of 1 or less is a no-op

    An interval assuming independence is not conservative here; it is wrong in the
    direction that makes a finding look stronger. So the correction goes into the
    number, not into prose beside it.
    """
    base = (0.4, 0.6)
    wide = widen(base, 4.0)

    assert sum(wide) / 2 == pytest.approx(0.5)
    assert (wide[1] - wide[0]) == pytest.approx((base[1] - base[0]) * 2)
    assert widen(base, 1.0) == base


def test_wilson_holds_at_the_extremes_a_small_sample_produces():
    """
    Scenario: 0 of 8 and 8 of 8 — the shapes a 40-label hand sample reaches

    The normal approximation gives a zero-width interval at p=0 and p=1, which reads
    as certainty from eight observations.
    """
    lo, hi = wilson_interval(0, 8)
    assert lo == 0.0 and 0.0 < hi < 0.5

    lo, hi = wilson_interval(8, 8)
    assert hi == 1.0 and 0.5 < lo < 1.0

    # Verifies: an empty sample admits everything rather than dividing by zero
    assert wilson_interval(0, 0) == (0.0, 1.0)
