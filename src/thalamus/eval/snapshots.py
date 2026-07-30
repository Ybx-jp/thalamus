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
- `registry()` reads the committed ledger.

The registry is committed; the `.kryo` files are not. The graph is one operator's
session history and is never shipped (docs/index, 2026-07-29) — what travels is the
*claim* that a number came from a named, hash-identified state, which is falsifiable
by anyone holding the same snapshot and is honest about what they cannot check.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from thalamus.substrate.snapshot import snapshot
from thalamus.substrate.writer import close_connection, connect

# Server-side, inside the graph container's data volume — the same directory
# `graphLocation` lives in, so a snapshot is reachable by the same mount.
SERVER_DATA_DIR = "/opt/gremlin-server/data"
CONTAINER = "thalamus-graph-1"
VOLUME = "thalamus_thalamus-graph-data"
IMAGE = "tinkerpop/gremlin-server:3.7.3"

REGISTRY = Path(__file__).resolve().parents[3] / "experiments" / "snapshots.jsonl"

# A snapshot name is part of a filename and of a published citation, so it is
# restricted rather than sanitised — a name that needs escaping is a name that
# will be quoted wrong somewhere.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class SnapshotError(RuntimeError):
    pass


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


def take(name: str, *, note: str = "", url: str | None = None) -> SnapshotRow:
    """Pin the live graph under `name` and record what was pinned.

    Refuses to overwrite: a name that has been cited must keep meaning what it
    meant. Re-pinning the same state is a new name, not a mutation of an old one.
    """
    if not _NAME_RE.match(name):
        raise SnapshotError(
            f"invalid snapshot name `{name}` — lowercase letters, digits and hyphens, 3-64 chars"
        )
    if any(row.name == name for row in registry()):
        raise SnapshotError(f"snapshot `{name}` already exists; snapshots are immutable")
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
        taken_at=datetime.now(timezone.utc).isoformat(),
        vertices=int(vertices),
        edges=int(edges),
        sha256=digest,
        byte_size=size,
        git_ref=_git_ref(),
        note=note,
    )
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as handle:
        handle.write(json.dumps(asdict(row)) + "\n")
    return row


def adopt(name: str, *, filename: str, note: str = "") -> SnapshotRow:
    """Register a `.kryo` that already exists on the server under `name`.

    For states pinned before there was a registry — `pre-sandbox-purge-20260729.kryo`
    is one, and it is the only pre-existing pinned artifact in the corpus. Its counts
    are read by *serving* it rather than taken on trust, so an adopted row says the
    same thing a `take()` row does.
    """
    if not _NAME_RE.match(name):
        raise SnapshotError(f"invalid snapshot name `{name}`")
    if any(row.name == name for row in registry()):
        raise SnapshotError(f"snapshot `{name}` already registered")
    path = f"{SERVER_DATA_DIR}/{filename}"
    if not _file_exists(path):
        raise SnapshotError(f"{path} does not exist on the server")
    if filename != f"{name}.kryo":
        raise SnapshotError(
            f"adopted file must be named `{name}.kryo` — `{filename}` would make the "
            "registry name and the on-disk name disagree"
        )

    digest, size = _sha256_and_size(path)
    # Counts come from the snapshot itself, not from whoever adopted it — and the
    # registry row is written only once they are in hand, so a failed adoption
    # leaves no half-row claiming a state nobody counted.
    vertices, edges = _count_by_serving(name, digest)

    row = SnapshotRow(
        name=name, taken_at=datetime.now(timezone.utc).isoformat(),
        vertices=vertices, edges=edges, sha256=digest, byte_size=size,
        git_ref=_git_ref(), note=note,
    )
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as handle:
        handle.write(json.dumps(asdict(row)) + "\n")
    return row


def _count_by_serving(name: str, digest: str) -> tuple[int, int]:
    with _serve_path(name, server_path(name), digest) as url:
        g = connect(url)
        try:
            return int(g.V().count().next()), int(g.E().count().next())
        finally:
            close_connection(g)


def registry() -> list[SnapshotRow]:
    if not REGISTRY.is_file():
        return []
    rows = []
    for line in REGISTRY.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(SnapshotRow(**json.loads(line)))
    return rows


def find(name: str) -> SnapshotRow:
    for row in registry():
        if row.name == name:
            return row
    known = ", ".join(r.name for r in registry()) or "none"
    raise SnapshotError(f"unknown snapshot `{name}`; registered: {known}")


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
    if digest != row.sha256:
        raise SnapshotError(
            f"snapshot `{name}` no longer hashes to its registry entry "
            f"({digest[:12]} != {row.sha256[:12]}) — it is not the state that was cited"
        )
    with _serve_path(name, row.server_path, digest, port=port, timeout=timeout) as url:
        yield url


@contextmanager
def _serve_path(name: str, path: str, digest: str, *, port: int = 8183, timeout: int = 90):
    """The container half of `serve`, usable before a registry row exists."""
    conf = _write_snapshot_conf(name, path)
    # Any snapshot server still holding this port is a leftover from a run that was
    # killed before its cleanup — reap it. Reaping only this snapshot's own container
    # name is not enough: the port, not the name, is what collides.
    _reap_snapshot_containers(port)
    container = f"thalamus-snapshot-{name}-{port}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
    proc = subprocess.run(
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
    listing = subprocess.run(
        ["docker", "ps", "--filter", "name=thalamus-snapshot-", "--format", "{{.Names}}\t{{.Ports}}"],
        capture_output=True, text=True,
    ).stdout
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and f":{port}->" in parts[1]:
            subprocess.run(["docker", "rm", "-f", parts[0]], capture_output=True, check=False)


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

    logs = subprocess.run(
        ["docker", "logs", "--tail", "20", container], capture_output=True, text=True
    ).stdout
    raise SnapshotError(f"snapshot server not ready in {timeout}s: {last}\n{logs}")


def _file_exists(path: str) -> bool:
    return subprocess.run(
        ["docker", "exec", CONTAINER, "test", "-f", path], capture_output=True
    ).returncode == 0


def _sha256_and_size(path: str) -> tuple[str, int]:
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", f"sha256sum {path} && stat -c %s {path}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SnapshotError(f"cannot hash {path}: {proc.stderr.strip()[:200]}")
    lines = proc.stdout.split()
    return lines[0], int(lines[-1])


def _git_ref() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"
