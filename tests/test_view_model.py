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
    assert "artifact:fastmcp" in node_ids
    # Verifies: a missing artifact reference is represented by a visible placeholder and edge
    assert "missing:artifact:src/graph_memory/cli.py" in node_ids
    assert (
        "thread:add-render-flag|TOUCHES|missing:artifact:src/graph_memory/cli.py"
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
        "session:test-session-2026-07-09",
        "decision:test-session-2026-07-09:0",
        "problem:test-session-2026-07-09:0",
        "solution:test-session-2026-07-09:0",
        "thread:add-render-flag",
    } <= node_ids
    # Verifies: problem-to-solution and session-to-thread relationships preserve graph semantics
    assert {
        (
            "problem:test-session-2026-07-09:0|SOLVED_BY|"
            "solution:test-session-2026-07-09:0"
        ),
        "session:test-session-2026-07-09|SPAWNS|thread:add-render-flag",
    } <= edge_ids
