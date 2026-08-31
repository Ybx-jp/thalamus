"""Named graph snapshots — the reproducibility floor under every published number.

A measurement taken against the live graph is not reproducible: the graph moves
every time a session ends. Every figure in `lab/` was computed that way, and
`pre-sandbox-purge-20260729.kryo` is the only pinned artifact in 33 entries — it
exists by accident of a purge, not by policy.

So: a published number names the snapshot it was computed on, and anyone can serve
that snapshot back and re-run the script. Three pieces:

- `take()` writes the live graph to a named server-side `.kryo` and appends a
  registry row: counts, git ref, sha256, note.
- `serve()` starts a **throwaway, read-only** Gremlin server on that snapshot at
  another port, so an analysis can address the past without the live graph moving
  underneath it — and without the risk of writing to it.
- `registry()` reads the ledger.

The ledger and the `.kryo` files are both operator state: the registry lives at
`~/.thalamus/snapshots.jsonl`, outside any checkout, because a pin belongs to whoever
took it rather than to the source it was taken from. The graph is one operator's
session history and is never shipped — what travels is the *claim* that a number came
from a named, hash-identified state, which is falsifiable by anyone holding the same
snapshot and is honest about what they cannot check.

The vocabulary here — the name rule, the digest pairing, immutability, the mismatch
refusal — is `thalamus.artifacts`'s, and a graph snapshot is one artifact kind using it.

**The sha256 identifies the file, not the state.** A graph loaded from a `.kryo` does
not re-serialize to those bytes. Measured: restoring a snapshot leaves the live file
byte-identical to it, while a fresh `take()` of that same in-memory graph — identical
counts, no writes in between — lands a different digest, and the two safety pins of a
restore round-trip differ from the snapshots they were taken of on digest while
matching them exactly on counts. Two consequences a reader has to hold. `verify()`
answers *has this file been corrupted or replaced since it was recorded*, which is what
`restore()` needs before it swaps anything; it does not answer *do these two snapshots
hold the same graph*, and equal counts under different digests is the ordinary case
across a restart rather than evidence of drift. And the live file's digest moves on its
own at the next clean shutdown, when the server flushes memory to `graphLocation`, so
hashing it is not a change detector either.
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from thalamus import artifacts
from thalamus.substrate.snapshot import DEFAULT_SNAPSHOT_PATH, snapshot
from thalamus.substrate.writer import DEFAULT_URL, close_connection, connect

# Server-side, inside the graph container's data volume — the same directory
# `graphLocation` lives in, so a snapshot is reachable by the same mount.
SERVER_DATA_DIR = "/opt/gremlin-server/data"
CONTAINER = "thalamus-graph-1"
VOLUME = "thalamus_thalamus-graph-data"
IMAGE = "tinkerpop/gremlin-server:3.7.3"

# Operator state, beside the graph's other ledgers — a pinned snapshot belongs to
# whoever took it, not to the checkout it was taken from.
REGISTRY = Path.home() / ".thalamus" / "snapshots.jsonl"

# A graph snapshot is one kind of pinned artifact, and its failures are pin failures:
# a name that cannot be cited, a name already taken, bytes that no longer hash to what
# the registry recorded. There is nothing snapshot-specific about any of those, so this
# is the same type rather than a parallel one a caller would have to catch twice.
SnapshotError = artifacts.ArtifactError


@dataclass(frozen=True)
class SnapshotRow:
    name: str
    taken_at: str
    vertices: int
    edges: int
    sha256: str
    byte_size: int
    git_ref: str
    note: str

    @property
    def server_path(self) -> str:
        return f"{SERVER_DATA_DIR}/{self.name}.kryo"


def server_path(name: str) -> str:
    return f"{SERVER_DATA_DIR}/{name}.kryo"


def _registry() -> artifacts.Registry[SnapshotRow]:
    """Built per call rather than at import, so `REGISTRY` stays the one place the
    ledger's location is stated and a caller that redirects it is obeyed."""
    return artifacts.Registry(REGISTRY, SnapshotRow, noun="snapshot", plural="snapshots")


def take(name: str, *, note: str = "", url: str | None = None) -> SnapshotRow:
    """Pin the live graph under `name` and record what was pinned.

    Refuses to overwrite: a name that has been cited must keep meaning what it
    meant. Re-pinning the same state is a new name, not a mutation of an old one.
    """
    artifacts.check_name(name, noun="snapshot")
    _registry().refuse_duplicate(name)
    if _file_exists(server_path(name)):
        raise SnapshotError(f"{server_path(name)} exists on the server but is not in the registry")

    g = connect(url) if url else connect()
    try:
        vertices = g.V().count().next()
        edges = g.E().count().next()
        snapshot(g, server_path(name))
    finally:
        close_connection(g)

    digest, size = _sha256_and_size(server_path(name))
    row = SnapshotRow(
        name=name,
        taken_at=artifacts.now(),
        vertices=int(vertices),
        edges=int(edges),
        sha256=digest,
        byte_size=size,
        git_ref=_git_ref(),
        note=note,
    )
    return _registry().append(row)


