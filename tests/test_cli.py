"""
Graph Memory CLI viewer launch tests.

Interfaces: thalamus visualize FILE
Infrastructure: mocked Uvicorn server
Scope: pending-session viewer construction and launch configuration
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from thalamus import cli


def test_visualize_starts_local_viewer_with_pending_session(monkeypatch, capsys):
    """
    Scenario: Launch an interactive preview from session YAML

    Requires:
    - fixture: tests/fixtures/sample_session.yaml
    - infrastructure: mocked Uvicorn server

    Observable via:
    - uvicorn.run application and arguments
    - GET /api/previews/current

    Verifications:
    - visualize starts Uvicorn on the requested host and port
    - the launched application contains the requested pending session
    - --no-open suppresses browser launch
    """
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    def unexpected_browser_open(_url):
        raise AssertionError("browser must not open with --no-open")

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(cli.webbrowser, "open", unexpected_browser_open)
    args = SimpleNamespace(
        file=cli.Path("tests/fixtures/sample_session.yaml"),
        host="127.0.0.1",
        port=43123,
        no_open=True,
    )

    cli._cmd_visualize(args)

    # Verifies: visualize starts Uvicorn on the requested host and port
    assert captured["kwargs"] == {
        "host": "127.0.0.1",
        "port": 43123,
        "log_level": "warning",
    }
    client = TestClient(captured["app"])
    response = client.get("/api/previews/current")
    # Verifies: the launched application contains the requested pending session
    assert response.status_code == 200
    assert any(
        node["id"] == "scope:main:session:fixture-session-0001"
        for node in response.json()["nodes"]
    )
    # Verifies: --no-open suppresses browser launch
    assert "Thalamus viewer: http://127.0.0.1:43123" in capsys.readouterr().out


def test_visualize_without_file_connects_to_the_persisted_memory_graph(monkeypatch, capsys):
    """
    Scenario: Launch the memory explorer without a pending session file

    Requires:
    - infrastructure: mocked graph connection and Uvicorn server

    Observable via:
    - connect, close_connection, and Uvicorn application arguments

    Verifications:
    - visualize connects the configured persisted graph and injects it into the viewer
    - the graph connection is closed after the viewer server exits
    """
    graph = object()
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli, "connect", lambda url: graph)
    monkeypatch.setattr(cli, "close_connection", lambda connection: captured.setdefault("closed", connection))
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    args = SimpleNamespace(
        file=None,
        url="ws://graph.example.test/gremlin",
        host="127.0.0.1",
        port=43123,
        no_open=True,
    )

    cli._cmd_visualize(args)

    # Verifies: visualize connects the configured persisted graph and injects it into the viewer
    assert captured["app"].state.graph is graph
    assert captured["kwargs"]["port"] == 43123
    # Verifies: the graph connection is closed after the viewer server exits
    assert captured["closed"] is graph
    assert "Thalamus viewer: http://127.0.0.1:43123" in capsys.readouterr().out
