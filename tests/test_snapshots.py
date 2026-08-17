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


def test_a_missing_docker_is_a_sentence_not_a_traceback(registry, monkeypatch):
    """
    Scenario: any snapshot operation on a host with no `docker` on PATH

    Verifications:
    - the public entry point refuses with what is missing and what to run
    - `_run_or_raise` — which checked only the exit status — refuses the same way

    A snapshot is a file inside the graph container, so every call in the module
    goes through the client. Absent, it is an ordinary environment difference, and
    `eval/arms.py` already answers the same condition with an instruction rather
    than a stack trace.
    """
    def no_docker(command, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "docker")

    monkeypatch.setattr(snapshots.subprocess, "run", no_docker)

    with pytest.raises(snapshots.SnapshotError) as absent:
        snapshots.take("some-state")
    assert "`docker` is not on PATH" in str(absent.value)
    assert "docker compose up -d" in str(absent.value)

    with pytest.raises(snapshots.SnapshotError, match="not on PATH"):
        snapshots._run_or_raise(["docker", "start", "thalamus-graph"], "cannot start")


@pytest.fixture
def docker_log(monkeypatch):
    """Record the docker commands a restore issues, in order, without running them."""
    calls: list[list[str]] = []
    monkeypatch.setattr(snapshots, "_run_or_raise", lambda command, message: calls.append(command))
    monkeypatch.setattr(snapshots, "_wait_ready", lambda url, container, timeout: None)
    return calls


def _verb(command: list[str]) -> str:
    """The docker subcommand, e.g. `stop` / `run` / `start`."""
    return command[1]


def test_restoring_stops_the_server_before_swapping_the_file(
    registry, stub_server, docker_log, monkeypatch
):
    """
    Scenario: A pinned snapshot is restored over the live graph

    Verifications:
    - The current graph is pinned as a safety net first
    - The container is stopped BEFORE the file is swapped, and started after

    The ordering is the whole correctness argument, not a tidiness preference.
    TinkerGraph holds the graph in memory and flushes `graphLocation` on clean
    shutdown, so swapping the file under a running server means the shutdown writes
    the state being discarded straight back over the state being restored — a
    restore that silently does nothing.
    """
    _fake_graph(monkeypatch, stub_server, vertices=42, edges=99)
    snapshots.take("good-state", note="known good")

    snapshots.restore("good-state")

    # Verifies: a safety pin of the live graph exists before the destructive part
    names = [json.loads(line)["name"] for line in registry.read_text().splitlines()]
    assert names[0] == "good-state"
    assert names[1].startswith("pre-restore-")

    # Verifies: stop, then swap, then start — in that order
    assert [_verb(command) for command in docker_log] == ["stop", "run", "start"]

    swap = docker_log[1]
    assert "cp /data/good-state.kryo /data/thalamus-graph.kryo" in swap[-1]


def test_a_snapshot_that_no_longer_hashes_to_its_citation_is_not_restored(
    registry, stub_server, docker_log, monkeypatch
):
    """
    Scenario: The pinned .kryo on the server has changed since it was registered

    Verifications:
    - The restore is refused
    - Nothing was stopped, swapped or started

    Restoring a file that no longer matches its registry row would put the graph
    into a state nothing on record describes — worse than the bad state it replaces,
    because the bad state at least has a snapshot describing it. The check runs
    before the container is touched so a refusal costs no downtime.
    """
    _fake_graph(monkeypatch, stub_server)
    snapshots.take("drifted", note="")
    stub_server["hash"] = "b" * 64

    with pytest.raises(snapshots.SnapshotError, match="refusing to restore"):
        snapshots.restore("drifted")

    # Verifies: refused before any container command ran
    assert docker_log == []


def test_a_restore_that_lands_on_the_wrong_counts_says_where_the_old_state_went(
    registry, stub_server, docker_log, monkeypatch
):
    """
    Scenario: The restore completes but the live graph does not hold what the
    registry says the snapshot held

    Verifications:
    - It raises rather than reporting success
    - The error names the safety pin holding the pre-restore state

    A restore is run when something has already gone wrong, so the failure mode that
    matters is the operator being told "restored" while holding a third unknown
    state. Naming the safety pin is what makes the situation recoverable rather than
    merely reported.
    """
    _fake_graph(monkeypatch, stub_server, vertices=42, edges=99)
    snapshots.take("good-state", note="")

    # The live graph now answers with counts that do not match the registry row.
    _fake_graph(monkeypatch, stub_server, vertices=7, edges=7)

    with pytest.raises(snapshots.SnapshotError, match=r"pre-restore-"):
        snapshots.restore("good-state")


def test_an_unknown_snapshot_name_is_refused_before_anything_is_touched(
    registry, stub_server, docker_log
):
    """
    Scenario: A restore names a snapshot that was never registered

    Verifications:
    - It raises, listing what is registered
    - No container command runs
    """
    with pytest.raises(snapshots.SnapshotError, match="unknown snapshot"):
        snapshots.restore("never-pinned")

    # Verifies: an unknown name costs nothing
    assert docker_log == []
