"""
MCP server policy tests — what the server decides for itself, not per call.

Interfaces: harness.mcp_server.knowledge_scopes, harness.mcp_server._connect and the
tool guard that reads its result
Infrastructure: a temporary config directory via THALAMUS_CONFIG_DIR, and one TCP
connect to a port nothing listens on
Scope: the ambient knowledge surface (docs/02). The pin is resolved once at process
start and cannot change under a running server, but the roster can — manifests are
added to config/experts/ while servers are running. Plus what a tool returns when
the graph is down, which is the first thing a new install hits.
"""

import pytest

from thalamus.harness import mcp_server


@pytest.fixture
def roster(tmp_path, monkeypatch):
    """A manifest directory this test owns, and a helper that adds scopes to it."""
    experts = tmp_path / "experts"
    experts.mkdir()
    monkeypatch.setenv("THALAMUS_CONFIG_DIR", str(tmp_path))

    def add(*scopes: str) -> None:
        for scope in scopes:
            (experts / f"{scope}.yaml").write_text(f"scope: {scope}\n")

    return add


def test_knowledge_scopes_excludes_the_pin(roster, monkeypatch):
    roster("literature", "qe", "teacher")
    monkeypatch.setattr(mcp_server, "SCOPE", "qe")

    assert mcp_server.knowledge_scopes() == ["literature", "teacher"]


def test_knowledge_scopes_sees_a_manifest_added_after_startup(roster, monkeypatch):
    """A running server must not serve a roster frozen at its own launch date.

    This is the regression: assembling the list once at import meant a server that
    had been up since before a scope was added served every session it owned a graph
    with that expert's knowledge missing — silently, since an absent scope reads as
    an expert that simply knows nothing rather than as an error.
    """
    roster("literature", "qe")
    monkeypatch.setattr(mcp_server, "SCOPE", "main")
    assert mcp_server.knowledge_scopes() == ["literature", "qe"]

    roster("dl")  # the roster grows under a process that is already running

    assert mcp_server.knowledge_scopes() == ["dl", "literature", "qe"]


class TestTheGraphIsDown:
    """The first-run case: an agent session opened before `docker compose up -d`.

    Every tool body is `try: … finally: _close(g)` with no `except`, so whatever
    `_connect` does not catch propagates to FastMCP and reaches the operator as the
    driver's transport error relayed through the model. `_connect` catches it because
    `connect` probes the port instead of returning a source that fails later.
    """

    DEAD = "ws://localhost:9/gremlin"

    def test_connect_returns_the_diagnosis_instead_of_a_source(self, monkeypatch):
        monkeypatch.setattr(mcp_server, "GRAPH_URL", self.DEAD)
        result = mcp_server._connect()
        assert isinstance(result, str)
        assert "docker compose up -d" in result

    def test_a_tool_answers_with_it_rather_than_raising(self, monkeypatch):
        """The `isinstance(g, str)` guard at the head of each tool is what turns that
        into an answer; it was unreachable for this case until the probe existed."""
        monkeypatch.setattr(mcp_server, "GRAPH_URL", self.DEAD)
        assert "docker compose up -d" in mcp_server.memory_recall("anything")
        assert "docker compose up -d" in mcp_server.memory_open_threads()
