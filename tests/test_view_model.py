"""
Pending session visualization model tests.

Interfaces: thalamus.plane.view_model.session_to_graph_view
Infrastructure: none
Scope: complete rendering, stable relationships, and structured validation findings
"""

from pathlib import Path

import yaml

from thalamus.contract.ontology import vid
from thalamus.plane.view_model import session_to_graph_view
from thalamus.substrate.schema import SessionGraph

FIXTURES = Path(__file__).parent / "fixtures"


def test_session_preview_keeps_orphans_and_missing_references_visible():
    """
    Scenario: Convert a semantically invalid pending session for visual inspection

    Requires:
    - fixture: sample_session.yaml
    - infrastructure: none

    Verifications:
    - every declared artifact remains in the graph, including orphan artifacts
    - a missing artifact reference is represented by a visible placeholder and edge
    - findings identify both the orphan and the missing reference
    """
    data = yaml.safe_load((FIXTURES / "sample_session.yaml").read_text())
    session = SessionGraph(**data)

    view = session_to_graph_view(session)
    node_ids = {node.id for node in view.nodes}
    edge_ids = {edge.id for edge in view.edges}
    finding_codes = {finding.code for finding in view.findings}

    # Verifies: every declared artifact remains in the graph, including orphan artifacts
    assert "artifact:examplelib" in node_ids
    # Verifies: a missing artifact reference is represented by a visible placeholder and edge
    assert "missing:artifact:src/example/cache.py" in node_ids
    thread_id = vid("Thread", "add-widget-cache", session.scope)
    assert f"{thread_id}|TOUCHES|missing:artifact:src/example/cache.py" in edge_ids
    # Verifies: findings identify both the orphan and the missing reference
    assert {"orphan_artifact", "missing_artifact_reference"} <= finding_codes


def test_session_preview_uses_writer_compatible_ids_and_relationships():
    """
    Scenario: Convert normal session entities and relationships

    Requires:
    - fixture: sample_session.yaml
    - infrastructure: none

    Verifications:
    - preview IDs match the deterministic IDs used by the graph writer
    - problem-to-solution and session-to-thread relationships preserve graph semantics
    """
    data = yaml.safe_load((FIXTURES / "sample_session.yaml").read_text())
    session = SessionGraph(**data)

    view = session_to_graph_view(session)
    node_ids = {node.id for node in view.nodes}
    edge_ids = {edge.id for edge in view.edges}

    # Verifies: preview IDs match the deterministic IDs used by the graph writer.
    # Derived from the ontology, never hardcoded — claims are content-addressed, so a
    # literal here would be a hash nobody could maintain.
    scope = session.scope
    session_node = vid("Session", "fixture-session-0001", scope)
    thread_node = vid("Thread", "add-widget-cache", scope)
    problem_node = vid("Claim", session.problems[0].content_id(), scope)
    solution_node = vid("Claim", session.solutions[0].content_id(), scope)
    decision_node = vid("Claim", session.decisions[0].content_id(), scope)

    assert {session_node, decision_node, problem_node, solution_node, thread_node} <= node_ids
    # Verifies: claims are one label discriminated by kind, not three labels
    assert {node.kind for node in view.nodes if node.id == decision_node} == {"Claim"}
    assert {
        node.properties["kind"] for node in view.nodes if node.id == decision_node
    } == {"decision"}
    # Verifies: problem-to-solution and session-to-thread relationships preserve graph semantics
    assert {
        f"{problem_node}|SOLVED_BY|{solution_node}",
        f"{session_node}|SPAWNS|{thread_node}",
    } <= edge_ids