def registry() -> list[SnapshotRow]:
    return _registry().rows()


def find(name: str) -> SnapshotRow:
    return _registry().find(name)


def verify(name: str) -> bool:
    """Does the pinned file still hash to what the registry says it did?"""
    row = find(name)
    digest, _size = _sha256_and_size(row.server_path)
    return digest == row.sha256


@contextmanager
def serve(name: str, *, port: int = 8183, timeout: int = 90):
    """Serve a snapshot read-only at `port` for the duration of the block.

    Yields the Gremlin URL. The container is thrown away on exit, and the data
    volume is mounted **read-only** so an analysis cannot write to the past — the
    failure that would make a snapshot silently stop being the thing it was named
    for. TinkerGraph would otherwise flush `graphLocation` on shutdown.
    """
    row = find(name)
    digest, _ = _sha256_and_size(row.server_path)
    artifacts.check_digest(name, digest, row.sha256, noun="snapshot",
                         consequence="it is not the state that was cited")
    with _serve_path(name, row.server_path, digest, port=port, timeout=timeout) as url:
        yield url


def restore(name: str, *, safety_pin: bool = True, url: str | None = None) -> SnapshotRow:
    """Make a pinned snapshot the live graph again.

    Pinning exists so a state can be returned to, and until this the returning half
    did not exist: `serve` reads the past read-only, and nothing put it back. The gap
    is only visible when it matters, which is after a bad write — recovery then meant
    hand-run `docker` against the data volume, exactly the operation that should not
    be improvised under pressure.

    The order is forced by TinkerGraph holding the graph in memory: the container is
    stopped **before** the file is swapped, because a running server flushes memory to
    `graphLocation` on clean shutdown and would write the state being discarded back
    over the state being restored.

    A safety pin of the current graph is taken first, so this is reversible in the
    direction it is most likely to be needed — a restore run against the wrong name.
    """
    row = find(name)

    # Verified before anything is stopped: a snapshot that no longer hashes to its
    # registry entry is not the state that was cited, and restoring it would put the
    # graph into a condition nothing on record describes.
    digest, _size = _sha256_and_size(row.server_path)
    artifacts.check_digest(name, digest, row.sha256, noun="snapshot",
                         consequence="refusing to restore it")

    pinned: SnapshotRow | None = None
    if safety_pin:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        pinned = take(
            f"pre-restore-{stamp}",
            note=f"Live graph immediately before restoring `{name}`.",
            url=url,
        )

    _run_or_raise(["docker", "stop", CONTAINER], f"cannot stop {CONTAINER}")
    # A throwaway container does the copy: the graph container is down, and reaching
    # into /var/lib/docker/volumes from the host needs root the CLI does not have.
    _run_or_raise(
        [
            "docker", "run", "--rm", "-v", f"{VOLUME}:/data", "--entrypoint", "sh", IMAGE,
            "-c", f"cp /data/{row.name}.kryo /data/{Path(DEFAULT_SNAPSHOT_PATH).name}",
        ],
        f"cannot swap {DEFAULT_SNAPSHOT_PATH} for {row.server_path}",
    )
    _run_or_raise(["docker", "start", CONTAINER], f"cannot start {CONTAINER}")

    endpoint = url or DEFAULT_URL
    _wait_ready(endpoint, CONTAINER, 90)

    g = connect(endpoint)
    try:
        vertices = int(g.V().count().next())
        edges = int(g.E().count().next())
    finally:
        close_connection(g)

    if (vertices, edges) != (row.vertices, row.edges):
        raise SnapshotError(
            f"restored `{name}` but the live graph holds {vertices}V/{edges}E where the "
            f"registry records {row.vertices}V/{row.edges}E"
            + (f" — the prior state is pinned as `{pinned.name}`" if pinned else "")
        )
    return row


DOCKER_ABSENT = (
    "`docker` is not on PATH. Snapshots are files inside the graph container and "
    "every operation here goes through it — install Docker and bring the graph up "
    "with `docker compose up -d`, then retry."
)


