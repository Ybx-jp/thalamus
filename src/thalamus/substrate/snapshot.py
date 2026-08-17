"""Flush the in-memory graph to its persistent file.

TinkerGraph holds the graph in memory and writes `graphLocation` back to disk
only when the graph closes cleanly. That is fine for a shutdown and useless for
a crash: `docker kill`, an OOM, or a power cut discards everything written since
the last close.

`snapshot()` closes that window by driving the io()-step against the same path,
on demand. The write happens **on the server**, not locally — the path is a
container path, and the client never sees the bytes.

Callers on the write path invoke this after a successful write, so durability is
the default rather than an operator chore.
"""

from __future__ import annotations

import logging

from gremlin_python.process.graph_traversal import GraphTraversalSource

logger = logging.getLogger(__name__)

# Server-side path. Must match `gremlin.tinkergraph.graphLocation` in
# config/tinkergraph.properties — writing anywhere else produces a file that
# startup will not load.
DEFAULT_SNAPSHOT_PATH = "/opt/gremlin-server/data/thalamus-graph.kryo"


class SnapshotError(RuntimeError):
    """The graph could not be flushed to disk."""


def snapshot(g: GraphTraversalSource, path: str = DEFAULT_SNAPSHOT_PATH) -> str:
    """Write the whole graph to `path` on the server. Returns the path written.

    Raises SnapshotError on failure — callers that treat persistence as optional
    should use `snapshot_quietly` instead.
    """
    try:
        g.io(path).write().iterate()
    except Exception as exc:  # noqa: BLE001 - surfaced as SnapshotError below
        raise SnapshotError(f"Graph snapshot to `{path}` failed: {exc}") from exc
    logger.info("Graph snapshot written to %s", path)
    return path


def snapshot_quietly(g: GraphTraversalSource, path: str = DEFAULT_SNAPSHOT_PATH) -> bool:
    """Best-effort flush used after CLI writes. Warns instead of raising.

    A failed snapshot must not fail the write that preceded it: the write already
    succeeded in memory, and a clean shutdown will still persist it. The operator
    needs to know durability was not achieved, not to see the write reported as
    lost when it was not.
    """
    try:
        snapshot(g, path)
        return True
    except SnapshotError as exc:
        logger.warning(
            "%s — the write is in memory but not yet on disk; it will persist on a "
            "clean shutdown (`docker compose stop`), and would be lost to a hard kill.",
            exc,
        )
        return False
