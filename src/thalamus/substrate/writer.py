"""Write session subgraphs to the graph via Gremlin."""

from __future__ import annotations

import hashlib
import logging
import socket
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import PurePosixPath

from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.driver.protocol import GremlinServerError
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import Direction, Merge, P, T

from thalamus.contract.ontology import vid
from thalamus.contract.paths import PROJECT_ROOT
from thalamus.substrate import spans
from thalamus.substrate.artifact_paths import checkout_registry, relativize
from thalamus.substrate.schema import (
    Alternative,
    Claim,
    Provenance,
    SessionGraph,
    ThreadClose,
    Tier,
    rejected_kind,
)

logger = logging.getLogger(__name__)

DEFAULT_URL = "ws://localhost:8182/gremlin"


class GraphWriteError(RuntimeError):
    """A graph write failure annotated with the operation and affected entity."""


class GraphUnavailable(RuntimeError):
    """The graph is not answering, said in words the operator can act on.

    `DriverRemoteConnection.__init__` opens no socket, so a graph that is down does
    not fail here — it fails at the first traversal, inside the driver, as an
    `aiohttp` transport error. Whoever asked then reads
    `Cannot connect to host localhost:8182 ssl:default [Connect call failed ...]`,
    and every guard written around `connect()` is dead code for the case it was
    written for. `connect` probes the port before handing back a source, so the
    failure lands where those guards already are and carries the same diagnosis
    `thalamus init --check` prints.
    """


def split_ws(url: str) -> tuple[str | None, int]:
    """host/port out of ws://host:port/path, without importing a URL parser."""
    rest = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = rest.partition(":")
    if not host:
        return None, 0
    try:
        return host, int(port or 8182)
    except ValueError:
        return None, 0


def probe_socket(url: str, timeout: float = 2.0) -> str | None:
    """`None` when something is listening; the reason when nothing is.

    A bounded TCP connect, which is the stage that separates "the container is not
    up" — the first-run case — from every other way a traversal can fail. It says
    nothing about whether the peer speaks Gremlin: `install._probe_graph` runs a
    real traversal for that, and only once this has passed.
    """
    host, port = split_ws(url)
    if host is None:
        return f"could not parse a host:port out of {url}"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        if probe.connect_ex((host, port)) != 0:
            return f"nothing listening on {host}:{port}"
    return None


def graph_down_detail(reason: str) -> str:
    """A graph-down reason plus the command that fixes it — one text, every surface.

    `thalamus init --check` reaches this from a deliberate probe and the recall
    tools reach it from a read they wanted to do, and a first-time user should not
    get two different accounts of the same container being down.
    """
    return (f"{reason} — start it with `docker compose up -d` in {PROJECT_ROOT}, "
            "then re-run `thalamus init --check`")


