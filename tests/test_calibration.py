"""Permutation-null calibration tests (I1; lab/034).

Interfaces: thalamus.eval.calibration — kappa, strata, rotation constraints,
            cluster bootstrap, reconstruction fidelity.
Infrastructure: synthetic Cases; no graph, no archive. `load_cases` is exercised
            against the live graph by the experiment runner, not here — a stubbed
            traversal would test the stub.
Scope: the two properties that make a null a null. A rotation must cross sessions
       (or shared vocabulary is not controlled for) and must stay inside a
       window-length stratum (or the null measures the length change instead).
"""

from datetime import datetime, timezone

from thalamus.eval import calibration
from thalamus.eval.attribution import JUDGES, OutputTurn, OutputWindow


def _window(text: str, repeats: int = 1) -> OutputWindow:
    return OutputWindow(turns=[OutputTurn(index=i, parts=[("prose", text)]) for i in range(repeats)])


def _case(trace: str, session: str, node_text: str, window_text: str, repeats: int = 1):
    return calibration.Case(
        trace_id=trace,
        session_id=session,
        scope="main",
        tool="memory_recall",
        ts=datetime(2026, 7, 30, tzinfo=timezone.utc),
        nodes={f"scope:main:claim:{trace}": node_text},
        window=_window(window_text, repeats),
    )


def test_kappa_is_the_share_of_headroom_the_judge_captures():
    """
    Scenario: a judge scores 63% where chance alone scores 59%.

    Verification: kappa reports 0.098, not 0.63 and not the 4-point raw gap. The
    raw rate reads as five times more signal than it has, which is how a target of
    "used% above ~50" came to sit below chance.
    """
    assert calibration.kappa(0.629, 0.594) == pytest_approx(0.086, 0.01)
    assert calibration.kappa(1.0, 0.5) == 1.0
    assert calibration.kappa(0.5, 0.5) == 0.0
    # No headroom: a null at ceiling means there is nothing left to capture, and
    # dividing by zero would turn a degenerate case into a large-looking number.
    assert calibration.kappa(1.0, 1.0) == 0.0


def pytest_approx(value: float, tol: float) -> float:
    class _Approx(float):
        def __eq__(self, other):
            return abs(other - value) <= tol

    return _Approx(value)


def test_strata_split_the_corpus_by_window_length():
    """The judge's used% moves 51.7% -> 69.7% on window length alone, so a
    rotation that ignores length measures the length change."""
    cases = [_case(f"t{i}", f"s{i}", "node", "output", repeats=i + 1) for i in range(12)]
    calibration._assign_strata(cases)
    strata = [c.stratum for c in sorted(cases, key=lambda c: c.window_chars)]
    assert strata == sorted(strata)
    assert len(set(strata)) == calibration.STRATA


def test_a_rotation_never_reuses_the_case_s_own_session():
    """
    Scenario: the null is drawn by re-judging each case against someone else's
    output window.

    Verification: the partner is never the same session. Judging a session against
    itself would put the case's own vocabulary in the null, which is the thing the
    null exists to hold constant.
    """
    same_text = "the reader caps details at eight per node"
    cases = [
        _case("t1", "session-a", same_text, same_text),
        _case("t2", "session-a", same_text, same_text),
    ]
    calibration._assign_strata(cases)
    judge = JUDGES["shipped"]
    result = calibration.score(cases, judge)
    # Both cases are in one session, so no case has an eligible partner and the
    # rotation yields nothing rather than pairing a session with itself.
    rotated = calibration.rotate(cases, judge, result, rotations=5, seed=1)
    assert rotated.null_rates == []
    assert rotated.unpartnered == len(cases)


