"""
Persisted visualization query model tests.

Interfaces: thalamus.plane.view_query.node_from_value_map,
            thalamus.plane.view_query.edge_from_value_map,
            thalamus.plane.view_query.persisted_node_details
Infrastructure: none
Scope: conversion of Gremlin property maps into stable canonical graph elements
"""

from gremlin_python.process.traversal import T

from thalamus.plane import view_query
from thalamus.plane.view_query import (
    edge_from_value_map,
    expand_subgraph,
    node_from_value_map,
    persisted_node_details,
    persisted_overview,
)


class _OverviewTraversal:
    """Minimal fluent traversal double for deterministic overview query results."""

    def __init__(self, data, label=None):
        self._data = data
        self._label = label
        self._limit = None

    def V(self, *_):
        return _OverviewTraversal(self._data)

    def has_label(self, label):
        self._label = label
        return self

    def has(self, *_):
        return self

    def order(self):
        return self

    def by(self, *_):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def value_map(self, *_):
        return self

    def to_list(self):
        values = self._data.get(self._label, [])
        return values[: self._limit] if self._limit is not None else values


class _NodeDetailsTraversal:
    """Minimal traversal double for a node map and aggregate edge counts."""

    def __init__(self, value_map, incoming_count, outgoing_count, operation="node"):
        self._value_map = value_map
        self._incoming_count = incoming_count
        self._outgoing_count = outgoing_count
        self._operation = operation

    def V(self, *_):
        return _NodeDetailsTraversal(self._value_map, self._incoming_count, self._outgoing_count)

    def limit(self, *_):
        return self

    def value_map(self, *_):
        return self

    def in_e(self):
        self._operation = "incoming"
        return self

    def out_e(self):
        self._operation = "outgoing"
        return self

    def count(self):
        return self

    def to_list(self):
        if self._operation == "incoming":
            return [self._incoming_count]
        if self._operation == "outgoing":
            return [self._outgoing_count]
        return [self._value_map]


def test_value_maps_preserve_stable_ids_properties_and_expandability():
    """
    Scenario: Convert a persisted Session value map for the graph explorer

    Requires:
    - value map: Gremlin value_map(True) shape
    - infrastructure: none

    Verifications:
    - stable persisted IDs, labels, and properties are retained in canonical nodes
    - persisted element kinds advertise that their undisplayed neighbors can expand
    """
    node = node_from_value_map(
        {
            T.id: "session:abc123",
            T.label: "Session",
            "session_id": ["abc123"],
            "summary": ["Implemented persisted explorer"],
            "timestamp": ["2026-07-10T12:00:00"],
            "project": ["graph-memory"],
        }
    )

    # Verifies: stable persisted IDs, labels, and properties are retained in canonical nodes
    assert node.id == "session:abc123"
    assert node.label == "Implemented persisted explorer"
    assert node.properties == {
        "session_id": "abc123",
        "summary": "Implemented persisted explorer",
        "timestamp": "2026-07-10T12:00:00",
        "project": "graph-memory",
    }
    # Verifies: persisted element kinds advertise that their undisplayed neighbors can expand
    assert node.expandable.incoming is True
    assert node.expandable.outgoing is True


def test_edge_value_maps_use_deterministic_endpoint_based_ids():
    """
    Scenario: Convert a persisted edge without a database-provided edge ID

    Requires:
    - value map: Gremlin edge value_map(True) shape
    - infrastructure: none

    Verifications:
    - edge IDs are stable from the known endpoints and relationship label
    - edge properties remain available to renderer-neutral clients
    """
    edge = edge_from_value_map(
        {T.id: "database-dependent-edge-id", T.label: "CONTAINS", "weight": [2]},
        source="session:abc123",
        target="decision:abc123:0",
    )

    # Verifies: edge IDs are stable from the known endpoints and relationship label
    assert edge.id == "session:abc123|CONTAINS|decision:abc123:0"
    assert edge.kind == "CONTAINS"
    # Verifies: edge properties remain available to renderer-neutral clients
    assert edge.properties == {"weight": 2}


