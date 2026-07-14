"""Write session subgraphs to TinkerGraph via Gremlin."""

from __future__ import annotations

import logging

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import Direction, Merge, T

from thalamus.substrate.schema import SessionGraph

logger = logging.getLogger(__name__)

DEFAULT_URL = "ws://localhost:8182/gremlin"


class GraphWriteError(RuntimeError):
    """A graph write failure annotated with the operation and affected entity."""


def connect(url: str = DEFAULT_URL) -> GraphTraversalSource:
    connection = DriverRemoteConnection(url, "g")
    g = traversal().with_remote(connection)
    # GraphTraversalSource has no public close() method in gremlinpython 3.x.
    # Retain the connection so callers can deterministically close its client session.
    g._thalamus_connection = connection
    return g


def close_connection(g: GraphTraversalSource) -> None:
    """Close the remote connection associated with a traversal source."""
    connection = getattr(g, "_thalamus_connection", None)
    if connection is not None:
        connection.close()


def write_session(g: GraphTraversalSource, session: SessionGraph) -> str:
    """Write a session subgraph to the graph. Idempotent on session_id.

    Returns the session vertex ID.
    """
    session_vid = _upsert_session_vertex(g, session)
    artifact_vids = _upsert_artifacts(g, session)
    _write_decisions(g, session, session_vid, artifact_vids)
    _write_problems_and_solutions(g, session, session_vid, artifact_vids)
    _write_threads(g, session, session_vid, artifact_vids)
    _write_thread_refs(g, session, session_vid)

    logger.info(f"Wrote session subgraph: {session.session_id} ({_subgraph_size(session)} nodes)")
    return session_vid


def _upsert_session_vertex(g: GraphTraversalSource, session: SessionGraph) -> str:
    """Create or update the Session entry node."""
    vid = f"session:{session.session_id}"

    graph_traversal = g.merge_v(
        {"session_id": session.session_id, T.label: "Session"}
    ).option(
        Merge.on_create,
        {
            T.id: vid,
            "session_id": session.session_id,
            "timestamp": session.timestamp.isoformat(),
            "tool": session.tool.value,
            "project": session.project or "",
            "summary": session.summary,
        },
    ).option(
        Merge.on_match,
        {
            "timestamp": session.timestamp.isoformat(),
            "tool": session.tool.value,
            "project": session.project or "",
            "summary": session.summary,
        },
    )
    _iterate(graph_traversal, "upsert Session", vid)

    return vid


def _upsert_artifacts(
    g: GraphTraversalSource, session: SessionGraph
) -> dict[str, str]:
    """Upsert Artifact nodes. Returns mapping of identifier -> vertex ID.

    Artifacts are shared across sessions, so we merge on identifier.
    """
    artifact_vids: dict[str, str] = {}

    for artifact in session.artifacts:
        vid = f"artifact:{artifact.identifier}"

        graph_traversal = g.merge_v(
            {"identifier": artifact.identifier, T.label: "Artifact"}
        ).option(
            Merge.on_create,
            {
                T.id: vid,
                "identifier": artifact.identifier,
                "type": artifact.type.value,
                "project": artifact.project or "",
            },
        ).option(
            Merge.on_match,
            {
                "type": artifact.type.value,
                "project": artifact.project or session.project or "",
            },
        )
        _iterate(graph_traversal, "upsert Artifact", vid)

        artifact_vids[artifact.identifier] = vid

    return artifact_vids


def _write_decisions(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> None:
    """Write Decision nodes and edges."""
    for i, decision in enumerate(session.decisions):
        vid = f"decision:{session.session_id}:{i}"

        graph_traversal = g.merge_v({T.id: vid, T.label: "Decision"}).option(
            Merge.on_create,
            {
                T.id: vid,
                "description": decision.description,
                "rationale": decision.rationale,
                "outcome": decision.outcome or "",
            },
        ).option(
            Merge.on_match,
            {
                "description": decision.description,
                "rationale": decision.rationale,
                "outcome": decision.outcome or "",
            },
        )
        _iterate(graph_traversal, "upsert Decision", vid)

        # Session -[CONTAINS]-> Decision
        _ensure_edge(g, session_vid, vid, "CONTAINS")

        # Decision -[TOUCHES]-> Artifact
        for artifact_id in decision.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, vid, artifact_vids[artifact_id], "TOUCHES")


