"""
Randomization inference tests (eval/randomization.py + its use of eval/sequential.py).

Interfaces: thalamus.eval.randomization (feasible, min_attainable_p, smallest_design,
randomization_test, monitor, render)
Infrastructure: none — pure arithmetic over cluster-level outcome vectors
Scope: the test anchored as the few-treated-clusters fallback, and the design floor
that decides whether a campaign can reject before it is run. The floor is two-sided
because a signed two-sided outcome is required.
"""

import pytest

from thalamus.eval.randomization import (
    difference_in_means,
    feasible,
    min_attainable_p,
    monitor,
    n_assignments,
    randomization_test,
    render,
    smallest_design,
)


def test_the_floor_is_two_sided_in_a_balanced_design():
    """
    Scenario: 6 clusters split 3/3. There are 20 assignments, so a one-sided floor
    would be 0.05.

    Verification: the floor is 0.10, not 0.05. Every assignment's complement is also
    an assignment and yields the negated difference, so the most extreme statistic
    always arrives as a ± pair and a two-sided count can never see fewer than two.
    """
    assert n_assignments(6, 3) == 20
    assert min_attainable_p(6, 3) == pytest.approx(0.10)


def test_an_unbalanced_design_has_no_complement_and_so_a_lower_floor():
    """
    Verification: 7 clusters split 3/4 floors at 1/35, because the complement of a
    3-of-7 assignment is a 4-of-7 split, which is not a candidate assignment at all.
    The arithmetic favours the odd split; power still favours balance above the floor.
    """
    assert min_attainable_p(7, 3) == pytest.approx(1 / 35)
    # Verifies: the balanced neighbour needs more clusters to clear the same alpha
    assert min_attainable_p(6, 3) > 0.05 >= min_attainable_p(7, 3)


def test_a_perfect_separation_still_cannot_reject_with_six_clusters():
    """
    Scenario: three treated clusters all above three control clusters, with no
    overlap whatsoever — the cleanest result the design could ever produce.

    Verification: p = 0.10. This is the module's reason for existing: no effect size
    rescues a design whose assignment space is too small, so the shape has to be
    fixed while it is still free to change.
    """
    outcomes = [0.9, 0.8, 0.85, 0.2, 0.3, 0.25]
    treated = [True] * 3 + [False] * 3
    result = randomization_test(outcomes, treated)

    assert result.exact
    assert result.p_value == pytest.approx(0.10)
    assert result.at_floor
    assert not feasible(6, 3).possible


def test_eight_clusters_can_reject_on_the_same_shape():
    """
    Verification: the identical separation over 8 clusters reads p = 2/70. The data
    did not get better — the assignment space got bigger, which is the only thing
    that moves the floor.
    """
    outcomes = [0.9, 0.8, 0.85, 0.88, 0.2, 0.3, 0.25, 0.22]
    treated = [True] * 4 + [False] * 4
    result = randomization_test(outcomes, treated)

    assert result.p_value == pytest.approx(2 / 70)
    assert result.p_value <= 0.05
    assert feasible(8, 4).possible


def test_smallest_design_reports_the_split_not_just_the_count():
    """
    Verification: the smallest design clearing alpha=0.05 is 7 clusters split 3/4,
    and the function returns the split because the count alone would be read as
    balanced and would not clear it.
    """
    total, treated = smallest_design(alpha=0.05)
    assert (total, treated) == (7, 3)
    assert min_attainable_p(total, treated) <= 0.05
    # Verifies: one fewer cluster cannot clear it under any split
    assert all(min_attainable_p(6, t) > 0.05 for t in range(1, 6))


def test_no_effect_reads_as_no_effect():
    """
    Verification: identical outcomes across arms give the largest possible p rather
    than an artefact of the enumeration — the observed assignment ties every other,
    so every one of them counts as at least as extreme.
    """
    outcomes = [0.5] * 8
    treated = [True] * 4 + [False] * 4
    result = randomization_test(outcomes, treated)
    assert result.observed == pytest.approx(0.0)
    assert result.p_value == pytest.approx(1.0)


def test_a_design_with_no_contrast_is_refused_rather_than_scored():
    """
    Verification: when every cluster is treated there is no counterfactual arm, so
    the result is p = 1.0 and a floor of 1.0 rather than a divide-by-zero or a
    spuriously confident number.
    """
    result = randomization_test([0.9, 0.8], [True, True])
    assert result.p_value == 1.0
    assert result.floor == 1.0


def test_outcomes_and_assignment_must_describe_the_same_clusters():
    """
    Verification: a length mismatch raises instead of silently zipping short, which
    would drop clusters off the end of the vector and shrink the assignment space
    without saying so.
    """
    with pytest.raises(ValueError):
        randomization_test([0.1, 0.2, 0.3], [True, False])


def test_the_statistic_is_signed_so_harm_is_observable():
    """
    Verification: a treated arm *below* control yields a negative statistic and the
    same p-value as the mirrored case. This is required — a metric that counts
    only wins cannot observe the harm a room might cause.
    """
    good = randomization_test([0.9, 0.9, 0.1, 0.1], [True, True, False, False])
    bad = randomization_test([0.1, 0.1, 0.9, 0.9], [True, True, False, False])
    assert good.observed > 0 > bad.observed
    assert good.p_value == pytest.approx(bad.p_value)
    assert difference_in_means([1.0], [0.0]) == pytest.approx(1.0)


def test_monitor_gives_sequential_its_caller_and_stays_conservative():
    """
    Scenario: the unpaired shape a room design actually has — clusters are treated or
    not, so there is no per-cluster difference to take.

    Verification: both arms get a confidence sequence, and at 4 observations the
    Robbins boundary is wide enough that the intervals overlap despite a clean
    separation. That is the anytime-valid price being paid honestly, and the text
    says overlap licenses no conclusion rather than implying a null.
    """
    outcomes = [0.9, 0.8, 0.85, 0.88, 0.2, 0.3, 0.25, 0.22]
    treated = [True] * 4 + [False] * 4
    text = monitor(outcomes, treated)

    assert "treated" in text and "control" in text
    assert "overlap" in text
    assert "no conclusion" in text


def test_monitor_refuses_a_paired_read_of_an_unpaired_design():
    """
    Verification: paired monitoring needs one treated and one control observation per
    cluster; an uneven split says so rather than silently zipping to the shorter arm
    and reporting a difference over a subset.
    """
    text = monitor([0.9, 0.8, 0.2], [True, True, False], paired=True)
    assert "paired monitoring needs" in text


def test_render_keeps_the_two_guarantees_apart():
    """
    Verification: the rendered block labels the sequence as valid at every look and
    keeps it separate from the p-value, which is exact at one. Merging them into a
    single number would imply a joint guarantee neither provides — and a sequential
    randomization test is a construction this project does not hold literature for.
    """
    outcomes = [0.9, 0.8, 0.85, 0.88, 0.2, 0.3, 0.25, 0.22]
    treated = [True] * 4 + [False] * 4
    text = render(randomization_test(outcomes, treated), feasible(8, 4), monitor(outcomes, treated))

    assert "design:" in text
    assert "randomization inference:" in text
    assert "every look" in text
