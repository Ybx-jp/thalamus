"""
Retiring named Sources and what rests only on them.

Interfaces: thalamus.substrate.source_retirement.decide
Infrastructure: none — `decide` is pure over rows already read, which is where the
                judgement about what a deletion may reach lives
Scope: a vertex goes only when everything it rests on goes. Every case pins the timid
       direction: keeping a vertex that could have gone costs an audit line, removing
       one that should have stayed costs evidence another document supplied.
"""

from __future__ import annotations

from thalamus.substrate.source_retirement import decide

BAD = {"vid": "scope:literature:source:bad", "title": "mlflow/mlflow"}
GOOD = "scope:literature:source:good"


def _derived(vid, label="Claim", derived_from=(BAD["vid"],), edges=()):
    return {"vid": vid, "label": label, "detail": vid, "derived_from": list(derived_from),
            "edges": list(edges)}


def test_a_claim_resting_only_on_the_source_goes_with_it():
    plan = decide(sources=[BAD], derived=[_derived("claim:1")], entities=[])

    assert [d.vid for d in plan.claims] == ["claim:1"]
    assert plan.kept_claims == []


def test_a_claim_another_document_also_supports_is_kept():
    """Claims are content-addressed: the same statement from a second ingest converges
    onto one vertex with two DERIVED_FROM edges, and the second is still evidence."""
    plan = decide(sources=[BAD], derived=[_derived("claim:1", derived_from=(BAD["vid"], GOOD))],
                  entities=[])

    assert plan.claims == []
    assert plan.kept_claims == [("claim:1", 1)]


def test_chunks_go_with_their_source():
    plan = decide(sources=[BAD], derived=[_derived("chunk:0", label="Chunk")], entities=[])

    assert [d.vid for d in plan.chunks] == ["chunk:0"]


def test_an_entity_only_the_retired_document_mentions_is_removed():
    plan = decide(
        sources=[BAD],
        derived=[_derived("claim:1"), _derived("chunk:0", label="Chunk")],
        entities=[{"vid": "entity:mlflow", "name": "MLflow",
                   "neighbours": ["claim:1", "chunk:0"]}],
    )

    assert [d.detail for d in plan.entities] == ["MLflow"]


def test_an_entity_another_claim_mentions_is_kept():
    """Entities are scope-wide; one document retiring does not retire the concept."""
    plan = decide(
        sources=[BAD],
        derived=[_derived("claim:1")],
        entities=[{"vid": "entity:dvc", "name": "DVC",
                   "neighbours": ["claim:1", "scope:literature:claim:elsewhere"]}],
    )

    assert plan.entities == []
    assert plan.kept_entities == [("DVC", 1)]


def test_edges_from_surviving_vertices_are_counted_as_history_lost():
    """A Trace that served the claim keeps existing and loses its RETURNS edge; edges
    between two retiring vertices are not history anyone keeps."""
    plan = decide(
        sources=[BAD],
        derived=[_derived("claim:1", edges=[
            ("DERIVED_FROM", BAD["vid"]),
            ("ANCHORS", "chunk:0"),
            ("RETURNS", "scope:main:trace:t1"),
            ("RETURNS", "scope:main:trace:t2"),
        ]), _derived("chunk:0", label="Chunk")],
        entities=[],
    )

    assert plan.lost_edges == {"RETURNS": 2}


def test_a_kept_claim_loses_no_edges():
    plan = decide(
        sources=[BAD],
        derived=[_derived("claim:1", derived_from=(BAD["vid"], GOOD),
                          edges=[("RETURNS", "scope:main:trace:t1")])],
        entities=[],
    )

    assert not plan.lost_edges


def test_the_sources_themselves_are_always_in_the_plan():
    plan = decide(sources=[BAD], derived=[], entities=[])

    assert plan.doomed_vids() == [BAD["vid"]]
    assert plan.total() == 1