def _write_problems_and_solutions(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> None:
    """Write Problem and Solution nodes with edges."""
    problem_vids: dict[int, str] = {}

    for i, problem in enumerate(session.problems):
        vid = f"problem:{session.session_id}:{i}"
        problem_vids[i] = vid

        graph_traversal = g.merge_v({T.id: vid, T.label: "Problem"}).option(
            Merge.on_create,
            {
                T.id: vid,
                "description": problem.description,
                "category": problem.category.value,
            },
        ).option(
            Merge.on_match,
            {
                "description": problem.description,
                "category": problem.category.value,
            },
        )
        _iterate(graph_traversal, "upsert Problem", vid)

        _ensure_edge(g, session_vid, vid, "CONTAINS")

        for artifact_id in problem.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, vid, artifact_vids[artifact_id], "TOUCHES")

    for i, solution in enumerate(session.solutions):
        vid = f"solution:{session.session_id}:{i}"

        graph_traversal = g.merge_v({T.id: vid, T.label: "Solution"}).option(
            Merge.on_create,
            {
                T.id: vid,
                "description": solution.description,
                "approach": solution.approach,
                "worked": solution.worked,
            },
        ).option(
            Merge.on_match,
            {
                "description": solution.description,
                "approach": solution.approach,
                "worked": solution.worked,
            },
        )
        _iterate(graph_traversal, "upsert Solution", vid)

        _ensure_edge(g, session_vid, vid, "CONTAINS")

        if solution.problem_ref is not None and solution.problem_ref in problem_vids:
            _ensure_edge(g, problem_vids[solution.problem_ref], vid, "SOLVED_BY")

        for artifact_id in solution.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, vid, artifact_vids[artifact_id], "TOUCHES")


def _write_threads(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> None:
    """Write new Thread nodes spawned by this session.

    Threads are shared across sessions (keyed by thread ID), so a thread opened in one
    session can be continued/resolved by future sessions.
    """
    # Create every thread before writing relationships. A thread may block a later
    # thread in the YAML, and merge_e requires both endpoint vertices to exist.
    for thread in session.threads:
        vid = f"thread:{thread.id}"

        graph_traversal = g.merge_v(
            {"thread_id": thread.id, T.label: "Thread"}
        ).option(
            Merge.on_create,
            {
                T.id: vid,
                "thread_id": thread.id,
                "title": thread.title,
                "description": thread.description,
                "status": thread.status.value,
                "project": session.project or "",
            },
        ).option(
            Merge.on_match,
            {
                "title": thread.title,
                "description": thread.description,
                "status": thread.status.value,
            },
        )
        _iterate(graph_traversal, "upsert Thread", vid)

    for thread in session.threads:
        vid = f"thread:{thread.id}"
        # Session -[SPAWNS]-> Thread
        _ensure_edge(g, session_vid, vid, "SPAWNS")

        # Thread -[TOUCHES]-> Artifact
        for artifact_id in thread.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, vid, artifact_vids[artifact_id], "TOUCHES")

        # Thread -[BLOCKS]-> Thread
        for blocked_id in thread.blocks:
            blocked_vid = f"thread:{blocked_id}"
            _ensure_edge(g, vid, blocked_vid, "BLOCKS")


def _write_thread_refs(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
) -> None:
    """Write edges from this session to existing threads being continued or resolved."""
    for ref in session.thread_refs:
        vid = f"thread:{ref.id}"

        # Update thread status
        graph_traversal = (
            g.V(vid).has_label("Thread").property("status", ref.status.value)
        )
        _iterate(graph_traversal, "update Thread status", vid)

        # Session -[CONTINUES|RESOLVES]-> Thread based on new status
        if ref.status in ("resolved", "abandoned"):
            _ensure_edge(g, session_vid, vid, "RESOLVES")
        else:
            _ensure_edge(g, session_vid, vid, "CONTINUES")


def _ensure_edge(g: GraphTraversalSource, from_vid: str, to_vid: str, label: str) -> None:
    """Create an edge if it doesn't already exist."""
    graph_traversal = g.merge_e(
        {
            T.label: label,
            Direction.from_: from_vid,
            Direction.to: to_vid,
        }
    )
    _iterate(graph_traversal, f"merge {label} edge", f"{from_vid} -> {to_vid}")


def _iterate(graph_traversal, operation: str, target: str) -> None:
    """Execute a write traversal with concise user errors and debug-level bytecode."""
    logger.debug(
        "Executing Gremlin write: operation=%s target=%s bytecode=%r",
        operation,
        target,
        graph_traversal.bytecode,
    )
    try:
        # gremlinpython 3.7 encodes iterate() with the server-supported
        # none() terminal step. Version 3.8 changed this to unsupported discard().
        graph_traversal.iterate()
    except GremlinServerError as exc:
        attributes = exc.status_attributes or {}
        exceptions = attributes.get("exceptions", [])
        exception_text = f"; server exceptions: {', '.join(exceptions)}" if exceptions else ""
        logger.debug(
            "Gremlin server stack trace for %s %s:\n%s",
            operation,
            target,
            attributes.get("stackTrace", "<not supplied>"),
        )
        raise GraphWriteError(
            f"{operation} `{target}` failed: Gremlin server {exc.status_code}: "
            f"{exc.status_message}{exception_text}"
        ) from exc
    except Exception as exc:
        raise GraphWriteError(
            f"{operation} `{target}` failed: {type(exc).__name__}: {exc}"
        ) from exc


def _subgraph_size(session: SessionGraph) -> int:
    return (
        1  # session node
        + len(session.artifacts)
        + len(session.decisions)
        + len(session.problems)
        + len(session.solutions)
        + len(session.threads)
    )
