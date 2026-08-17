"""Confidence-sequence tests.

Interfaces: thalamus.eval.sequential — the mixture boundary, the stopping rule.
Infrastructure: synthetic observation streams; no graph.
Scope: the coverage property that makes a sequence worth having — that it may be
       inspected at every t — and the peeking failure it exists to prevent.
"""

import random

from thalamus.eval import sequential as seq


def test_the_interval_narrows_and_stays_valid_at_every_t():
    """A fixed-n interval is valid at the n you chose in advance. This one is valid
    whenever you look, which is the whole reason to pay for its extra width."""
    states = seq.track([0.5] * 200)
    assert states[0].radius > states[-1].radius
    assert all(s.radius > 0 for s in states)
    # Monotone narrowing: no moment where waiting made the interval worse.
    assert all(a.radius >= b.radius for a, b in zip(states, states[1:]))


def test_a_true_null_is_not_excluded_by_peeking_at_every_step():
    """
    Scenario: the measured failure, simulated. A campaign with no effect is inspected
    after every single observation, and the analyst stops the first time the
    interval excludes the null.

    Verification: across many such campaigns, that almost never happens. Repeated
    fixed-n testing would fire constantly — that is exactly how P(on>off)=0.789 with
    p=0.0154 at 19 arms decayed to p=0.0849 by 24.
    """
    rng = random.Random(20260730)
    false_alarms = 0
    trials = 200
    for _ in range(trials):
        observations = [rng.random() for _ in range(80)]  # mean 0.5, no effect
        if any(state.excludes(0.5) for state in seq.track(observations)):
            false_alarms += 1
    # alpha = 0.05 over the whole path, not per look.
    assert false_alarms <= trials * 0.05


def test_a_real_effect_is_caught_and_the_campaign_can_stop_early():
    observations = [0.9] * 60
    states = seq.track(observations)
    firing = next((s for s in states if s.excludes(0.5)), None)
    assert firing is not None
    assert firing.n < len(observations), "stopping early is the point"


def test_futility_is_a_result_not_a_failure_to_find_one():
    """Without an equivalence margin a sequence can only ever say "not yet". "The
    effect is smaller than we care about" is worth stopping for."""
    states = seq.track([0.5] * 400)
    final = states[-1]
    assert seq.decide(final, null=0.5, margin=0.15) == "futile"
    assert seq.decide(final, null=0.5, margin=0.0) == "continue"
    assert seq.decide(final, null=0.5, margin=0.0, horizon=len(states)) == "horizon"


def test_paired_differences_map_onto_the_same_boundary():
    """One boundary in the codebase rather than two that have to agree."""
    treated, control = [1.0] * 40, [0.0] * 40
    differences = seq.paired_differences(treated, control)
    assert differences == [1.0] * 40
    states = seq.track(differences)
    assert states[-1].excludes(seq.NO_DIFFERENCE)

    no_effect = seq.paired_differences([0.4] * 40, [0.4] * 40)
    assert no_effect == [0.5] * 40
    assert not seq.track(no_effect)[-1].excludes(seq.NO_DIFFERENCE)
