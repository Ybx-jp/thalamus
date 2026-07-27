"""
Graph snapshot (durability flush) tests.

Interfaces: thalamus.substrate.snapshot.snapshot, snapshot_quietly
Infrastructure: none; fake traversal sources only
Scope: io()-step wiring, the raise-vs-warn split on failure
"""

import logging

import pytest

from thalamus.substrate.snapshot import (
    DEFAULT_SNAPSHOT_PATH,
    SnapshotError,
    snapshot,
    snapshot_quietly,
)


class FakeIoTraversal:
    def __init__(self, recorder, error=None):
        self.recorder = recorder
        self.error = error

    def write(self):
        self.recorder["wrote"] = True
        return self

    def iterate(self):
        if self.error:
            raise self.error
        self.recorder["iterated"] = True
        return self


class FakeGraphTraversalSource:
    def __init__(self, error=None):
        self.calls = {}
        self.error = error

    def io(self, path):
        self.calls["path"] = path
        return FakeIoTraversal(self.calls, self.error)


def test_snapshot_drives_io_write_to_the_configured_path():
    """
    Scenario: Flush the graph with no explicit path

    Requires:
    - infrastructure: none

    Verifications:
    - the io()-step targets the configured graphLocation
    - write() is modulated onto io() and the traversal is terminated
    """
    g = FakeGraphTraversalSource()

    written = snapshot(g)

    assert written == DEFAULT_SNAPSHOT_PATH
    assert g.calls["path"] == DEFAULT_SNAPSHOT_PATH
    assert g.calls["wrote"] is True
    # A lazy traversal would silently do nothing; the terminal step is the point.
    assert g.calls["iterated"] is True


def test_snapshot_honours_an_explicit_side_path():
    """
    Scenario: Take a side copy without touching the live graph file

    Requires:
    - infrastructure: none

    Verifications:
    - the supplied path is used verbatim
    """
    g = FakeGraphTraversalSource()

    assert snapshot(g, "/opt/gremlin-server/data/side-copy.kryo") == (
        "/opt/gremlin-server/data/side-copy.kryo"
    )
    assert g.calls["path"] == "/opt/gremlin-server/data/side-copy.kryo"


def test_snapshot_raises_with_the_path_in_the_message():
    """
    Scenario: The server cannot write the file

    Requires:
    - infrastructure: none

    Verifications:
    - the failure surfaces as SnapshotError, naming the path
    """
    g = FakeGraphTraversalSource(error=RuntimeError("Could not write file"))

    with pytest.raises(SnapshotError) as excinfo:
        snapshot(g)

    assert DEFAULT_SNAPSHOT_PATH in str(excinfo.value)


def test_snapshot_quietly_warns_instead_of_raising(caplog):
    """
    Scenario: A post-write flush fails

    Requires:
    - infrastructure: none

    Verifications:
    - no exception escapes, so a failed flush cannot report a successful write
      as a failed one
    - the operator is warned that durability was not achieved
    """
    g = FakeGraphTraversalSource(error=RuntimeError("disk full"))

    with caplog.at_level(logging.WARNING):
        assert snapshot_quietly(g) is False

    assert "not yet on disk" in caplog.text


def test_snapshot_quietly_reports_success():
    """
    Scenario: A post-write flush succeeds

    Requires:
    - infrastructure: none

    Verifications:
    - returns True and terminates the traversal
    """
    g = FakeGraphTraversalSource()

    assert snapshot_quietly(g) is True
    assert g.calls["iterated"] is True