def connect(url: str = DEFAULT_URL) -> GraphTraversalSource:
    """A traversal source, or a refusal that says why — never a source that cannot read.

    The probe costs one localhost TCP connect and buys the difference between a
    guard that fires and one that cannot (see `GraphUnavailable`).
    """
    down = probe_socket(url)
    if down is not None:
        raise GraphUnavailable(graph_down_detail(down))
    connection = DriverRemoteConnection(url, "g")
    # Every traversal this source runs is timed by shape (substrate/spans.py). The
    # wrap goes on before the source exists, so no caller can hold an untimed one.
    spans.instrument(connection)
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
    # A long-lived process (the MCP server) opens and closes a connection per call
    # and may never exit; the span ledger would otherwise only ever see its atexit.
    spans.maybe_flush()


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
    columns — collapsing them costs 12.2 accuracy points in TSM. This is
    the transaction-time axis only. Valid time — when a fact stopped being true — is a
    second axis this does not attempt, and the decision log's dated refusal stands.

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
    derivation closure and a property could not be walked.
    """
    return {
        "tier": int(provenance.tier),
        "source": provenance.source,
        "ingested_at": provenance.ingested_at.isoformat(),
    }


# Source properties a matching upsert may not silently rewrite.
#
# `tier` is where every DERIVED_FROM chain terminates — effective trust is the floor of
# the derivation chain — so the same bytes arriving under a friendlier
# provenance must never *raise* trust. The two readings combine to the least trusted
# instead, which can lower trust and never lift it.
#
# `origin` is the key `_article_heads` searches by. Rewriting it moves an article's
# supersession lineage under readers that already walked it, and an article Source
# carries no body digest to detect the move with. `source` travels with it because
# `KnowledgeBatch.default_provenance` derives one from the other — freezing the address
# but not the provenance string that restates it leaves the two disagreeing silently.
_SOURCE_WRITE_ONCE = ("tier", "origin", "source")

# Held at the first value once set. `tier` is not among them: it has its own rule below,
# because trust must still be able to fall.
_SOURCE_HELD_FIRST = ("origin", "source")


def _source_on_match(
    g: GraphTraversalSource, source_vid: str, properties: dict[str, object]
) -> dict[str, object]:
    """The subset of a Source's properties a matching upsert may refresh.

    Identical bytes in one scope hash to one vertex id, so a re-ingest of the same
    document lands here as a match. Title, size and timestamps are refreshable; trust
    and lineage identity are not. Those are held at what the graph already carries, and
    an attempt to change either is **reported** rather than applied — a corpus can be
    built entirely out of successful operations and still be wrong, and a silent
    relabel is how.
    """
    refreshable = {k: v for k, v in properties.items() if k not in _SOURCE_WRITE_ONCE}
    try:
        rows = g.V(source_vid).value_map(*_SOURCE_WRITE_ONCE).limit(1).to_list()
    except Exception:
        # A read that *failed* is not a read that found nothing. `to_list()` on a
        # missing vertex returns [] without raising, so this branch is a real fault —
        # a dropped connection, a serializer error — and the held values are unknown.
        # Fail closed: write none of the protected properties and leave whatever the
        # graph holds. Safe because this never feeds `Merge.on_create`, so a genuine
        # first write still lands with full provenance.
        logger.warning(
            "Source %s: could not read held provenance; leaving tier, origin and "
            "source untouched on this match",
            source_vid,
        )
        return refreshable
    stored = rows[0] if rows and isinstance(rows[0], dict) else {}

    def held(key: str) -> object:
        value = stored.get(key)
        return value[0] if isinstance(value, list) and value else value

    def as_tier(value: object) -> int:
        # Written as an int and read back as one; a digit string from an older
        # writer converts the same way. Anything else is not a tier.
        if isinstance(value, int | str):
            return int(value)
        raise TypeError(f"Source {source_vid}: tier property is not a number: {value!r}")

    held_tier, incoming_tier = held("tier"), properties.get("tier")
    if incoming_tier is None:
        pass  # nothing offered; never write an absent property as null
    elif held_tier is None:
        # Nothing recorded — a first write, or a vertex predating the property. Let the
        # incoming value through, or the node would end up with no tier at all and fail
        # the contract's provenance obligation.
        refreshable["tier"] = incoming_tier
    elif as_tier(incoming_tier) != as_tier(held_tier):
        keep = max(as_tier(held_tier), as_tier(incoming_tier))
        refreshable["tier"] = keep
        logger.warning(
            "Source %s holds tier %s and was re-written at tier %s; keeping %s — "
            "effective trust is the floor of the derivation chain",
            source_vid,
            held_tier,
            incoming_tier,
            keep,
        )

    for key in _SOURCE_HELD_FIRST:
        if key not in properties:
            continue
        held_value, incoming = held(key), properties.get(key)
        if not held_value:
            refreshable[key] = incoming
        elif incoming and incoming != held_value:
            logger.warning(
                "Source %s holds %s %s and was re-written with %s; keeping the first — "
                "identical bytes reached under two addresses",
                source_vid,
                key,
                held_value,
                incoming,
            )

    return refreshable


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
        "project_evidence": session.project_evidence.value if session.project_evidence else "",
        "cwd": session.cwd,
        "repo_root": session.repo_root,
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


def _held_projections(
    g: GraphTraversalSource, identifiers: list[str]
) -> dict[str, tuple[str, str]]:
    """identifier -> the `(repo, path)` already on that Artifact, where one exists.

    Both halves, because a session that cannot anchor an artifact has to write the held
    pair back unchanged — carrying only the repo would blank the path on every write
    that had nothing to say.

    Fetched in one query rather than per artifact: a session touching fifty files would
    otherwise pay fifty round trips to learn what it is about to reconcile against.
    """
    if not identifiers:
        return {}
    rows = (
        g.V().has_label("Artifact").has("identifier", P.within(identifiers))
        .project("identifier", "repo", "path").by("identifier")
        .by(__.coalesce(__.values("repo"), __.constant("")))
        .by(__.coalesce(__.values("path"), __.constant("")))
        .to_list()
    )
    return {
        str(row["identifier"]): (str(row["repo"]), str(row["path"])) for row in rows
    }


def _project_artifact(identifier: str, registry: list[str], repo_root: str) -> tuple[str, str]:
    """This session's reading of an artifact's `(repo, path)`.

    An absolute path is cut against the registry; a relative one is this session's, so
    the session's own checkout anchors it. A session outside any checkout anchors
    nothing, which is the honest answer rather than a gap.
    """
    if identifier.startswith("/"):
        return relativize(identifier, registry)
    if not repo_root:
        return "", ""
    return PurePosixPath(repo_root.rstrip("/")).name, identifier


def _reconcile(held: tuple[str, str] | None, repo: str, path: str) -> tuple[str, str]:
    """What to write, given what the artifact already carries.

    Absence is not disagreement — the rule the project migration was rebuilt around.
    A session that cannot anchor an artifact says nothing about it and must not erase
    another session's answer; a session that anchors it to a *different* checkout does
    disagree, and the honest result of two owners is none.
    """
    if held is None or not held[0]:
        return repo, path
    if not repo:
        return held
    return (repo, path) if repo == held[0] else ("", "")


def _upsert_artifacts(g: GraphTraversalSource, session: SessionGraph) -> dict[str, str]:
    """Upsert Artifact nodes. Returns identifier -> vertex ID.

    Artifacts are GLOBAL: one vertex per identifier, shared across every scope, merged on
    identifier alone. Two experts touching the same file land on the same node by design —
    that is what makes artifacts the join key between scopes (contract/ontology.py).

    The raw tool-call string is a weak identity — one file arrives absolute from one
    call and repo-relative from the next — so a derived `(repo, path)` is written
    beside it and *is* the join key. The identifier itself is never re-keyed: it feeds
    `vid("Artifact", identifier)`, so moving it breaks every citation ever minted, and
    it is the string the tool call actually carried, where a derivation over it is an
    inference.

    Anchoring here uses the session's own `repo_root` alongside every root the graph
    already proves, so a file lands projected as it is written rather than waiting for
    `thalamus derive-artifact-paths` to sweep. Absence and disagreement are kept apart,
    the same distinction the batch makes: a session that cannot anchor an artifact
    leaves an existing projection alone, while a session that anchors it *differently*
    clears it, because an artifact reached from two checkouts has no single owner and
    inventing one is the false merge re-keying was rejected for.
    """
    artifact_vids: dict[str, str] = {}
    try:
        registry = checkout_registry(g)
        if session.repo_root and session.repo_root.rstrip("/") not in registry:
            registry = sorted(
                [*registry, session.repo_root.rstrip("/")], key=len, reverse=True
            )
        held = _held_projections(g, [a.identifier for a in session.artifacts])
        projectable = True
    except Exception as exc:
        # Fail closed, the same way a Source's protected properties do: a read that
        # failed is not a read that found nothing, and without `held` this cannot tell
        # absence from disagreement — so it would overwrite another session's anchor
        # with a guess. The projection is derived and `thalamus derive-artifact-paths`
        # recomputes it; the write itself must not be held hostage to that.
        logger.warning("artifact projection unavailable, writing without it: %s", exc)
        registry, held, projectable = [], {}, False

    for artifact in session.artifacts:
        artifact_vid = vid("Artifact", artifact.identifier)
        provenance = artifact.provenance or session.default_provenance()
        properties = {
            "type": artifact.type.value,
            "project": artifact.project or session.project or "",
            **_provenance_properties(provenance),
        }
        if projectable:
            repo, path = _project_artifact(artifact.identifier, registry, session.repo_root)
            properties["repo"], properties["path"] = _reconcile(
                held.get(artifact.identifier), repo, path
            )

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
    session distilled more than once while its transcript grew holds several snapshots,
    and the lineage is what gives consumers a defined "current"
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
            .option(Merge.on_match, _source_on_match(g, source_vid, properties))
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
        # `about`, `references` and `alternatives` are excluded for the same reason
        # `derived_from` is on provenance: relationships become edges (and, for an
        # alternative, a node), never list-valued properties.
        exclude={
            "provenance", "artifacts", "kind", "description", "about", "references",
            "alternatives",
        },
    )
    # `anchors` is the one list that *is* a property — message UUIDs, joined the way
    # `TOUCHES.anchors` is, so one convention reads both.
    return {
        key: ",".join(str(v) for v in value) if isinstance(value, list) else value
        for key, value in fields.items()
        if value is not None and value != []
    }


def _write_claims(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
) -> dict[str, str]:
    """Write Claim nodes (decisions, problems, solutions) and their edges."""
    claim_vids: dict[str, str] = {}

    for claim in session.claims():
        claim_vid = _upsert_claim(g, session, session_vid, artifact_vids, claim)
        claim_vids[claim.content_id()] = claim_vid
        for alternative in getattr(claim, "alternatives", []):
            _write_alternative(g, session, session_vid, artifact_vids, claim_vid, alternative)

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


def _upsert_claim(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
    claim: Claim,
    extra: Mapping[str, object] | None = None,
) -> str:
    """One Claim vertex with the edges every claim carries: CONTAINS from its session,
    TOUCHES to its artifacts, DERIVED_FROM to its origins, USES to its references."""
    claim_vid = vid("Claim", claim.content_id(), session.scope)
    provenance = claim.provenance or session.default_provenance()

    properties = {
        "kind": claim.kind,
        "description": claim.description,
        "scope": session.scope,
        **_claim_properties(claim),
        **(extra or {}),
        **_provenance_properties(provenance),
    }

    graph_traversal = (
        g.merge_v({T.id: claim_vid, T.label: "Claim"})
        .option(Merge.on_create, {T.id: claim_vid, **properties})
        .option(Merge.on_match, properties)
    )
    _iterate(graph_traversal, "upsert Claim", claim_vid)

    _ensure_edge(g, session_vid, claim_vid, "CONTAINS")

    for artifact_id in claim.artifacts:
        if artifact_id in artifact_vids:
            _ensure_edge(g, claim_vid, artifact_vids[artifact_id], "TOUCHES")

    for origin_vid in provenance.derived_from:
        _ensure_edge(g, claim_vid, origin_vid, "DERIVED_FROM")

    _write_references(g, claim_vid, getattr(claim, "references", []))
    return claim_vid


def _write_alternative(
    g: GraphTraversalSource,
    session: SessionGraph,
    session_vid: str,
    artifact_vids: dict[str, str],
    decision_vid: str,
    alternative: Alternative,
) -> None:
    """The option a decision turned down, as a claim of its own.

    Kind `<scope>/rejected`, contained by the session like any episodic claim, and
    reached from the decision by `USES {role: rejected, reason}` — the reason lives on
    the edge, so the same option refused by two decisions for two reasons converges on
    one node carrying both. The option's own `references` become USES edges from it,
    which is the whole point of its being a node: the reason it lost is often a
    literature claim, and a property list could not point at one.
    """
    option = Claim(
        kind=rejected_kind(session.scope),
        description=alternative.description,
        provenance=session.default_provenance(),
    )
    extra = {"anchors": ",".join(alternative.anchors)} if alternative.anchors else None
    option_vid = _upsert_claim(g, session, session_vid, artifact_vids, option, extra)
    _write_references(g, option_vid, alternative.references)
    qualification: dict[str, object] = {"role": "rejected"}
    if alternative.reason:
        qualification["reason"] = alternative.reason
    _ensure_edge(g, decision_vid, option_vid, "USES", qualification)


def _write_references(g: GraphTraversalSource, claim_vid: str, references: list[str]) -> None:
    """Claim -[USES {role: reason}]-> Claim | Chunk, one per knowledge item the claim
    reasoned with.

    Existence and label are checked first, on the thread_refs rule: an ID the model
    invented names no vertex, mergeE cannot create an edge to a missing one, and a
    reference to a Session or a Source is not a knowledge item. Dropping either loses
    nothing real. A claim naming itself is dropped the same way.

    `verified` is deliberately not written here. It is `eval sync`'s stamp, taken from
    the traces of the sessions containing this claim, and re-asserting the claim must
    not erase it — mergeE's on-match sets only the keys given, so `role` is all this
    write touches on an edge that already exists.
    """
    for target_vid in dict.fromkeys(references):
        if not target_vid or target_vid == claim_vid:
            continue
        if not g.V(target_vid).has_label("Claim", "Chunk").has_next():
            logger.warning(
                "reference %r on %s names no Claim or Chunk; dropping", target_vid, claim_vid
            )
            continue
        _ensure_edge(g, claim_vid, target_vid, "USES", {"role": "reason"})


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
    head for the same origin — versioning stays visible to the eval loop.
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
        # in is a fact about the document. The ingestion protocol requires it on every
        # write; claims reach it by walking DERIVED_FROM.
        "feed": batch.feed,
        **_provenance_properties(source.provenance or provenance),
    }
    graph_traversal = (
        g.merge_v({T.id: source_vid, T.label: "Source"})
        .option(Merge.on_create, {T.id: source_vid, **properties})
        .option(Merge.on_match, _source_on_match(g, source_vid, properties))
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

    # Chunks before claims, so the anchor edge has something to point at.
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
        # provenance-mediated rather than provenance-free.
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
    """Open one consultation exchange record — the mint IS the write.

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


