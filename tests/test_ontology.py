"""
Core ontology and scope-legality tests.

Interfaces: thalamus.contract.ontology.vid, scope_of, edge_crosses_scope
Infrastructure: none
Scope: the global-Artifact carve-out and the scope segment in vertex IDs
"""

from thalamus.contract.ontology import (
    LABEL_PROPERTIES,
    MAIN_SCOPE,
    edge_crosses_scope,
    is_global,
    scope_of,
    vid,
)


def test_artifact_is_the_only_global_node_type():
    """
    Scenario: Distinguish the global join key from scoped node types

    Verifications:
    - Artifact vertex IDs carry no scope segment
    - Session, Thread, and Claim vertex IDs are scoped
    """
    # Verifies: Artifact is global — one vertex per identifier, shared by every scope
    assert is_global("Artifact")
    assert vid("Artifact", "src/foo.py") == "artifact:src/foo.py"
    assert vid("Artifact", "src/foo.py", scope="literature") == "artifact:src/foo.py"

    # Verifies: everything else is scoped
    for label in ("Session", "Thread", "Claim"):
        assert not is_global(label)
    assert vid("Session", "abc", "main") == "scope:main:session:abc"
    assert vid("Claim", "9f3a", "literature") == "scope:literature:claim:9f3a"
    assert scope_of(vid("Thread", "t1", "dl")) == "dl"
    assert scope_of(vid("Artifact", "src/foo.py")) is None


def test_edges_through_global_artifacts_do_not_count_as_scope_crossings():
    """
    Scenario: Decide whether an edge crosses a scope boundary

    Verifications:
    - a direct edge between two expert scopes is a crossing
    - an edge into the global Artifact vertex is NOT a crossing

    This is the load-bearing case. Artifacts are shared, so two experts that ever touched
    the same file are joined through one. If paths through globals counted as crossings,
    the cross-scope density metric that grades roster granularity (docs/08 split/merge)
    would measure "same repo" rather than "same domain" and be useless. See docs/09 G3.
    """
    literature_claim = vid("Claim", "aaa", "literature")
    dl_claim = vid("Claim", "bbb", "dl")
    shared_artifact = vid("Artifact", "src/model.py")

    # Verifies: a direct expert-to-expert edge is a real crossing
    assert edge_crosses_scope(literature_claim, dl_claim)

    # Verifies: shared vocabulary is not a channel — neither direction is a crossing
    assert not edge_crosses_scope(literature_claim, shared_artifact)
    assert not edge_crosses_scope(dl_claim, shared_artifact)
    assert not edge_crosses_scope(shared_artifact, dl_claim)

    # Verifies: same-scope edges are never crossings
    assert not edge_crosses_scope(
        vid("Session", "s1", MAIN_SCOPE), vid("Claim", "ccc", MAIN_SCOPE)
    )


def test_label_properties_cover_every_core_node_type():
    """
    Scenario: The viewer can label any core node without a hardcoded table

    Verifications:
    - every core label declares which property renders as its display label
    """
    # Verifies: the registry is complete, so view_query needs no literal of its own
    assert set(LABEL_PROPERTIES) == {"Session", "Thread", "Claim", "Source", "Artifact"}
