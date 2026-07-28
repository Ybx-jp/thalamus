"""Rake registry tests — Class A stage 0 (lab/024 §2.1).

Interfaces: thalamus.eval.rakes
Infrastructure: none — pure aggregation, no graph, no model
Scope: the three rules that decide whether this metric is honest or flattering.
Each is a measured property of the live corpus, not a hypothetical:

- unobservable rakes must never be counted as never-hit (they inflate any
  benefit number by ~2x on the real graph: 214 unobservable vs 208 observable);
- the project gate must hold, because Artifact is global and relative paths
  genuinely collide across projects (14 such artifacts live today);
- low-specificity keys are flagged, never dropped (arXiv 2111.03382).

The graph readers are exercised live like every other write/read path; the
window arithmetic is what can silently rot, so it is what gets pinned here.
"""

from thalamus.eval.rakes import (
    HOT_ARTIFACT_SESSIONS,
    Rake,
    SessionRow,
    build_rake_report,
)


def _session(vid: str, ts: str, project: str = "thalamus") -> SessionRow:
    return SessionRow(vid=vid, session_id=vid, project=project, ts=ts)


def test_a_rake_no_later_session_touched_is_unobservable_not_never_hit():
    """The load-bearing bucket. 'Nothing to observe' and 'observed clean' are
    different verdicts, the same way an empty attribution window is not 'ignored'."""
    rakes = [
        Rake(vid="r1", description="jq missing in the arm image", artifacts=("hooks.sh",), sessions=("s1",)),
    ]
    sessions = {"s1": _session("s1", "2026-07-01")}

    report = build_rake_report(rakes, sessions, {"hooks.sh": ["s1"]})

    assert report.observable == 0
    assert report.unobservable == 1
    assert report.unkeyable == 0
    assert report.candidates == []
    # The renderer has to say so out loud — a bare count invites the wrong read.
    assert "not 'never hit'" in report.render()


def test_a_rake_with_no_artifact_is_unkeyable_and_kept_apart_from_unobservable():
    rakes = [Rake(vid="r1", description="a purely conceptual misunderstanding", sessions=("s1",))]
    report = build_rake_report(rakes, {"s1": _session("s1", "2026-07-01")}, {})

    assert (report.unkeyable, report.unobservable, report.observable) == (1, 0, 0)


def test_only_sessions_strictly_after_the_rake_was_registered_count():
    """A session that ran *before* the problem was solved cannot have stepped on
    a rake that did not exist yet."""
    rakes = [Rake(vid="r1", description="p", artifacts=("arms.py",), sessions=("s2",))]
    sessions = {
        "s1": _session("s1", "2026-07-01"),  # earlier — not a candidate
        "s2": _session("s2", "2026-07-10"),  # the registering session itself
        "s3": _session("s3", "2026-07-20"),  # later — the only candidate
    }

    report = build_rake_report(rakes, sessions, {"arms.py": ["s1", "s2", "s3"]})

    assert report.observable == 1
    assert [c.session_vid for c in report.candidates] == ["s3"]


def test_cross_project_pairs_are_gated_and_disclosed():
    """Artifact is global and keyed on `identifier`, so one README.md vertex is
    shared by every project that touched it. Without the gate a stepmania session
    opening README.md becomes a candidate for a thalamus rake."""
    rakes = [Rake(vid="r1", description="p", artifacts=("README.md",), sessions=("s1",))]
    sessions = {
        "s1": _session("s1", "2026-07-01", project="thalamus"),
        "s2": _session("s2", "2026-07-05", project="stepmania-chart-generator"),
        "s3": _session("s3", "2026-07-06", project="thalamus"),
    }

    report = build_rake_report(rakes, sessions, {"README.md": ["s1", "s2", "s3"]})

    assert [c.session_vid for c in report.candidates] == ["s3"]
    assert report.cross_project_dropped == 1
    assert "cross-project pair" in report.render()


def test_hot_artifact_pairs_are_flagged_and_counted_apart_but_never_dropped():
    """Flag, never exclude (arXiv 2111.03382) — the same rule the infra classifier
    and the escape detector follow. A hot key is weak evidence, not no evidence."""
    hot_sessions = [f"h{i}" for i in range(HOT_ARTIFACT_SESSIONS + 2)]
    rakes = [
        Rake(vid="r1", description="p", artifacts=("README.md",), sessions=("s1",)),
        Rake(vid="r2", description="q", artifacts=("eval/rakes.py",), sessions=("s1",)),
    ]
    sessions = {"s1": _session("s1", "2026-07-01")}
    sessions.update({h: _session(h, "2026-07-10") for h in hot_sessions})

    report = build_rake_report(
        rakes,
        sessions,
        {"README.md": ["s1", *hot_sessions], "eval/rakes.py": ["s1", hot_sessions[0]]},
    )

    hot = [c for c in report.candidates if c.rake_vid == "r1"]
    specific = [c for c in report.candidates if c.rake_vid == "r2"]
    assert hot and all(c.hot for c in hot)
    assert specific and not any(c.hot for c in specific)
    # Dropped would have been the easy call; the queue keeps them, separated.
    assert len(report.candidates) == len(hot) + len(specific)
    assert report.specific_candidates == specific
    assert report.hot_artifacts == {"README.md": len(hot_sessions) + 1}


def test_identity_convergence_is_reported_because_it_is_the_detector_that_failed():
    """4 of 504 on the live corpus. The number is rendered every run so no future
    session assumes content-addressed identity can carry recurrence detection."""
    rakes = [
        Rake(vid="r1", description="p", artifacts=("a.py",), sessions=("s1", "s2")),
        Rake(vid="r2", description="q", artifacts=("a.py",), sessions=("s1",)),
    ]
    sessions = {"s1": _session("s1", "2026-07-01"), "s2": _session("s2", "2026-07-02")}

    report = build_rake_report(rakes, sessions, {"a.py": ["s1", "s2"]})

    assert report.converged == 1
    assert "identity-converged rakes: 1/2" in report.render()


def test_a_rake_whose_sessions_have_no_timestamp_cannot_bound_later():
    """No registration time means 'later' is undefined; that is unobservable, not
    an excuse to compare against the empty string and match everything."""
    rakes = [Rake(vid="r1", description="p", artifacts=("a.py",), sessions=("s1",))]
    sessions = {"s1": _session("s1", ""), "s2": _session("s2", "2026-07-20")}

    report = build_rake_report(rakes, sessions, {"a.py": ["s1", "s2"]})

    assert report.unobservable == 1
    assert report.candidates == []


def test_the_report_states_that_candidates_are_not_hits():
    report = build_rake_report(
        [Rake(vid="r1", description="p", artifacts=("a.py",), sessions=("s1",))],
        {"s1": _session("s1", "2026-07-01"), "s2": _session("s2", "2026-07-20")},
        {"a.py": ["s1", "s2"]},
    )
    rendered = report.render()

    assert report.observable == 1
    assert "proximity, not encounters" in rendered
    assert "no rake is scored hit or missed here" in rendered


def test_an_empty_registry_says_so_rather_than_rendering_a_zero_rate():
    report = build_rake_report([], {}, {}, problems=12)

    assert report.rakes == 0
    assert "No rakes registered" in report.render()
