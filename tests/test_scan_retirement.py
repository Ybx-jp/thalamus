"""
Retiring the graph records of architecture scans.

Interfaces: thalamus.substrate.scan_retirement.decide
Infrastructure: none — `decide` is pure over rows already read, which is deliberately
                where the dangerous judgement lives
Scope: what a deletion is allowed to reach. The asymmetry is the point: keeping a
       vertex that could have gone costs an orphan line in an audit, and removing one
       that should have stayed costs a file its identity, so every case here pins the
       timid direction.
"""

from __future__ import annotations

from thalamus.substrate.scan_retirement import decide

SOURCE = {"vid": "scope:architect:source:aaa", "origin": "arch:scan:demo:abc:def", "uri": "archive://aaa"}
CLAIM = {"vid": "scope:architect:claim:111", "description": "Import cycle among 2 modules."}


def test_an_artifact_touched_by_a_session_too_is_kept():
    """The whole reason Artifacts are global: a scan and a session name one vertex."""
    plan = decide(
        sources=[SOURCE],
        claims=[CLAIM],
        artifacts=[
            {
                "vid": "artifact:src/app/core.py",
                "identifier": "src/app/core.py",
                "neighbours": [CLAIM["vid"], "scope:main:session:real-session"],
            }
        ],
    )
    assert plan.artifacts == []
    assert plan.kept_artifacts == [("src/app/core.py", 1)]


def test_an_artifact_only_a_scan_ever_touched_is_removed():
    plan = decide(
        sources=[SOURCE],
        claims=[CLAIM],
        artifacts=[
            {
                "vid": "artifact:src/app/lonely.py",
                "identifier": "src/app/lonely.py",
                "neighbours": [CLAIM["vid"]],
            }
        ],
    )
    assert [d.detail for d in plan.artifacts] == ["src/app/lonely.py"]
    assert plan.kept_artifacts == []


def test_a_neighbour_that_is_itself_doomed_does_not_save_an_artifact():
    """Two scan claims propping each other up is not a surviving reference."""
    second = {"vid": "scope:architect:claim:222", "description": "Dependency rule violated."}
    plan = decide(
        sources=[SOURCE],
        claims=[CLAIM, second],
        artifacts=[
            {
                "vid": "artifact:src/app/pair.py",
                "identifier": "src/app/pair.py",
                "neighbours": [CLAIM["vid"], second["vid"], SOURCE["vid"]],
            }
        ],
    )
    assert [d.detail for d in plan.artifacts] == ["src/app/pair.py"]


def test_retained_bytes_are_reported_and_never_counted_as_removable():
    plan = decide(sources=[SOURCE], claims=[], artifacts=[])
    assert plan.uncited_blobs == ["archive://aaa"]
    assert plan.doomed_vids() == [SOURCE["vid"]]


def test_an_empty_graph_plans_nothing():
    plan = decide(sources=[], claims=[], artifacts=[])
    assert plan.total() == 0
    assert plan.doomed_vids() == []


def test_claims_are_dropped_before_the_sources_they_derive_from():
    """Order is not incidental — a reader of the plan should see the leaves first."""
    plan = decide(sources=[SOURCE], claims=[CLAIM], artifacts=[])
    assert plan.doomed_vids() == [CLAIM["vid"], SOURCE["vid"]]
