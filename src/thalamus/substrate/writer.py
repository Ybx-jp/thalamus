"""Write session subgraphs to the graph via Gremlin."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import GraphTraversalSource, __
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


def _text_stamp(g: GraphTraversalSource, vertex_id: str, text: str) -> dict[str, object]:
    """`written_at`: when this vertex's text last *changed*, beside `ingested_at`.

    `ingested_at` carries the writing session's timestamp and is overwritten on every
    re-upsert, so it can move backwards and cannot answer "when did this node's text
    change" — a question the graph could not answer at all until this existed, which
    is why the mutable-text exposure had to be inferred from evidence strings rather
    than queried.

    The two are different axes and the literature keeps them apart: Graphiti carries
    `t'_created`/`t'_expired` (ingestion order) separately from `t_valid`/`t_invalid`
    (when the fact held), and TOKI keeps `system_time_*` separate from `valid_*`
    columns — collapsing them costs 12.2 accuracy points in TSM (docs/11 §5). This is
    the transaction-time axis only. Valid time — when a fact stopped being true — is a
    second axis this does not attempt (docs/09, and the decision log's dated refusal).

    A digest rather than the text itself: it is the comparison that matters, and
    storing the text twice would be one more copy to keep honest.
    """
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
    now = datetime.now(timezone.utc).isoformat()
    try:
        rows = g.V(vertex_id).value_map("written_at", "text_digest").limit(1).to_list()
    except Exception:
        # A vertex that cannot be read has no prior text to differ from, which is the
        # first-write case and stamps `now` — the same posture as _snapshot_heads.
        rows = []
    if rows:
        stored = rows[0] if isinstance(rows[0], dict) else {}
        held = stored.get("text_digest")
        held = held[0] if isinstance(held, list) and held else held
        if held == digest:
            kept = stored.get("written_at")
            kept = kept[0] if isinstance(kept, list) and kept else kept
            # Unchanged text keeps its original stamp. Refreshing it here would make
            # `written_at` a synonym for "last written", which is the property
            # `ingested_at` already fails to be useful as.
            if kept:
                return {"written_at": kept, "text_digest": digest}
    return {"written_at": now, "text_digest": digest}


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
        "room": session.room,
        "forked_from": session.forked_from,
        "summary": session.summary,
        **_provenance_properties(provenance),
        **_text_stamp(g, session_vid, session.summary),
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

    A transcript snapshot also SUPERSEDES the session's previous snapshot heads: a
    session distilled more than once while its transcript grew holds several snapshots
    (docs/10, lab/002), and the lineage is what gives consumers a defined "current"
    one instead of a guess. Only transcript Sources supersede — two unrelated pieces
    of evidence on one session (a paper and a transcript, someday) are siblings, not
    revisions of each other.
    """
    for source in session.sources:
        source_vid = vid("Source", source.content_hash, session.scope)
        provenance = source.provenance or session.default_provenance()

        prior_heads = (
            _snapshot_heads(g, session_vid) if source.kind.value == "transcript" else []
        )

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
            **_text_stamp(g, source_vid, source.title),
        }

        graph_traversal = (
            g.merge_v({T.id: source_vid, T.label: "Source"})
            .option(Merge.on_create, {T.id: source_vid, **properties})
            .option(Merge.on_match, properties)
        )
        _iterate(graph_traversal, "upsert Source", source_vid)

        _ensure_edge(g, session_vid, source_vid, "DERIVED_FROM")
        for head_vid in prior_heads:
            if head_vid != source_vid:
                _ensure_edge(g, source_vid, head_vid, "SUPERSEDES")


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
        mode="json",
        # `about` is excluded for the same reason `derived_from` is on provenance:
        # relationships become edges, never list-valued properties.
        exclude={"provenance", "artifacts", "kind", "description", "about"},
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
            "kind": claim.kind,
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
            **_text_stamp(g, thread_vid, thread.title),
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
    """Write edges from this session to existing threads continued or resolved.

    A ref to a thread that does not exist is dropped, not written and not fatal: it is
    model output referencing memory that was never formed (hallucinated id, renamed
    slug), and mergeE cannot create an edge to a missing vertex anyway. Dropping it
    loses nothing real — the thread it names was never real.
    """
    for ref in session.thread_refs:
        thread_vid = vid("Thread", ref.id, session.scope)

        if not g.V(thread_vid).has_label("Thread").has_next():
            logger.warning(
                "thread_ref '%s' does not match any Thread in scope %s; dropping",
                ref.id,
                session.scope,
            )
            continue

        graph_traversal = g.V(thread_vid).has_label("Thread").property("status", ref.status.value)
        _iterate(graph_traversal, "update Thread status", thread_vid)

        if ref.status in ("resolved", "abandoned"):
            _ensure_edge(g, session_vid, thread_vid, "RESOLVES")
        else:
            _ensure_edge(g, session_vid, thread_vid, "CONTINUES")


