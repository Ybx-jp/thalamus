"""Write session subgraphs to TinkerGraph via Gremlin."""

from __future__ import annotations

import logging

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import Direction, Merge, T

from thalamus.contract.ontology import vid
from thalamus.substrate.schema import Claim, Provenance, SessionGraph

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
    _write_sources(g, session, session_vid)
    artifact_vids = _upsert_artifacts(g, session)
    _write_touches(g, session, session_vid, artifact_vids)
    _write_claims(g, session, session_vid, artifact_vids)
    _write_threads(g, session, session_vid, artifact_vids)
    _write_thread_refs(g, session, session_vid)

    logger.info(
        "Wrote session subgraph: %s (scope=%s, %d nodes)",
        session.session_id,
        session.scope,
        _subgraph_size(session),
    )
    return session_vid


def _provenance_properties(provenance: Provenance) -> dict[str, object]:
    """Flatten a provenance envelope into vertex properties.

    Every node in the graph carries these. `derived_from` is deliberately NOT among them
    — it becomes edges, not a property, because effective trust is a traversal over the
    derivation closure (docs/05) and a property could not be walked.
    """
    return {
        "tier": int(provenance.tier),
        "source": provenance.source,
        "ingested_at": provenance.ingested_at.isoformat(),
    }


def _upsert_session_vertex(g: GraphTraversalSource, session: SessionGraph) -> str:
    """Create or update the Session entry node."""
    session_vid = vid("Session", session.session_id, session.scope)
    provenance = session.default_provenance()

    properties = {
        "session_id": session.session_id,
        "timestamp": session.timestamp.isoformat(),
        "tool": session.tool.value,
        "scope": session.scope,
        "project": session.project or "",
        "summary": session.summary,
        **_provenance_properties(provenance),
    }

    graph_traversal = (
        g.merge_v({"session_id": session.session_id, "scope": session.scope, T.label: "Session"})
        .option(Merge.on_create, {T.id: session_vid, **properties})
        .option(Merge.on_match, properties)
    )
    _iterate(graph_traversal, "upsert Session", session_vid)

    return session_vid


def _upsert_artifacts(g: GraphTraversalSource, session: SessionGraph) -> dict[str, str]:
    """Upsert Artifact nodes. Returns identifier -> vertex ID.

    Artifacts are GLOBAL: one vertex per identifier, shared across every scope, merged on
    identifier alone. Two experts touching the same file land on the same node by design —
    that is what makes artifacts the join key between scopes (contract/ontology.py).
    """
    artifact_vids: dict[str, str] = {}

    for artifact in session.artifacts:
        artifact_vid = vid("Artifact", artifact.identifier)
        provenance = artifact.provenance or session.default_provenance()

        properties = {
            "type": artifact.type.value,
            "project": artifact.project or session.project or "",
            **_provenance_properties(provenance),
        }

        graph_traversal = (
            g.merge_v({"identifier": artifact.identifier, T.label: "Artifact"})
            .option(
                Merge.on_create,
                {T.id: artifact_vid, "identifier": artifact.identifier, **properties},
            )
            .option(Merge.on_match, properties)
        )
        _iterate(graph_traversal, "upsert Artifact", artifact_vid)

        artifact_vids[artifact.identifier] = artifact_vid

    return artifact_vids


def _write_sources(g: GraphTraversalSource, session: SessionGraph, session_vid: str) -> None:
    """Write the evidence this session was distilled from, and link back to it.

    The Session -[DERIVED_FROM]-> Source edge is what gives every belief in this session a
    provenance *floor*. Without it the chain terminates at a summary of itself.
    """
    for source in session.sources:
        source_vid = vid("Source", source.content_hash, session.scope)
        provenance = source.provenance or session.default_provenance()

        properties = {
            "content_hash": source.content_hash,
            "kind": source.kind.value,
            "title": source.title,
            "uri": source.uri,
            "origin": source.origin or "",
            "byte_size": source.byte_size,
            "message_count": source.message_count,
            "scope": session.scope,
            **_provenance_properties(provenance),
        }

        graph_traversal = (
            g.merge_v({T.id: source_vid, T.label: "Source"})
            .option(Merge.on_create, {T.id: source_vid, **properties})
            .option(Merge.on_match, properties)
        )
        _iterate(graph_traversal, "upsert Source", source_vid)

        _ensure_edge(g, session_vid, source_vid, "DERIVED_FROM")


