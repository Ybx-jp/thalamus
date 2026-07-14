"""
Graph writer traversal construction and diagnostics tests.

Interfaces: Gremlin merge_v option modulators, thalamus.substrate.writer._iterate
Infrastructure: none; fake traversals only
Scope: merge token encoding and contextual write failure reporting
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.traversal import Merge

from thalamus.substrate.writer import GraphWriteError, _iterate, _upsert_session_vertex


class FakeTraversal:
    def __init__(self, error=None):
        self.bytecode = "fake-bytecode"
        self.error = error
        self.options = []

    def option(self, key, value):
        self.options.append((key, value))
        return self

    def iterate(self):
        if self.error:
            raise self.error
        return self


class FakeGraphTraversalSource:
    def __init__(self, graph_traversal):
        self.graph_traversal = graph_traversal

    def merge_v(self, _values):
        return self.graph_traversal


def test_session_upsert_uses_merge_enum_tokens():
    """
    Scenario: Encode merge option modulators for a session upsert

    Requires:
    - infrastructure: none

    Verifications:
    - on-create and on-match options use Gremlin Merge tokens, not strings
    """
    graph_traversal = FakeTraversal()
    g = FakeGraphTraversalSource(graph_traversal)
    session = SimpleNamespace(
        session_id="test-session",
        timestamp=datetime(2026, 7, 9, tzinfo=UTC),
        tool=SimpleNamespace(value="cursor"),
        project="graph-memory",
        summary="Regression test",
    )

    _upsert_session_vertex(g, session)

    # Verifies: on-create and on-match options use Gremlin Merge tokens, not strings
    assert [key for key, _ in graph_traversal.options] == [
        Merge.on_create,
        Merge.on_match,
    ]


def test_iterate_reports_operation_target_and_server_details():
    """
    Scenario: Report a Gremlin server write failure

    Requires:
    - infrastructure: none

    Verifications:
    - write errors identify the failed operation, target, status, and server exception
    """
    server_error = GremlinServerError(
        {
            "code": 599,
            "message": "bad traversal",
            "attributes": {
                "exceptions": ["java.lang.IllegalStateException"],
                "stackTrace": "server stack",
            },
        }
    )

    with pytest.raises(GraphWriteError) as error:
        _iterate(FakeTraversal(server_error), "upsert Session", "session:test")

    message = str(error.value)
    # Verifies: write errors identify the failed operation, target, status, and server exception
    assert "upsert Session `session:test` failed" in message
    assert "Gremlin server 599: bad traversal" in message
    assert "java.lang.IllegalStateException" in message
