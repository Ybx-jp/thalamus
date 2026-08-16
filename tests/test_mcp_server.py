"""
MCP server policy tests — what the server decides for itself, not per call.

Interfaces: harness.mcp_server.knowledge_scopes
Infrastructure: none; a temporary config directory via THALAMUS_CONFIG_DIR
Scope: the ambient knowledge surface (docs/02). The pin is resolved once at process
start and cannot change under a running server, but the roster can — manifests are
added to config/experts/ while servers are running.
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