def _docker(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` for a docker command, with the absent client named.

    Every call in this module drives the graph container, so `docker` missing is one
    condition with one answer rather than nine bare tracebacks at nine call sites.
    The refusal says what is missing and what to run.
    """
    try:
        return subprocess.run(command, **kwargs)
    except FileNotFoundError as exc:
        raise SnapshotError(DOCKER_ABSENT) from exc


def _run_or_raise(command: list[str], message: str) -> None:
    proc = _docker(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SnapshotError(f"{message}: {proc.stderr.strip()[:200]}")


@contextmanager
def _serve_path(name: str, path: str, digest: str, *, port: int = 8183, timeout: int = 90):
    """The container half of `serve`, usable before a registry row exists."""
    conf = _write_snapshot_conf(name, path)
    # Any snapshot server still holding this port is a leftover from a run that was
    # killed before its cleanup — reap it. Reaping only this snapshot's own container
    # name is not enough: the port, not the name, is what collides.
    _reap_snapshot_containers(port)
    container = f"thalamus-snapshot-{name}-{port}"
    _docker(["docker", "rm", "-f", container], capture_output=True, check=False)
    proc = _docker(
        [
            "docker", "run", "--rm", "-d", "--name", container,
            "-p", f"127.0.0.1:{port}:8182",
            "-v", f"{VOLUME}:{SERVER_DATA_DIR}:ro",
            "-v", f"{conf}:/opt/gremlin-server/conf/thalamus:ro",
            "--entrypoint", "/opt/gremlin-server/bin/gremlin-server.sh",
            IMAGE, "conf/thalamus/gremlin-server.yaml",
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SnapshotError(f"could not start snapshot server: {proc.stderr.strip()[:400]}")

    url = f"ws://localhost:{port}/gremlin"
    try:
        _wait_ready(url, container, timeout)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)


def _reap_snapshot_containers(port: int) -> None:
    """Remove any `thalamus-snapshot-*` container publishing `port`.

    Only ours, and only snapshot servers: a stale container from an interrupted run
    is ours to clean up, while anything else on that port is someone else's process
    and the failure to bind is the correct outcome.
    """
    listing = _docker(
        ["docker", "ps", "--filter", "name=thalamus-snapshot-", "--format", "{{.Names}}\t{{.Ports}}"],
        capture_output=True, text=True,
    ).stdout
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and f":{port}->" in parts[1]:
            _docker(["docker", "rm", "-f", parts[0]], capture_output=True, check=False)


def _write_snapshot_conf(name: str, graph_location: str) -> Path:
    """A conf dir whose graphLocation is the snapshot, and whose graph is inert.

    Built from the repo's own config so the snapshot server differs from the live
    one in exactly one property. The init script is dropped: it belongs to the live
    graph's startup, and a read-only replay has nothing to initialise.
    """
    repo_conf = Path(__file__).resolve().parents[3] / "config"
    out = Path.home() / ".thalamus" / "snapshot-conf" / name
    out.mkdir(parents=True, exist_ok=True)

    properties = (repo_conf / "tinkergraph.properties").read_text()
    properties = re.sub(
        r"^gremlin\.tinkergraph\.graphLocation=.*$",
        f"gremlin.tinkergraph.graphLocation={graph_location}",
        properties,
        flags=re.MULTILINE,
    )
    (out / "tinkergraph.properties").write_text(properties)

    # The init script binds the `g` traversal source the client connects as, so it
    # is copied rather than dropped — without it the server starts and every query
    # fails with "traversal source [g] ... is not configured".
    (out / "thalamus-graph.groovy").write_text((repo_conf / "thalamus-graph.groovy").read_text())
    (out / "gremlin-server.yaml").write_text((repo_conf / "gremlin-server.yaml").read_text())
    return out


_PROBE = (
    "import sys;"
    "from thalamus.substrate.writer import connect, close_connection;"
    "g = connect(sys.argv[1]);"
    "n = g.V().limit(1).count().next();"
    "close_connection(g);"
    "print(n)"
)


def _wait_ready(url: str, container: str, timeout: int) -> None:
    """Wait until the snapshot server answers a real traversal.

    The probe runs in a **subprocess**, one per attempt, and that is the whole
    design: gremlin-python owns an event loop per connection and does not survive
    one being opened and closed repeatedly in a single process ("Cannot run the
    event loop while another loop is running"), so an in-process poll would poison
    the caller's own connection. A port check alone is not enough either — the
    server binds before the init script binds `g`, and a query in that window fails
    with a disconnect that reads like an empty graph.
    """
    parsed = urlparse(url)
    deadline = time.time() + timeout
    last = "port never opened"

    while time.time() < deadline:
        with socket.socket() as probe:
            probe.settimeout(2)
            if probe.connect_ex((parsed.hostname or "localhost", parsed.port or 8182)) == 0:
                break
        time.sleep(1)

    while time.time() < deadline:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE, url], capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0:
            return
        last = (proc.stderr.strip().splitlines() or ["no output"])[-1][:200]
        time.sleep(2)

    logs = _docker(
        ["docker", "logs", "--tail", "20", container], capture_output=True, text=True
    ).stdout
    raise SnapshotError(f"snapshot server not ready in {timeout}s: {last}\n{logs}")


def _file_exists(path: str) -> bool:
    return _docker(
        ["docker", "exec", CONTAINER, "test", "-f", path], capture_output=True
    ).returncode == 0


def _sha256_and_size(path: str) -> tuple[str, int]:
    proc = _docker(
        ["docker", "exec", CONTAINER, "sh", "-c", f"sha256sum {path} && stat -c %s {path}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SnapshotError(f"cannot hash {path}: {proc.stderr.strip()[:200]}")
    lines = proc.stdout.split()
    return lines[0], int(lines[-1])


def _git_ref() -> str:
    return artifacts.git_ref(Path(__file__).resolve().parents[3])
