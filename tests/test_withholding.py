"""
Randomized-withholding recurrence tests (tracker #107).

Interfaces: thalamus.eval.withholding (Event, analyse, _later_universes)
Infrastructure: hand-built Events; no live graph, no ledger on disk
Scope: the outcome layer only — eligibility, the within-event permutation null, and
the two recurrence universes. The graph/ledger join (`load_events`) is exercised
against the live corpus, not here.
"""

import pytest

from thalamus.eval.withholding import Event, _later_universes, analyse


def _event(ts, offered, withheld, surfaced=None, session="s1"):
    return Event(
        trace_id=f"trace:{ts}",
        session_id=session,
        scope="main",
        ts=ts,
        tool="mcp__thalamus__memory_recall",
        offered=tuple(offered),
        withheld=frozenset(withheld),
        surfaced=frozenset(surfaced if surfaced is not None else offered),
    )


def test_singleton_offer_is_never_contested():
    """
    Scenario: an event offering one node, and one offering two with a draw

    Verifications:
    - a singleton offer cannot contribute a contrast whatever the draw said
    - the exclusion follows from the arms being empty, not from a size test
    """
    assert not _event("1", ["a"], []).contested
    assert not _event("1", ["a"], ["a"]).contested
    assert _event("1", ["a", "b"], ["a"]).contested


def test_uncontested_events_have_an_empty_arm():
    """
    Scenario: an event where the draw took nothing, and one where it took all

    Verifications:
    - both are uncontested, for opposite reasons
    - `kept` is offered-minus-withheld and preserves offered order
    """
    assert not _event("1", ["a", "b"], []).contested
    assert not _event("1", ["a", "b"], ["a", "b"]).contested
    assert _event("1", ["a", "b", "c"], ["b"]).kept == ("a", "c")


def test_later_universes_exclude_the_event_itself():
    """
    Scenario: three ordered events in one session, each surfacing a distinct node

    Verifications:
    - position i sees everything after i and nothing at or before it
    - the last event sees nothing, which is what makes it terminal
    - the returned universe drops what a later event withheld; surfaced keeps it
    """
    group = [
        _event("1", ["a"], [], surfaced=["a"]),
        _event("2", ["b", "x"], ["x"], surfaced=["b", "x"]),
        _event("3", ["c"], [], surfaced=["c"]),
    ]
    surfaced_after, returned_after = _later_universes(group)
    assert surfaced_after[0] == {"b", "x", "c"}
    assert surfaced_after[1] == {"c"}
    assert surfaced_after[2] == set()
    # `x` was withheld at position 1, so it never rendered — present in the
    # surfaced universe of position 0 and absent from the returned one.
    assert returned_after[0] == {"b", "c"}


def test_terminal_event_is_excluded_not_scored_as_a_miss():
    """
    Scenario: a session whose only contested event is its last retrieval

    Verifications:
    - the event is counted terminal and contributes no nodes to either arm
    - a design predicate, evaluated before any outcome is read
    """
    events = [_event("1", ["a", "b"], ["a"])]
    report = analyse(events, draws=50)
    assert report.terminal_events == 1
    assert report.eligible_events == 0
    assert report.withheld.total == 0


def test_statistic_is_the_mean_over_sessions_not_over_nodes():
    """
    Scenario: a one-event session where only the withheld node returns, and a
    three-event session where both arms return alike

    Verifications:
    - the statistic is +0.5, the mean of the two sessions' differences
    - it is not the node-pooled +0.14, which the larger session would dominate
    """
    small = [
        _event("1", ["a", "b"], ["a"], surfaced=["a", "b"], session="small"),
        _event("2", ["a"], [], surfaced=["a"], session="small"),
    ]
    big = [
        _event(str(i), ["a", "b", "c", "d"], ["a", "b"],
               surfaced=["a", "b", "c", "d"], session="big")
        for i in range(1, 4)
    ] + [_event("4", ["zz"], [], surfaced=["zz"], session="big")]
    report = analyse(small + big, draws=10)
    assert report.sessions == 2
    assert report.statistic == pytest.approx(0.5)
    pooled = (report.withheld.hits / report.withheld.total
              - report.kept.hits / report.kept.total)
    assert pooled == pytest.approx(1 / 7 * 5 - 4 / 7, abs=0.01)
    assert report.statistic != pytest.approx(pooled)


def test_withholding_that_changes_nothing_reads_null():
    """
    Scenario: recurrence assigned so that it is independent of the withheld label

    Verifications:
    - the observed statistic sits inside the permutation null
    - p is nowhere near the floor, and the detectable effect is reported with it
    """
    events = []
    for i in range(1, 21):
        # Two of four nodes recur in the next event, one from each arm — so the
        # arms recur alike by construction.
        events.append(_event(
            f"{i:02d}", ["a", "b", "c", "d"], ["a", "b"],
            surfaced=["a", "b", "c", "d"],
        ))
        events.append(_event(f"{i:02d}z", ["a", "c"], [], surfaced=["a", "c"]))
    report = analyse(events, draws=500, seed=1)
    assert report.p_value > 0.2
    assert report.detectable > 0


def test_a_planted_effect_is_detected():
    """
    Scenario: every withheld node recurs and no kept node does, across 12 sessions

    Verifications:
    - the permutation test reaches its attainable floor
    - the effect is the full +1.0 the construction plants
    """
    events = []
    for s in range(12):
        events.append(_event(
            "1", ["w1", "w2", "k1", "k2"], ["w1", "w2"],
            surfaced=["w1", "w2", "k1", "k2"], session=f"s{s}",
        ))
        # Only the withheld pair comes back.
        events.append(_event(
            "2", ["w1", "w2"], [], surfaced=["w1", "w2"], session=f"s{s}",
        ))
    report = analyse(events, draws=500, seed=1)
    assert report.statistic == pytest.approx(1.0)
    assert report.p_value == pytest.approx(1 / 501)


def test_permutation_holds_the_withheld_count_fixed():
    """
    Scenario: one session of events with differing withheld counts

    Verifications:
    - the arm totals are a property of the draw sizes, so they are identical in
      every permutation and the null varies only in which nodes carry the label
    """
    events = [
        _event("1", ["a", "b", "c"], ["a"], surfaced=["a", "b", "c"]),
        _event("2", ["a", "b", "c"], ["a", "b"], surfaced=["a", "b", "c"]),
        _event("3", ["a", "b"], [], surfaced=["a", "b"]),
    ]
    report = analyse(events, draws=200, seed=1)
    # Events 1 and 2 are contested and non-terminal; 3 is uncontested.
    assert report.eligible_events == 2
    assert report.uncontested_events == 1
    assert report.withheld.total == 3
    assert report.kept.total == 3


def test_report_renders_counts_and_the_detectable_floor():
    """
    Scenario: a rendered report for a small corpus

    Verifications:
    - the permutation floor and the detectable effect both travel with the p-value
    - `Rate` refuses a percentage under its own n floor rather than printing one
    """
    events = [
        _event("1", ["a", "b", "c"], ["a"], surfaced=["a", "b", "c"]),
        _event("2", ["a", "b"], [], surfaced=["a", "b"]),
    ]
    rendered = analyse(events, draws=100).render()
    assert "attainable floor" in rendered
    assert "at 80% power" in rendered
    assert "no rate rendered (n<20)" in rendered
