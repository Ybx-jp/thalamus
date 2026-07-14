"""
Local visualization HTTP API tests.

Interfaces: GET /api/health, GET /api/previews/current, POST /api/previews,
            GET /api/overview, POST /api/subgraphs/expand, GET /api/nodes/{node_id}
Infrastructure: in-process FastAPI application
Scope: session-preview lifecycle and canonical graph responses
"""

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from thalamus.substrate.schema import SessionGraph
from thalamus.plane.view_model import Expandable, GraphView, NodeDetails, ViewMetadata, ViewNode
from thalamus.plane.web import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def _sample_session() -> SessionGraph:
    data = yaml.safe_load((FIXTURES / "sample_session.yaml").read_text())
    return SessionGraph(**data)


def test_initial_session_is_available_to_the_viewer():
    """
    Scenario: Start the local service from a CLI-provided session

    Requires:
    - fixture: sample_session.yaml
    - infrastructure: in-process FastAPI application

    Observable via:
    - GET /api/previews/current

    Verifications:
    - the current-preview endpoint returns the CLI-provided session graph
    - the response reports structured validation findings
    """
    client = TestClient(create_app(_sample_session()))

    response = client.get("/api/previews/current")

    assert response.status_code == 200
    body = response.json()
    # Verifies: the current-preview endpoint returns the CLI-provided session graph
    assert body["metadata"]["mode"] == "session_preview"
    assert any(node["id"].startswith("session:fixture-session") for node in body["nodes"])
    # Verifies: the response reports structured validation findings
    assert any(finding["code"] == "orphan_artifact" for finding in body["findings"])


def test_posted_session_becomes_the_current_preview():
    """
    Scenario: Create a preview through the HTTP API

    Requires:
    - fixture: sample_session.yaml
    - infrastructure: in-process FastAPI application

    Modifies:
    - in-memory current preview (discarded with application)

    Observable via:
    - POST /api/previews
    - GET /api/previews/current

    Verifications:
    - POST /api/previews accepts a SessionGraph JSON object and returns its graph
    - the posted graph becomes the current preview
    """
    client = TestClient(create_app())
    payload = _sample_session().model_dump(mode="json")

    response = client.post("/api/previews", json=payload)

    # Verifies: POST /api/previews accepts a SessionGraph JSON object and returns its graph
    assert response.status_code == 200
    assert response.json()["metadata"]["visible_node_count"] > 0
    current = client.get("/api/previews/current")
    # Verifies: the posted graph becomes the current preview
    assert current.status_code == 200
    assert current.json() == response.json()


def test_missing_current_preview_returns_not_found():
    """
    Scenario: Open the preview API without loading a session

    Requires:
    - infrastructure: in-process FastAPI application

    Observable via:
    - GET /api/previews/current

    Verifications:
    - the API reports that no pending preview is loaded
    """
    client = TestClient(create_app())

    response = client.get("/api/previews/current")

    # Verifies: the API reports that no pending preview is loaded
    assert response.status_code == 404
    assert response.json()["detail"] == "No session preview is loaded"


def test_persisted_overview_uses_the_server_graph(monkeypatch):
    """
    Scenario: Load the persisted memory explorer's initial graph

    Requires:
    - infrastructure: in-process FastAPI application
    - graph: injected traversal source

    Observable via:
    - GET /api/overview

    Verifications:
    - overview parameters are forwarded to the bounded persisted-graph query
    - the query response is returned as the canonical explorer graph
    """
    graph = object()
    captured = {}
    expected = GraphView(
        nodes=[],
        edges=[],
        findings=[],
        metadata=ViewMetadata(mode="overview", visible_node_count=0, visible_edge_count=0),
    )

    def fake_overview(graph_source, **kwargs):
        captured["graph"] = graph_source
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("thalamus.plane.web.persisted_overview", fake_overview)
    client = TestClient(create_app(graph=graph))

    response = client.get("/api/overview?project=graph-memory&per_project_session_limit=3")

    # Verifies: overview parameters are forwarded to the bounded persisted-graph query
    assert captured == {
        "graph": graph,
        "kwargs": {
            "project": "graph-memory",
            "start": None,
            "end": None,
            "per_project_session_limit": 3,
            "total_limit": 100,
        },
    }
    # Verifies: the query response is returned as the canonical explorer graph
    assert response.status_code == 200
    assert response.json()["metadata"]["mode"] == "overview"