def test_node_details_uses_persisted_edge_counts_not_visible_elements():
    """
    Scenario: Inspect a persisted node after the explorer has loaded only a subgraph

    Requires:
    - graph: traversal source returning a persisted node and aggregate edge counts
    - infrastructure: traversal double

    Observable via:
    - thalamus.plane.view_query.persisted_node_details

    Verifications:
    - the details response keeps the complete persisted node properties
    - relationship counters come from graph aggregate traversals
    """
    graph = _NodeDetailsTraversal(
        {
            T.id: "artifact:src/main.py",
            T.label: "Artifact",
            "identifier": ["src/main.py"],
            "type": ["file"],
        },
        incoming_count=8,
        outgoing_count=3,
    )

    details = persisted_node_details(graph, "artifact:src/main.py")

    # Verifies: the details response keeps the complete persisted node properties
    assert details is not None
    assert details.node.properties == {"identifier": "src/main.py", "type": "file"}
    # Verifies: relationship counters come from graph aggregate traversals
    assert details.incoming_count == 8
    assert details.outgoing_count == 3


def test_persisted_overview_groups_recent_sessions_and_active_threads():
    """
    Scenario: Build a bounded project-oriented persisted overview

    Requires:
    - graph: traversal source returning Session and Thread value maps
    - infrastructure: traversal double

    Observable via:
    - thalamus.plane.view_query.persisted_overview

    Verifications:
    - project nodes aggregate matching sessions and contain the bounded recent subset
    - active threads are included with their project context in the initial graph
    """
    graph = _OverviewTraversal(
        {
            "Session": [
                {
                    T.id: "session:latest",
                    T.label: "Session",
                    "summary": ["Latest graph work"],
                    "timestamp": ["2026-07-10T12:00:00"],
                    "project": ["graph-memory"],
                },
                {
                    T.id: "session:older",
                    T.label: "Session",
                    "summary": ["Older graph work"],
                    "timestamp": ["2026-07-09T12:00:00"],
                    "project": ["graph-memory"],
                },
            ],
            "Thread": [
                {
                    T.id: "thread:next-slice",
                    T.label: "Thread",
                    "thread_id": ["next-slice"],
                    "title": ["Finish the persisted explorer"],
                    "status": ["open"],
                    "project": ["graph-memory"],
                }
            ],
        }
    )

    view = persisted_overview(graph, per_project_session_limit=1, total_limit=10)
    node_ids = {node.id for node in view.nodes}
    edge_ids = {edge.id for edge in view.edges}

    # Verifies: project nodes aggregate matching sessions and contain the bounded recent subset
    assert {"project:graph-memory", "session:latest"} <= node_ids
    assert "session:older" not in node_ids
    assert "project:graph-memory|PROJECT_CONTAINS|session:latest" in edge_ids
    # Verifies: active threads are included with their project context in the initial graph
    assert "thread:next-slice" in node_ids
    assert "project:graph-memory|PROJECT_CONTAINS|thread:next-slice" in edge_ids


def test_expansion_returns_only_unknown_neighbors_with_explicit_limits(monkeypatch):
    """
    Scenario: Expand one persisted Session while retaining the client's loaded graph

    Requires:
    - graph: traversal source
    - infrastructure: patched bounded neighbor query

    Observable via:
    - thalamus.plane.view_query.expand_subgraph

    Verifications:
    - already visible neighbors are omitted while their newly observed relationship is returned
    - node and edge response caps report truncation rather than returning an unbounded graph
    """
    pairs = [
        {
            "edge": {T.label: "CONTAINS"},
            "node": {T.id: "decision:known", T.label: "Decision", "description": ["Known"]},
        },
        {
            "edge": {T.label: "CONTAINS"},
            "node": {T.id: "decision:new", T.label: "Decision", "description": ["New"]},
        },
        {
            "edge": {T.label: "CONTAINS"},
            "node": {T.id: "decision:later", T.label: "Decision", "description": ["Later"]},
        },
    ]
    monkeypatch.setattr(view_query, "_neighbor_pairs", lambda *_: pairs)

    view = expand_subgraph(
        object(),
        root_ids=["session:one"],
        direction="outgoing",
        visible_node_ids={"session:one", "decision:known"},
        node_limit=1,
        edge_limit=2,
    )

    # Verifies: already visible neighbors are omitted while their newly observed relationship is returned
    assert {node.id for node in view.nodes} == {"decision:new"}
    assert {edge.id for edge in view.edges} == {
        "session:one|CONTAINS|decision:known",
        "session:one|CONTAINS|decision:new",
    }
    # Verifies: node and edge response caps report truncation rather than returning an unbounded graph
    assert view.metadata.truncated is True