def write_knowledge(g: GraphTraversalSource, batch) -> str:
    """Write one ingestion event into an expert's knowledge subgraph.

    Source (the retained article) -> Claims (DERIVED_FROM it) -> Entities (ABOUT).
    Re-ingesting a changed article creates a new Source that SUPERSEDES the previous
    head for the same origin — versioning stays visible to the eval loop (docs/06).
    Returns the Source vertex ID.
    """
    provenance = batch.default_provenance()
    source = batch.source
    source_vid = vid("Source", source.content_hash, batch.scope)

    prior_heads = _article_heads(g, batch.scope, source.origin or "")

    properties = {
        "content_hash": source.content_hash,
        "kind": source.kind.value,
        "title": source.title,
        "uri": source.uri,
        "origin": source.origin or "",
        "byte_size": source.byte_size,
        "scope": batch.scope,
        # Feed identity lives on the Source (the ingestion event), not on claims or
        # entities — those converge across feeds, and the feed that brought a document
        # in is a fact about the document. docs/06 requires it on every write; claims
        # reach it by walking DERIVED_FROM.
        "feed": batch.feed,
        **_provenance_properties(source.provenance or provenance),
    }
    graph_traversal = (
        g.merge_v({T.id: source_vid, T.label: "Source"})
        .option(Merge.on_create, {T.id: source_vid, **properties})
        .option(Merge.on_match, properties)
    )
    _iterate(graph_traversal, "upsert Source", source_vid)

    for head_vid in prior_heads:
        if head_vid != source_vid:
            _ensure_edge(g, source_vid, head_vid, "SUPERSEDES")

    entity_vids: dict[str, str] = {}
    for entity in batch.entities:
        entity_vid = vid("Entity", entity.slug(), batch.scope)
        entity_properties = {
            "name": entity.name,
            "kind": entity.kind,
            "description": entity.description or "",
            "scope": batch.scope,
            **_provenance_properties(entity.provenance or provenance),
            **_text_stamp(g, entity_vid, entity.name),
        }
        graph_traversal = (
            g.merge_v({T.id: entity_vid, T.label: "Entity"})
            .option(Merge.on_create, {T.id: entity_vid, **entity_properties})
            .option(Merge.on_match, entity_properties)
        )
        _iterate(graph_traversal, "upsert Entity", entity_vid)
        entity_vids[entity.name] = entity_vid

    # Chunks before claims, so the anchor edge has something to point at (lab/052).
    chunk_vids: dict[int, str] = {}
    previous_vid = ""
    for chunk in batch.chunks:
        chunk_vid = vid("Chunk", chunk.local_id(source.content_hash), batch.scope)
        chunk_properties = {
            "text": chunk.text,
            "ordinal": chunk.ordinal,
            "start": chunk.start,
            "end": chunk.end,
            "scope": batch.scope,
            **_provenance_properties(chunk.provenance or provenance),
        }
        graph_traversal = (
            g.merge_v({T.id: chunk_vid, T.label: "Chunk"})
            .option(Merge.on_create, {T.id: chunk_vid, **chunk_properties})
            .option(Merge.on_match, chunk_properties)
        )
        _iterate(graph_traversal, "upsert Chunk", chunk_vid)
        chunk_vids[chunk.ordinal] = chunk_vid

        # Same floor the claims get, and the reason reaching a chunk is
        # provenance-mediated rather than provenance-free (docs/05).
        _ensure_edge(g, chunk_vid, source_vid, "DERIVED_FROM")
        if previous_vid:
            _ensure_edge(g, previous_vid, chunk_vid, "ADJACENT_IN_TEXT")
        previous_vid = chunk_vid
        for name in chunk.about:
            if name in entity_vids:
                _ensure_edge(g, chunk_vid, entity_vids[name], "ABOUT")

    for index, claim in enumerate(batch.claims):
        claim_vid = vid("Claim", claim.content_id(), batch.scope)
        claim_properties = {
            "kind": claim.kind,
            "description": claim.description,
            "scope": batch.scope,
            **_claim_properties(claim),
            **_provenance_properties(claim.provenance or provenance),
        }
        graph_traversal = (
            g.merge_v({T.id: claim_vid, T.label: "Claim"})
            .option(Merge.on_create, {T.id: claim_vid, **claim_properties})
            .option(Merge.on_match, claim_properties)
        )
        _iterate(graph_traversal, "upsert Claim", claim_vid)

        # The provenance floor: this claim is what the SOURCE asserts, so the edge to
        # the retained bytes is not optional decoration — it is what keeps tier 2 a
        # walkable fact instead of a sticker.
        _ensure_edge(g, claim_vid, source_vid, "DERIVED_FROM")
        for name in claim.about:
            if name in entity_vids:
                _ensure_edge(g, claim_vid, entity_vids[name], "ABOUT")

        # The anchor: this claim's verbatim citation was located inside that chunk, so
        # the note reaches the passage it came from. Absent when the citation could not
        # be found verbatim — an anchor that had to be guessed is worse than none.
        anchor = batch.anchors.get(index)
        if anchor is not None and anchor in chunk_vids:
            _ensure_edge(g, claim_vid, chunk_vids[anchor], "ANCHORS")

    logger.info(
        "Wrote knowledge batch: %s (scope=%s, %d claims, %d entities, %d chunks)",
        source.origin or source.title,
        batch.scope,
        len(batch.claims),
        len(batch.entities),
        len(batch.chunks),
    )
    return source_vid