def test_expansion_passes_known_elements_and_enforces_request_limits(monkeypatch):
    """
    Scenario: Expand one visible persisted node

    Requires:
    - infrastructure: in-process FastAPI application
    - graph: injected traversal source

    Observable via:
    - POST /api/subgraphs/expand

    Verifications:
    - the endpoint forwards roots, visible elements, and bounded expansion limits
    - the query response is returned as a canonical expansion graph
    """
    graph = object()
    captured = {}
    expected = GraphView(
        nodes=[],
        edges=[],
        findings=[],
        metadata=ViewMetadata(mode="expansion", visible_node_count=0, visible_edge_count=0),
    )

    def fake_expand(graph_source, **kwargs):
        captured["graph"] = graph_source
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr("thalamus.plane.web.expand_subgraph", fake_expand)
    client = TestClient(create_app(graph=graph))

    response = client.post(
        "/api/subgraphs/expand",
        json={
            "root_ids": ["session:one"],
            "direction": "outgoing",
            "visible_node_ids": ["session:one"],
            "visible_edge_ids": ["known-edge"],
            "node_limit": 10,
            "edge_limit": 20,
        },
    )

    # Verifies: the endpoint forwards roots, visible elements, and bounded expansion limits
    assert captured == {
        "graph": graph,
        "kwargs": {
            "root_ids": ["session:one"],
            "direction": "outgoing",
            "visible_node_ids": {"session:one"},
            "visible_edge_ids": {"known-edge"},
            "node_limit": 10,
            "edge_limit": 20,
        },
    }
    # Verifies: the query response is returned as a canonical expansion graph
    assert response.status_code == 200
    assert response.json()["metadata"]["mode"] == "expansion"


def test_node_details_reports_graph_wide_relationship_counts(monkeypatch):
    """
    Scenario: Inspect a persisted node that has relationships outside the loaded subgraph

    Requires:
    - infrastructure: in-process FastAPI application
    - graph: injected traversal source

    Observable via:
    - GET /api/nodes/{node_id}

    Verifications:
    - the node-details endpoint delegates the persisted node ID to the graph query
    - incoming and outgoing counts are returned independently of rendered graph edges
    """
    graph = object()
    expected = NodeDetails(
        node=ViewNode(
            id="session:one",
            kind="Session",
            label="One",
            expandable=Expandable(incoming=True, outgoing=True),
        ),
        incoming_count=7,
        outgoing_count=11,
    )
    captured = {}

    def fake_node_details(graph_source, node_id):
        captured["graph"] = graph_source
        captured["node_id"] = node_id
        return expected

    monkeypatch.setattr("thalamus.plane.web.persisted_node_details", fake_node_details)
    client = TestClient(create_app(graph=graph))

    response = client.get("/api/nodes/session:one")

    # Verifies: the node-details endpoint delegates the persisted node ID to the graph query
    assert captured == {"graph": graph, "node_id": "session:one"}
    # Verifies: incoming and outgoing counts are returned independently of rendered graph edges
    assert response.status_code == 200
    assert response.json()["incoming_count"] == 7
    assert response.json()["outgoing_count"] == 11


def test_built_frontend_is_served_with_the_preview_api():
    """
    Scenario: Open the packaged browser application

    Requires:
    - frontend assets built into src/thalamus/plane/static
    - infrastructure: in-process FastAPI application

    Observable via:
    - GET /

    Verifications:
    - the backend serves the packaged Graph Memory Viewer application
    """
    client = TestClient(create_app(_sample_session()))

    response = client.get("/")

    # Verifies: the backend serves the packaged Graph Memory Viewer application
    assert response.status_code == 200
    assert "<title>Graph Memory Viewer</title>" in response.text