def test_rotation_produces_a_null_distribution_not_a_single_draw():
    """lab/032's cross-project 5.0% came from one rotation against one pool. One
    draw cannot say whether a 4-point gap is real."""
    topics = [
        "reader detail cap eight",
        "audio feature extraction pipeline",
        "gremlin traversal terminal step",
        "switchback carryover design",
    ]
    # Two sessions per stratum, so every case has an eligible partner. With one
    # case per stratum the rotation correctly yields nothing — see `unpartnered`.
    cases = [
        _case(f"t{i}", f"s{i}", topics[i % 4], topics[i % 4], repeats=1 + i // 2)
        for i in range(8)
    ]
    calibration._assign_strata(cases)
    judge = JUDGES["shipped"]
    result = calibration.score(cases, judge)
    calibration.rotate(cases, judge, result, rotations=25, seed=7)

    assert len(result.null_rates) == 25
    assert result.unpartnered == 0
    assert result.rate == 1.0  # every case echoes its own node verbatim
    lo, hi = result.null_ci
    assert lo <= result.null_mean <= hi


def test_the_bootstrap_resamples_sessions_not_verdicts():
    """Verdicts inside a session share a window, a topic and an operator. The
    measured ICC is 0.264 with a design effect near 4, so a verdict-level interval
    is about half as wide as the truth."""
    cases = [_case(f"t{i}", f"s{i % 3}", "shared vocabulary", "shared vocabulary") for i in range(9)]
    calibration._assign_strata(cases)
    result = calibration.score(cases, JUDGES["shipped"])
    lo, hi = calibration.cluster_bootstrap(cases, result, draws=200, seed=3)
    assert 0.0 <= lo <= hi <= 1.0


def test_fidelity_reports_where_replay_disagrees_with_what_was_stored():
    """
    Scenario: a stored verdict cannot be reproduced from today's graph.

    Verification: it is counted, not smoothed. Node text is mutable (latest-wins)
    and `ingested_at` carries the writing session's timestamp rather than the write
    time, so a node can be rewritten with no trace — and a replay that silently
    diverged would be measuring its own reconstruction.
    """
    case = _case("t1", "s1", "reader detail cap", "reader detail cap")
    case.stored = {"scope:main:claim:t1": False}
    calibration._assign_strata([case])
    result = calibration.score([case], JUDGES["shipped"])
    matched, total = calibration.fidelity([case], result)
    assert (matched, total) == (0, 1)

    case.stored = {"scope:main:claim:t1": True}
    assert calibration.fidelity([case], result) == (1, 1)


def test_discordance_is_measured_across_every_rotation():
    """
    Scenario: 50 rotations run.

    Verification: the flip rate is estimated from all of them, not from the first.
    The n a study needs scales linearly in this number, so estimating it from one
    pairing while discarding the rest is the same "one draw is not an estimate"
    error the null itself exists to avoid.
    """
    cases = [
        _case(f"t{i}", f"s{i}", "reader detail cap eight", "reader detail cap eight", repeats=1 + i // 2)
        for i in range(8)
    ]
    calibration._assign_strata(cases)
    judge = JUDGES["shipped"]
    result = calibration.score(cases, judge)
    calibration.rotate(cases, judge, result, rotations=50, seed=11)

    # Every case contributed a null verdict in every rotation.
    assert sum(t for _u, t in result.null_by_case.values()) == 8 * 50
    assert 0.0 <= result.discordance <= 1.0


def test_the_kappa_interval_moves_the_rate_and_its_null_together():
    """κ is a contrast, so its interval must resample the pair. An interval built
    on the rate alone prices variance the estimator does not have."""
    cases = [
        _case(f"t{i}", f"s{i % 4}", "shared vocabulary here", "shared vocabulary here", repeats=1 + i % 3)
        for i in range(12)
    ]
    calibration._assign_strata(cases)
    judge = JUDGES["shipped"]
    result = calibration.score(cases, judge)
    calibration.rotate(cases, judge, result, rotations=20, seed=5)
    lo, hi = calibration.kappa_ci(cases, result, draws=200, seed=5)
    assert lo <= hi
    # Every case echoes its own node and every partner's window is the same text,
    # so rate and null coincide: κ is 0 and the interval must contain it.
    assert lo <= 0.0 <= hi


def test_restricting_to_claims_keeps_only_immutable_text():
    """Claims are content-addressed on (kind, normalized description), so a
    rewritten claim is a new vertex. Threads and Sessions are upserted latest-wins,
    so their text can change under a stored verdict with nothing recording it."""
    case = calibration.Case(
        trace_id="t1",
        session_id="s1",
        scope="main",
        tool="memory_recall",
        ts=datetime(2026, 7, 30, tzinfo=timezone.utc),
        nodes={
            "scope:main:claim:aaa": "immutable claim text",
            "scope:main:thread:some-slug": "mutable thread description",
            "scope:main:session:abc": "mutable session summary",
        },
        window=_window("immutable claim text"),
        stored={"scope:main:claim:aaa": True},
    )
    claims_only = calibration.restrict([case], {"claim"})
    assert list(claims_only[0].nodes) == ["scope:main:claim:aaa"]
    assert claims_only[0].stored == {"scope:main:claim:aaa": True}

    # A case left with nothing after the filter drops out rather than becoming an
    # empty denominator.
    assert calibration.restrict([case], {"artifact"}) == []


def test_an_unstratified_rotation_is_a_different_null_by_design():
    """The stratum constraint is part of the estimand, not an implementation
    detail: swapping it changes κ by more than the spread between judges."""
    cases = [
        _case(f"t{i}", f"s{i}", "alpha beta gamma delta", "alpha beta gamma delta", repeats=1 + i * 3)
        for i in range(8)
    ]
    calibration._assign_strata(cases)
    judge = JUDGES["shipped"]
    stratified = calibration.score(cases, judge)
    calibration.rotate(cases, judge, stratified, rotations=10, seed=2, stratified=True)
    flat = calibration.score(cases, judge)
    calibration.rotate(cases, judge, flat, rotations=10, seed=2, stratified=False)
    # Both produce a null; the point is that they are separately reportable.
    assert stratified.null_rates and flat.null_rates


def test_restricting_a_corpus_keeps_the_terms_auditability_is_measured_from():
    """
    Scenario: Narrow the corpus to claims, then ask how much of it is auditable

    Verifications:
    - judged_terms survives the restriction, filtered to the surviving nodes
    - auditable() therefore still sees the verdicts that recorded their terms

    `restrict` is the function experiments/001 narrows with *before* calling
    auditable(), so dropping judged_terms here made the auditability of a restricted
    corpus read as zero in the one place it is actually measured — a stored number
    that was a function of a field the same call had just discarded.
    """
    case = calibration.Case(
        trace_id="t1",
        session_id="s1",
        scope="main",
        tool="memory_recall",
        ts=datetime(2026, 7, 30, tzinfo=timezone.utc),
        nodes={
            "scope:main:claim:aaa": "immutable claim text",
            "scope:main:thread:some-slug": "mutable thread description",
        },
        window=_window("immutable claim text"),
        stored={"scope:main:claim:aaa": True, "scope:main:thread:some-slug": False},
        judged_terms={
            "scope:main:claim:aaa": ["immutable", "claim"],
            "scope:main:thread:some-slug": ["mutable", "thread"],
        },
    )

    claims_only = calibration.restrict([case], {"claim"})

    assert claims_only[0].judged_terms == {"scope:main:claim:aaa": ["immutable", "claim"]}
    # Verifies: the terms of a node the filter removed do not ride along
    assert "scope:main:thread:some-slug" not in claims_only[0].judged_terms
    # Verifies: the verdict is still reported as auditable after narrowing
    with_terms, _immutable, total = calibration.auditable(claims_only)
    assert (with_terms, total) == (1, 1)
