"""Named-snapshot registry tests (R1, the reproducibility floor; lab/034).

Interfaces: thalamus.eval.snapshots — name validation, immutability, the registry
            ledger, hash verification.
Infrastructure: the registry path is redirected to tmp_path; hashing and the
            container are stubbed. `serve()` is NOT exercised here — it starts a
            real Docker container against the real data volume, which is an
            integration concern, and a stubbed container would test the stub.
Scope: the promises a published citation rests on — that a snapshot name means one
       state forever, and that the file still hashes to what was cited.
"""

import json

import pytest

from thalamus.eval import snapshots


@pytest.fixture
def registry(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.jsonl"
    monkeypatch.setattr(snapshots, "REGISTRY", path)
    return path


@pytest.fixture
def stub_server(monkeypatch):
    """A server whose files exist and hash to a known value."""
    state = {"hash": "a" * 64, "size": 1234, "written": []}
    monkeypatch.setattr(snapshots, "_sha256_and_size", lambda path: (state["hash"], state["size"]))
    monkeypatch.setattr(snapshots, "_file_exists", lambda path: path in state["written"])
    monkeypatch.setattr(snapshots, "_git_ref", lambda: "deadbee")
    return state


def _fake_graph(monkeypatch, state, vertices=100, edges=200):
    class FakeCount:
        def __init__(self, value):
            self.value = value

        def count(self):
            return self

        def next(self):
            return self.value

    class FakeGraph:
        def V(self):
            return FakeCount(vertices)

        def E(self):
            return FakeCount(edges)

    monkeypatch.setattr(snapshots, "connect", lambda url=None: FakeGraph())
    monkeypatch.setattr(snapshots, "close_connection", lambda g: None)
    monkeypatch.setattr(
        snapshots, "snapshot", lambda g, path: state["written"].append(path) or path
    )


def test_a_pinned_snapshot_records_what_it_pinned(registry, stub_server, monkeypatch):
    """
    Scenario: the operator pins the current graph.

    Verification: the registry row carries the counts, the hash, the byte size and
    the git ref — everything a later reader needs to tell whether the number they
    are looking at came from this state.
    """
    _fake_graph(monkeypatch, stub_server, vertices=5591, edges=13849)
    row = snapshots.take("post-purge-baseline", note="after the lab/033 purge")

    assert row.vertices == 5591 and row.edges == 13849
    assert row.sha256 == "a" * 64 and row.git_ref == "deadbee"
    assert row.server_path.endswith("/post-purge-baseline.kryo")

    stored = json.loads(registry.read_text().strip())
    assert stored["name"] == "post-purge-baseline"
    assert stored["note"] == "after the lab/033 purge"


def test_a_name_that_has_been_cited_cannot_be_repinned(registry, stub_server, monkeypatch):
    """A published number cites a name. If the name can be re-pointed at a later
    state, the citation silently stops meaning what it meant."""
    _fake_graph(monkeypatch, stub_server)
    snapshots.take("baseline")
    with pytest.raises(snapshots.SnapshotError, match="immutable"):
        snapshots.take("baseline")


def test_an_unregistered_file_blocks_the_name(registry, stub_server, monkeypatch):
    """A `.kryo` already on the server under this name is someone else's state.
    Writing over it would destroy evidence rather than pin any."""
    _fake_graph(monkeypatch, stub_server)
    stub_server["written"].append(snapshots.server_path("orphan"))
    with pytest.raises(snapshots.SnapshotError, match="not in the registry"):
        snapshots.take("orphan")


@pytest.mark.parametrize(
    "name", ["", "ab", "Has-Capitals", "under_scores", "has space", "trailing/slash", "x" * 65]
)
def test_names_that_would_be_quoted_wrong_somewhere_are_refused(
    registry, stub_server, monkeypatch, name
):
    """The name is both a filename and a citation. Restricting it beats escaping it
    in the two places it travels."""
    _fake_graph(monkeypatch, stub_server)
    with pytest.raises(snapshots.SnapshotError, match="invalid snapshot name"):
        snapshots.take(name)


def test_verify_catches_a_snapshot_that_no_longer_hashes_to_its_citation(
    registry, stub_server, monkeypatch
):
    """
    Scenario: the file behind a cited snapshot changes.

    Verification: `verify()` says so. Without this, a re-run against a mutated
    snapshot reproduces a number that was never computed on that state — the
    failure mode that makes pinning worse than not pinning, because it looks
    reproducible.
    """
    _fake_graph(monkeypatch, stub_server)
    snapshots.take("pinned")
    assert snapshots.verify("pinned") is True

    stub_server["hash"] = "b" * 64
    assert snapshots.verify("pinned") is False


def test_adopting_a_file_whose_name_disagrees_with_the_registry_is_refused(
    registry, stub_server, monkeypatch
):
    """An adopted row whose on-disk name differs from its registry name would
    resolve to the wrong file the moment anyone served it by name."""
    stub_server["written"].append(f"{snapshots.SERVER_DATA_DIR}/some-old-dump.kryo")
    with pytest.raises(snapshots.SnapshotError, match="must be named"):
        snapshots.adopt("pre-purge", filename="some-old-dump.kryo")


def test_find_names_what_is_registered_when_it_misses(registry, stub_server, monkeypatch):
    _fake_graph(monkeypatch, stub_server)
    snapshots.take("one")
    with pytest.raises(snapshots.SnapshotError, match="registered: one"):
        snapshots.find("two")
