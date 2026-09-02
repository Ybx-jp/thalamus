"""
Schema tests: content-addressed claim identity and the provenance envelope.

Interfaces: thalamus.substrate.schema.Claim.content_id, SessionGraph.default_provenance
Infrastructure: none
Scope: stable claim IDs and tier-1-by-construction provenance
"""

from datetime import datetime

from thalamus.contract.ontology import MAIN_SCOPE
from thalamus.substrate.schema import (
    Decision,
    Problem,
    ProblemCategory,
    SessionGraph,
    Tier,
    Tool,
)


def _session(**overrides) -> SessionGraph:
    defaults = dict(
        session_id="s1",
        timestamp=datetime(2026, 1, 1),
        tool=Tool.CLAUDE_CODE,
        summary="A session.",
    )
    return SessionGraph(**{**defaults, **overrides})


def test_claim_identity_is_content_addressed_not_positional():
    """
    Scenario: Re-extract a session with its claims reordered

    Verifications:
    - a claim's ID depends on its content, not its index
    - reordering claims does not repoint IDs at different nodes

    The old scheme was `decision:<session_id>:<index>`. Under it, reordering the YAML
    silently overwrote *different* nodes, and no claim could be cited, superseded, or
    contradicted — fatal for a system whose demo is "walk from a belief to its source".
    """
    first = Decision(description="Use TinkerGraph", rationale="Real traversals")
    second = Decision(description="Use Gremlin", rationale="Standard query language")

    original = _session(decisions=[first, second])
    reordered = _session(decisions=[second, first])

    # Verifies: identity travels with content, not position
    assert original.decisions[0].content_id() == reordered.decisions[1].content_id()
    assert original.decisions[1].content_id() == reordered.decisions[0].content_id()
    assert first.content_id() != second.content_id()


def test_the_same_claim_in_two_sessions_converges_on_one_node():
    """
    Scenario: Two different sessions assert the identical claim

    Verifications:
    - the claim's ID is independent of the session that asserted it

    This convergence is deliberate: it is how "this keeps coming up" becomes a graph fact
    (two CONTAINS edges into one Claim) rather than a human impression, and it is exactly
    how Artifact has always behaved.
    """
    claim = Decision(description="Use TinkerGraph", rationale="Real traversals")
    session_a = _session(session_id="a", decisions=[claim.model_copy()])
    session_b = _session(session_id="b", decisions=[claim.model_copy()])

    # Verifies: content-addressed IDs do not smuggle the session in
    assert session_a.decisions[0].content_id() == session_b.decisions[0].content_id()


def test_identity_is_the_assertion_not_its_supporting_fields():
    """
    Scenario: The same decision re-asserted with a revised rationale; a genuinely
    different decision; cosmetic whitespace/punctuation drift

    Verifications:
    - a revised rationale converges on the SAME node (latest-wins property update)
    - a different assertion is a different node
    - whitespace and a trailing period do not fork identity

    This reverses the original "substance is part of identity" design, on evidence:
    the first full-corpus run measured ZERO convergences across 1,089 claims
    because no two sessions reproduce a rationale byte-for-byte. The assertion is the
    identity; everything else is a property. Decision log 2026-07-15.
    """
    revised = Decision(description="Use TinkerGraph", rationale="Already have the infra")
    original = Decision(description="Use TinkerGraph", rationale="Real traversals")
    different = Decision(description="Use Neo4j", rationale="Real traversals")
    cosmetic = Decision(description="  Use   TinkerGraph.", rationale="Real traversals")

    assert original.content_id() == revised.content_id()
    assert original.content_id() != different.content_id()
    assert original.content_id() == cosmetic.content_id()


def test_claim_subtypes_share_one_label_and_differ_by_kind():
    """
    Scenario: Decisions, problems, and solutions coexist in one session

    Verifications:
    - all claims are reachable through a single accessor, whatever the subtype
    - each carries its discriminating kind
    """
    session = _session(
        decisions=[Decision(description="d", rationale="r")],
        problems=[Problem(description="p", category=ProblemCategory.BUG)],
    )

    # Verifies: consumers depend on Claim, not on its subtypes
    assert [claim.kind for claim in session.claims()] == ["decision", "problem"]


def test_session_extractions_are_tier_one_by_construction():
    """
    Scenario: A session is extracted without stating any provenance

    Verifications:
    - the derived envelope is tier-1, sourced to the session

    Provenance is stamped, not asked for: a session extraction IS the agent's own lived
    experience, so its origin is derivable. Feeds writing third-party content must supply
    it explicitly instead.
    """
    session = _session(session_id="abc")
    provenance = session.default_provenance()

    # Verifies: tier-1, and the source names the session it came from
    assert provenance.tier is Tier.FIRST_PARTY
    assert provenance.source == "session:abc"
    assert provenance.derived_from == []


def test_scope_defaults_to_main_and_is_independent_of_project():
    """
    Scenario: A session declares a project but no expert pin

    Verifications:
    - scope defaults to the connective main plane
    - project and scope are separate fields — which repo vs. which expert
    """
    session = _session(project="thalamus")

    # Verifies: orthogonal axes, not one dressed as the other
    assert session.scope == MAIN_SCOPE
    assert session.project == "thalamus"


def test_a_solution_says_how_it_ended_and_a_decision_what_it_turned_down():
    """
    Scenario: The outcome fields stage 1 adds to the episodic subtypes

    Verifications:
    - `outcome_kind` is the four-bucket enum the ledgers needed, and optional
    - `anchors` and `references` default empty rather than being required, so a
      model that omits them costs nothing under `partition_valid`
    - a rejected alternative is a model of its own with the same optional fields
    - the rejected kind is namespaced beneath its scope, never a core kind
    """
    from thalamus.substrate.schema import (
        Alternative,
        ClaimKind,
        Decision,
        OutcomeKind,
        Solution,
        is_rejected_kind,
        rejected_kind,
    )

    assert {k.value for k in OutcomeKind} == {"unresolved", "reversed", "rejected", "residual"}

    solution = Solution(description="Widened the shutter", approach="edit", worked=False)
    assert solution.outcome_kind is None
    assert solution.anchors == [] and solution.references == []
    failed = Solution(
        description="Widened the shutter", approach="edit", worked=False,
        outcome_kind="reversed", anchors=["a" * 36],
    )
    assert failed.outcome_kind is OutcomeKind.REVERSED

    decision = Decision(
        description="Chose the carry arm", rationale="continuity",
        alternatives=[Alternative(description="the cut arm", reason="loses the object")],
    )
    assert decision.alternatives[0].references == []
    # Identity is still (kind, description): the alternatives do not move it.
    assert decision.content_id() == Decision(
        description="Chose the carry arm", rationale="other"
    ).content_id()

    assert rejected_kind("designer") == "designer/rejected"
    assert is_rejected_kind("designer/rejected")
    assert not is_rejected_kind(ClaimKind.DECISION.value)
    assert "designer/rejected" not in {k.value for k in ClaimKind}
