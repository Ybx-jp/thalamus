"""The attribution-subgraph report: what it counts, and what it refuses to pool."""

from __future__ import annotations

import pytest

from thalamus.eval import uses as uses_mod
from thalamus.eval.uses import UsesReport, _longest_chain, _reach, uses_report


def _session(vid, scope="main", ts="2026-09-03T04:58:06+00:00", reason_edges=0, offered=0):
    return {
        "id": vid,
        "scope": scope,
        "ts": ts,
        "reason_edges": reason_edges,
        "offered": offered,
    }


def _edge(
    root="scope:main:claim:a",
    target="scope:main:claim:b",
    role="reason",
    verified=True,
    root_scope="main",
    target_scope="main",
    target_label="Claim",
    target_contained=1,
):
    return {
        "root": root,
        "root_scope": root_scope,
        "target": target,
        "target_label": target_label,
        "target_scope": target_scope,
        "target_contained": target_contained,
        "role": role,
        "verified": verified,
    }


@pytest.fixture
def rows(monkeypatch):
    """Drive the aggregation directly, without a Gremlin fake.

    The traversals are four projections whose shape a fake would restate; the logic
    worth protecting is what the report does with the rows, so the rows are the seam.
    """
    state: dict[str, list] = {"sessions": [], "edges": [], "rejected": 0, "kinds": []}
    monkeypatch.setattr(uses_mod, "_session_rows", lambda g, scope: state["sessions"])
    monkeypatch.setattr(uses_mod, "_edge_rows", lambda g, scope: state["edges"])
    monkeypatch.setattr(uses_mod, "_rejected_claims", lambda g, scope: state["rejected"])
    monkeypatch.setattr(
        uses_mod, "_outcome_kinds", lambda g, scope: uses_mod.Counter(state["kinds"])
    )
    monkeypatch.setattr(uses_mod, "_claims_in_window", lambda g, dated: set())
    return state


def test_longest_chain_reads_a_star_as_one_hop():
    assert _longest_chain([("a", "b"), ("a", "c"), ("d", "b")]) == 1


def test_longest_chain_counts_hops_through_a_cited_citer():
    assert _longest_chain([("a", "b"), ("b", "c"), ("c", "d")]) == 3


def test_longest_chain_refuses_a_cycle_rather_than_cutting_it():
    assert _longest_chain([("a", "b"), ("b", "a")]) == -1


def test_longest_chain_of_nothing_is_zero():
    assert _longest_chain([]) == 0


def test_sessions_split_by_what_they_did_with_the_offer(rows):
    rows["sessions"] = [
        _session("s1", reason_edges=2, offered=1),
        _session("s2", offered=1),
        _session("s3"),
    ]
    report = uses_report(object())
    assert (report.cited, report.offered_uncited, report.unoffered) == (1, 1, 1)
    assert report.offered == 2


def test_first_cited_is_the_earliest_citing_session(rows):
    rows["sessions"] = [
        _session("s1", ts="2026-09-07T00:00:00+00:00", reason_edges=1, offered=1),
        _session("s2", ts="2026-09-03T00:00:00+00:00", reason_edges=1, offered=1),
    ]
    report = uses_report(object())
    assert report.first_cited is not None
    assert str(report.first_cited.date()) == "2026-09-03"


def test_rejected_edges_are_stamped_apart_and_never_counted_as_attribution(rows):
    rows["edges"] = [
        _edge(),
        _edge(role="rejected", target="scope:main:claim:opt", verified=False),
    ]
    report = uses_report(object())
    assert report.reason_edges == 1
    assert report.roots == 1
    assert report.stamps["reason"]["served"] == 1
    assert report.stamps["rejected"]["not served"] == 1


def test_an_unstamped_edge_reads_as_unchecked_not_as_unserved(rows):
    rows["edges"] = [_edge(verified="")]
    report = uses_report(object())
    assert report.stamps["reason"]["unchecked"] == 1
    assert report.stamps["reason"]["not served"] == 0


def test_scope_narrows_the_root_and_keeps_the_cross_scope_target(rows):
    """The property the surface exists for: a scope owns the subgraphs it roots.

    Filtering on the target's scope would drop exactly the citations into another
    scope's knowledge that `USES` is allowed to make, which is the reach worth seeing.
    """
    rows["edges"] = [
        _edge(target="scope:literature:claim:x", target_scope="literature", target_contained=0)
    ]
    report = uses_report(object(), scope="main")
    assert report.reason_edges == 1
    assert report.target_reach["into another scope's knowledge"] == 1


def test_reach_names_the_three_places_an_edge_can_land():
    assert _reach(_edge()) == "within the root's own scope"
    knowledge = _edge(target_scope="literature", target_contained=0)
    assert _reach(knowledge) == "into another scope's knowledge"
    episodic = _edge(target_scope="qe", target_contained=1)
    assert "episodic" in _reach(episodic)


def test_window_excludes_rather_than_assumes(rows):
    rows["sessions"] = [
        _session("s1", ts="2026-09-01T00:00:00+00:00", offered=1),
        _session("s2", ts="", offered=1),
        _session("s3", ts="2026-09-05T00:00:00+00:00", reason_edges=1, offered=1),
    ]
    report = uses_report(object(), since="2026-09-02")
    assert (report.out_of_window, report.undated) == (1, 1)
    assert (report.cited, report.offered) == (1, 1)


def test_render_says_a_star_graph_has_not_compounded(rows):
    rows["sessions"] = [_session("s1", reason_edges=1, offered=1)]
    rows["edges"] = [_edge(), _edge(target="scope:main:claim:c")]
    rendered = uses_report(object()).render()
    assert "nothing has compounded yet" in rendered
    assert "1 hop" in rendered


def test_render_marks_the_stamp_as_constant_by_construction(rows):
    rows["edges"] = [_edge()]
    rendered = uses_report(object()).render()
    assert "near-constant by construction" in rendered


def test_render_says_the_stamp_rule_does_not_reach_a_rejected_edge(rows):
    rows["edges"] = [_edge(role="rejected", verified=False)]
    rendered = uses_report(object()).render()
    assert "the rule does not apply to `rejected`" in rendered
    assert "#202" in rendered


def test_render_never_prints_a_bare_coverage_percentage():
    """`Rate` refuses a null-less number without a reason; the report must not route
    around that by rendering the fraction itself."""
    rendered = UsesReport(cited=13, offered_uncited=172).render()
    assert "no null —" in rendered
    assert "13/185" in rendered


def test_render_reports_an_empty_graph_without_dividing_by_it():
    rendered = UsesReport().render()
    assert "nothing has been cited yet" in rendered


def test_a_window_keeps_the_edges_of_the_claims_it_holds(monkeypatch, rows):
    """Edges are windowed by the sessions containing their root, not by the edge.

    A `USES` edge carries no timestamp and its root claim carries none either — the
    claim is content-addressed and can sit in several sessions. So the window is read
    off the containing session, and an edge whose root is not in one of them is out.
    """
    rows["sessions"] = [
        _session("s1", ts="2026-09-05T00:00:00+00:00", reason_edges=1, offered=1)
    ]
    rows["edges"] = [
        _edge(root="scope:main:claim:kept"),
        _edge(root="scope:main:claim:dropped"),
    ]
    monkeypatch.setattr(
        uses_mod, "_claims_in_window", lambda g, dated: {"scope:main:claim:kept"}
    )
    report = uses_report(object(), since="2026-09-02")
    assert report.reason_edges == 1
    assert report.roots == 1
    assert sum(report.stamps["reason"].values()) == 1
