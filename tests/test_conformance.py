"""
Federation-contract conformance tests.

Interfaces: thalamus.contract.conformance.check_session
Infrastructure: none
Scope: obligations are enforced at write time, not filtered at read time
"""

from datetime import datetime

import pytest

from thalamus.contract.conformance import check_session, prune_orphan_artifacts
from thalamus.substrate.schema import (
    Artifact,
    ArtifactType,
    Decision,
    Provenance,
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


def test_orphan_artifacts_are_rejected_not_quietly_dropped():
    """
    Scenario: An artifact is declared but never referenced

    Verifications:
    - the contract check reports the orphan by name
    """
    session = _session(
        artifacts=[Artifact(identifier="src/lonely.py", type=ArtifactType.FILE)],
    )

    issues = check_session(session)

    # Verifies: rejected at write time, with the offending node named
    assert any("src/lonely.py" in issue for issue in issues)


def test_a_fully_connected_session_satisfies_the_contract():
    """
    Scenario: Every declared artifact is referenced by a claim

    Verifications:
    - no issues are raised
    """
    session = _session(
        artifacts=[Artifact(identifier="src/used.py", type=ArtifactType.FILE)],
        decisions=[
            Decision(description="d", rationale="r", artifacts=["src/used.py"]),
        ],
    )

    # Verifies: a conformant subgraph passes cleanly
    assert check_session(session) == []


def test_provenance_without_a_source_is_rejected():
    """
    Scenario: A node supplies a provenance envelope with an empty source

    Verifications:
    - the contract refuses it — "no provenance, no write"
    """
    session = _session(
        artifacts=[
            Artifact(
                identifier="src/used.py",
                type=ArtifactType.FILE,
                provenance=Provenance(tier=Tier.CURATED, source=""),
            )
        ],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/used.py"])],
    )

    issues = check_session(session)

    # Verifies: the gate fires at write time rather than being cleaned up later
    assert any("no provenance, no write" in issue for issue in issues)


def test_a_pinned_sessions_graph_is_legal_in_an_expert_scope():
    """
    Scenario: A whole session distilled into an expert scope (a pinned session —
    "the process is the pin")

    This was always legal — Session is generically scoped — but pinning makes it
    load-bearing: the SessionEnd hook now passes --scope, so expert-scoped episodic
    SessionGraphs must keep passing the write gate unchanged.
    """
    session = _session(
        scope="literature",
        artifacts=[Artifact(identifier="src/used.py", type=ArtifactType.FILE)],
        decisions=[
            Decision(description="d", rationale="r", artifacts=["src/used.py"]),
        ],
    )

    assert check_session(session) == []


def test_a_session_must_declare_a_scope():
    """
    Scenario: A session carries an empty scope

    Verifications:
    - the contract refuses it — every node belongs to exactly one scope
    """
    session = _session(scope="")

    # Verifies: scope is not optional, even though it defaults
    assert any("no scope" in issue for issue in check_session(session))


@pytest.mark.parametrize("scope", ["main", "literature"])
def test_prune_removes_only_unreferenced_artifacts(scope):
    """
    Scenario: Prepare a session for rendering, in any scope

    Verifications:
    - referenced artifacts survive, orphans do not
    """
    session = _session(
        scope=scope,
        artifacts=[
            Artifact(identifier="src/used.py", type=ArtifactType.FILE),
            Artifact(identifier="src/orphan.py", type=ArtifactType.FILE),
        ],
        decisions=[Decision(description="d", rationale="r", artifacts=["src/used.py"])],
    )

    pruned = prune_orphan_artifacts(session)

    # Verifies: pruning is by reachability, not by position or scope
    assert [a.identifier for a in pruned.artifacts] == ["src/used.py"]