def _write_touches(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> None:
    """Write the deterministic Session -[TOUCHES]-> Artifact edges.

    Recovered exactly from tool-call records, and anchored to the message UUIDs of the
    calls themselves — so "when did I touch this file, and where is the proof" is a two-hop
    traversal with no model in the loop.
    """
    for touch in session.touched:
        artifact_vid = artifact_vids.get(touch.identifier)
        if artifact_vid is None:
            continue
        properties = {"anchors": ",".join(touch.anchors)} if touch.anchors else None
        _ensure_edge(g, session_vid, artifact_vid, "TOUCHES", properties)


def _claim_properties(claim: Claim) -> dict[str, object]:
    """Subtype-specific fields, flattened onto the shared Claim label.

    One label discriminated by `kind`, not one label per subtype — so consumers query
    `hasLabel("Claim")` and keep working when an expert introduces a new kind.
    """
    fields = claim.model_dump(
        mode="json", exclude={"provenance", "artifacts", "kind", "description"}
    )
    return {key: value for key, value in fields.items() if value is not None}


def _write_claims(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> dict[str, str]:
    """Write Claim nodes (decisions, problems, solutions) and their edges."""
    claim_vids: dict[str, str] = {}

    for claim in session.claims():
        claim_vid = vid("Claim", claim.content_id(), session.scope)
        provenance = claim.provenance or session.default_provenance()

        properties = {
            "kind": claim.kind.value,
            "description": claim.description,
            "scope": session.scope,
            **_claim_properties(claim),
            **_provenance_properties(provenance),
        }

        graph_traversal = (
            g.merge_v({T.id: claim_vid, T.label: "Claim"})
            .option(Merge.on_create, {T.id: claim_vid, **properties})
            .option(Merge.on_match, properties)
        )
        _iterate(graph_traversal, "upsert Claim", claim_vid)

        claim_vids[claim.content_id()] = claim_vid
        _ensure_edge(g, session_vid, claim_vid, "CONTAINS")

        for artifact_id in claim.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, claim_vid, artifact_vids[artifact_id], "TOUCHES")

        for origin_vid in provenance.derived_from:
            _ensure_edge(g, claim_vid, origin_vid, "DERIVED_FROM")

    # problem_ref is an index into the problems list; resolve it to a content ID.
    problem_vids = {
        index: vid("Claim", problem.content_id(), session.scope)
        for index, problem in enumerate(session.problems)
    }
    for solution in session.solutions:
        problem_vid = problem_vids.get(solution.problem_ref)
        if problem_vid is not None:
            solution_vid = vid("Claim", solution.content_id(), session.scope)
            _ensure_edge(g, problem_vid, solution_vid, "SOLVED_BY")

    return claim_vids


def _write_threads(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> None:
    """Write new Thread nodes spawned by this session.

    Threads are shared across sessions within a scope (keyed by thread ID), so a thread
    opened in one session can be continued or resolved by a later one.
    """
    # Create every thread before writing relationships: a thread may block a later thread
    # in the YAML, and merge_e requires both endpoint vertices to exist.
    for thread in session.threads:
        thread_vid = vid("Thread", thread.id, session.scope)
        provenance = thread.provenance or session.default_provenance()

        properties = {
            "title": thread.title,
            "description": thread.description,
            "status": thread.status.value,
            "scope": session.scope,
            "project": session.project or "",
            **_provenance_properties(provenance),
        }

        graph_traversal = (
            g.merge_v({"thread_id": thread.id, "scope": session.scope, T.label: "Thread"})
            .option(Merge.on_create, {T.id: thread_vid, "thread_id": thread.id, **properties})
            .option(Merge.on_match, properties)
        )
        _iterate(graph_traversal, "upsert Thread", thread_vid)

    for thread in session.threads:
        thread_vid = vid("Thread", thread.id, session.scope)
        _ensure_edge(g, session_vid, thread_vid, "SPAWNS")

        for artifact_id in thread.artifacts:
            if artifact_id in artifact_vids:
                _ensure_edge(g, thread_vid, artifact_vids[artifact_id], "TOUCHES")

        for blocked_id in thread.blocks:
            _ensure_edge(g, thread_vid, vid("Thread", blocked_id, session.scope), "BLOCKS")


def _write_thread_refs(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
) -> None:
    """Write edges from this session to existing threads continued or resolved."""
    for ref in session.thread_refs:
        thread_vid = vid("Thread", ref.id, session.scope)

        graph_traversal = g.V(thread_vid).has_label("Thread").property("status", ref.status.value)
        _iterate(graph_traversal, "update Thread status", thread_vid)

        if ref.status in ("resolved", "abandoned"):
            _ensure_edge(g, session_vid, thread_vid, "RESOLVES")
        else:
            _ensure_edge(g, session_vid, thread_vid, "CONTINUES")


def _ensure_edge(
    g: GraphTraversalSource,
    from_vid: str,
    to_vid: str,
    label: str,
    properties: dict[str, object] | None = None,
) -> None:
    """Create an edge if it doesn't already exist, optionally carrying properties.

    Edge properties are how anchors ride along: a DERIVED_FROM or TOUCHES edge records
    *which messages* in the Source produced it, so a provenance walk lands on the exact
    evidence rather than on a 600 KB transcript.
    """
    graph_traversal = g.merge_e(
        {
            T.label: label,
            Direction.from_: from_vid,
            Direction.to: to_vid,
        }
    )
    if properties:
        graph_traversal = graph_traversal.option(Merge.on_create, properties).option(
            Merge.on_match, properties
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
        # gremlinpython 3.7 encodes iterate() with the server-supported none()
        # terminal step. Version 3.8 changed this to unsupported discard().
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
        1
        + len(session.sources)
        + len(session.artifacts)
        + len(session.claims())
        + len(session.threads)
    )
