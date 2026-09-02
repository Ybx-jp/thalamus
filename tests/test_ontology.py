"""
Core ontology and scope-legality tests.

Interfaces: thalamus.contract.ontology.vid, scope_of, edge_crosses_scope
Infrastructure: none
Scope: the global-Artifact carve-out and the scope segment in vertex IDs
"""

from thalamus.contract.ontology import (
    GLOBAL_LABELS,
    LABEL_PROPERTIES,
    MAIN_SCOPE,
    edge_crosses_scope,
    scope_of,
    vid,
)


def test_artifact_and_agent_are_the_global_node_types():
    """
    Scenario: Distinguish the global join keys from scoped node types

    Verifications:
    - Artifact and Agent vertex IDs carry no scope segment
    - Session, Thread, and Claim vertex IDs are scoped
    """
    # Verifies: Artifact is global — one vertex per identifier, shared by every scope
    assert "Artifact" in GLOBAL_LABELS
    assert vid("Artifact", "src/foo.py") == "artifact:src/foo.py"
    assert vid("Artifact", "src/foo.py", scope="literature") == "artifact:src/foo.py"

    # Verifies: Agent is global — one vertex per identity, whatever scope it acts in
    assert "Agent" in GLOBAL_LABELS
    assert vid("Agent", "operator") == "agent:operator"
    assert vid("Agent", "operator", scope="homelab") == "agent:operator"

    # Verifies: everything else is scoped
    for label in ("Session", "Thread", "Claim"):
        assert label not in GLOBAL_LABELS
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
    the cross-scope density metric that grades roster granularity (the split/merge signal)
    would measure "same repo" rather than "same domain" and be useless.
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
    Scenario: A consumer can label any core node without a hardcoded table

    Verifications:
    - every core label declares which property renders as its display label
    """
    # Verifies: the registry is complete, so a reader needs no literal of its own
    assert set(LABEL_PROPERTIES) == {
        "Session", "Thread", "Claim", "Source", "Artifact", "Trace", "Entity",
        "Exchange", "Chunk", "Agent",
    }


def test_an_agent_closing_a_thread_in_any_scope_is_not_a_crossing():
    """
    Scenario: The operator approves the close of a thread that lives in an expert
    scope, from outside that scope

    Verifications:
    - `Agent -> Thread` is not a scope crossing, whatever scope the thread is in

    This is what makes the operator-approved close expressible without touching
    `RESOLVES.may_cross_scope`. The incident that demands it is resolution
    evidence for one scope's thread landing in another scope's session; a scoped
    closer would need an illegal edge, and the legal-looking alternatives are a bare
    status flip (nothing for an adjudication to walk) or a Session for a conversation
    that never happened. The partition guards a channel for *content*, and an Agent
    carries none — only the identity that acted.
    """
    operator = vid("Agent", "operator")

    # Verifies: neither direction is a crossing, in any scope
    for scope in ("homelab", "literature", MAIN_SCOPE):
        thread = vid("Thread", "some-thread", scope)
        assert not edge_crosses_scope(operator, thread)
        assert not edge_crosses_scope(thread, operator)


def test_uses_is_a_qualified_claim_to_knowledge_edge_that_may_cross_scope():
    """
    Scenario: The edge a decision's reference becomes, as the ontology declares it

    Verifications:
    - USES leaves a Claim and lands on a Claim or a Chunk, nothing else
    - it may cross scope: an episodic claim in one expert reasons with a literature
      claim served from another, by ID, and the edge records that
    - it is qualified — role and the verification stamp are declared properties, so
      `contract check` can ask the live graph whether anything writes them

    The two-hop substitute (ABOUT to a shared Entity, ANCHORS to a shared Chunk)
    expresses co-topicality, not use; DERIVED_FROM reaches only Source. Neither says
    "this claim used that knowledge item as a reason", which is the one thing this
    edge exists to say (lab/067 §9.2).
    """
    from thalamus.contract.ontology import EDGES_BY_LABEL

    uses = EDGES_BY_LABEL["USES"]

    assert uses.from_labels == ("Claim",)
    assert uses.to_labels == ("Claim", "Chunk")
    assert uses.strict_endpoints
    assert uses.may_cross_scope
    assert set(uses.properties) >= {"role", "reason", "verified", "verifier", "verified_by"}
    assert edge_crosses_scope(vid("Claim", "aaa", "designer"), vid("Claim", "bbb", "literature"))