def write_thread_close(
    g: GraphTraversalSource,
    close: ThreadClose,
) -> str:
    """Close a thread on an operator's authority, with no session behind it.

    `Agent -[RESOLVES {basis, ...}]-> Thread`. Distillation's bare
    `Session -[RESOLVES]-> Thread` is untouched and both coexist: one edge label at two
    levels of detail, which is the qualification pattern already used by `RETURNS.used`
    and `DERIVED_FROM.anchors`. Anything asking only "is this closed, and by what" keeps
    working against the label alone.

    The Agent is global, so this edge is not a scope crossing and an operator can close
    a thread in any scope without `RESOLVES.may_cross_scope` being relaxed — the
    partition guards a channel for content, and a close carries none. What *is*
    constrained is the payload: `audit_edges` requires `basis` to resolve in the
    thread's own scope, or be global, so a close cannot smuggle a citation its readers
    are confined away from.

    Returns the Agent's vertex ID. Raises `ValueError` if the thread does not exist —
    unlike a distilled `thread_ref`, which is model output and is dropped when it names
    memory that was never formed, this is an operator naming a specific thread, and
    silently writing nothing would report success for work not done.
    """
    thread_vid = vid("Thread", close.thread_id, close.scope)
    if not g.V(thread_vid).has_label("Thread").has_next():
        raise ValueError(
            f"no thread `{close.thread_id}` in scope `{close.scope}` — nothing to close"
        )

    agent_vid = vid("Agent", close.agent)
    graph_traversal = (
        g.merge_v({T.id: agent_vid, T.label: "Agent"})
        .option(
            Merge.on_create,
            {
                T.id: agent_vid,
                "name": close.agent,
                # An Agent is an identity, not an assertion, so its provenance envelope
                # records where the identity came from rather than what it claims.
                "tier": Tier.FIRST_PARTY.value,
                "source": "operator",
                "ingested_at": close.closed_at,
            },
        )
        .option(Merge.on_match, {"name": close.agent})
    )
    _iterate(graph_traversal, "upsert Agent", agent_vid)

    _ensure_edge(g, agent_vid, thread_vid, "RESOLVES", close.edge_properties())

    graph_traversal = (
        g.V(thread_vid).has_label("Thread").property("status", close.status.value)
    )
    _iterate(graph_traversal, "close Thread", thread_vid)
    return agent_vid


def write_trace(
    g: GraphTraversalSource,
    trace_vid: str,
    properties: Mapping[str, object],
    session_vid: str,
    returns: dict[str, dict[str, object] | None],
) -> None:
    """Upsert one retrieval-trace vertex with its edges.

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
    properties: Mapping[str, object] | None = None,
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