def _article_heads(g: GraphTraversalSource, scope: str, origin: str) -> list[str]:
    """Current head Sources for an article origin within a scope."""
    if not origin:
        return []
    try:
        return [
            str(head)
            for head in (
                g.V()
                .has_label("Source")
                .has("scope", scope)
                .has("kind", "article")
                .has("origin", origin)
                .not_(__.in_e("SUPERSEDES"))
                .id_()
                .to_list()
            )
        ]
    except Exception:
        return []


def _snapshot_heads(g: GraphTraversalSource, session_vid: str) -> list[str]:
    """Current head snapshots of a session's transcript lineage.

    A head is a transcript Source with no incoming SUPERSEDES edge. Normally there is
    exactly one; pre-lineage sessions (written before this edge existed) may expose
    several, and linking the new snapshot to all of them heals the chain.
    """
    try:
        return [
            str(head)
            for head in (
                g.V(session_vid)
                .out("DERIVED_FROM")
                .has_label("Source")
                .has("kind", "transcript")
                .not_(__.in_e("SUPERSEDES"))
                .id_()
                .to_list()
            )
        ]
    except Exception:
        # A missing session vertex (first write) has no snapshots to supersede.
        return []


def write_exchange(
    g: GraphTraversalSource,
    exchange_vid: str,
    properties: dict[str, object],
    brief_refs: list[str] | None = None,
) -> None:
    """Open one consultation exchange record — the mint IS the write (docs/02).

    The vertex is created at ticket-mint time, before any answer exists, so an
    unrecorded consultation is impossible by construction. `brief_refs` are the
    consulted scope's nodes the server assembled into the expert brief; each gets an
    Exchange -[REFERENCES {role: brief}]-> node edge — the consulted expert's record
    of what it served, by ID, never copied.
    """
    graph_traversal = (
        g.merge_v({T.id: exchange_vid, T.label: "Exchange"})
        .option(Merge.on_create, {T.id: exchange_vid, **properties})
        .option(Merge.on_match, properties)
    )
    _iterate(graph_traversal, "upsert Exchange", exchange_vid)

    for ref_vid in brief_refs or []:
        _ensure_edge(g, exchange_vid, ref_vid, "REFERENCES", {"role": "brief"})


def close_exchange(
    g: GraphTraversalSource,
    exchange_vid: str,
    properties: dict[str, object],
    citation_refs: list[str],
) -> None:
    """Close an exchange with its validated answer, burning the ticket.

    `citation_refs` have already been validated to resolve inside the consulted scope
    (harness/consultation.py); each gets an Exchange -[REFERENCES {role: citation}]->
    node edge — the answer's evidence-support record. The status flip to `answered`
    rides in `properties`, and it is what makes the ticket single-use: an answered
    exchange refuses further answers and grants no further retrieval.
    """
    graph_traversal = g.V(exchange_vid).has_label("Exchange")
    for key, value in properties.items():
        graph_traversal = graph_traversal.property(key, value)
    _iterate(graph_traversal, "update Exchange", exchange_vid)

    for ref_vid in citation_refs:
        _ensure_edge(g, exchange_vid, ref_vid, "REFERENCES", {"role": "citation"})


def write_trace(
    g: GraphTraversalSource,
    trace_vid: str,
    properties: dict[str, object],
    session_vid: str,
    returns: dict[str, dict[str, object] | None],
) -> None:
    """Upsert one retrieval-trace vertex with its edges (docs/04 layer 1).

    Session -[QUERIES]-> Trace -[RETURNS]-> result nodes. `returns` maps each returned
    vertex ID to the properties its RETURNS edge should carry — after attribution that
    is the `used`/`evidence` verdict, which lives on the edge because it is a fact about
    this retrieval of the node, not about the node. Idempotent like every other write
    here: re-syncing a trace re-asserts the same vertex, and re-attributing updates the
    verdicts in place.
    """
    graph_traversal = (
        g.merge_v({T.id: trace_vid, T.label: "Trace"})
        .option(Merge.on_create, {T.id: trace_vid, **properties})
        .option(Merge.on_match, properties)
    )
    _iterate(graph_traversal, "upsert Trace", trace_vid)

    _ensure_edge(g, session_vid, trace_vid, "QUERIES")
    for target_vid, edge_properties in returns.items():
        _ensure_edge(g, trace_vid, target_vid, "RETURNS", edge_properties)


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
        # gremlinpython 3.7 encodes iterate() with the none() terminal step, which
        # the 3.7 server understands. Version 3.8 changed this to discard(); the
        # pin in pyproject.toml keeps the two ends on the same side of that split.
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
