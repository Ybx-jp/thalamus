"""
Pending session visualization model tests.

Interfaces: thalamus.plane.view_model.session_to_graph_view
Infrastructure: none
Scope: complete rendering, stable relationships, and structured validation findings
"""

from pathlib import Path

import yaml

from thalamus.substrate.schema import SessionGraph
from thalamus.plane.view_model import session_to_graph_view

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
    assert (
        "thread:add-widget-cache|TOUCHES|missing:artifact:src/example/cache.py"
        in edge_ids
    )
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

    # Verifies: preview IDs match the deterministic IDs used by the graph writer
    assert {
        "session:fixture-session-0001",
        "decision:fixture-session-0001:0",
        "problem:fixture-session-0001:0",
        "solution:fixture-session-0001:0",
        "thread:add-widget-cache",
    } <= node_ids
    # Verifies: problem-to-solution and session-to-thread relationships preserve graph semantics
    assert {
        (
            "problem:fixture-session-0001:0|SOLVED_BY|"
            "solution:fixture-session-0001:0"
        ),
        "session:fixture-session-0001|SPAWNS|thread:add-widget-cache",
    } <= edge_ids
