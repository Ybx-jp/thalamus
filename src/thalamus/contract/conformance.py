"""Conformance checks a subgraph must pass before it may be written.

The federation contract (docs/01) in its current form. Obligations are enforced **at
write time, not filtered at read time** — that stance is inherited from the base memory
system's orphan check and is the posture every obligation here adopts.

Two layers live here:

**Write-time** (`check_session`) — what a SessionGraph must satisfy before it may be
written: connectivity, provenance, scope legality.

**Audit-time** (`check_graph`, `thalamus contract check`) — the same obligations
re-verified against the *live graph*. Write-time checks only see what came through the
front door; the audit catches what write-time cannot: drift from schema changes, writes
that bypassed the contract, evidence blobs that went missing under an immutable-looking
URI. The audit functions are pure over plain rows so they are testable without a graph.

Not yet enforced (they need a second scope to be meaningful):
  - manifest validation — declared node/edge types vs. what is actually written
  - projection grants   — what the plane may read from a scope (docs/09 G4)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from thalamus.contract.ontology import (
    EDGES_BY_LABEL,
    NODES_BY_LABEL,
    edge_crosses_scope,
    scope_of,
    vid,
)
from thalamus.substrate.schema import SessionGraph


def referenced_artifacts(session: SessionGraph) -> set[str]:
    """Artifact identifiers that at least one node in the session points at.

    Includes `touched` — a session that edited a file has a direct TOUCHES edge to it, so
    the artifact is reachable even before any claim is extracted. This is what lets the
    deterministic bootstrap (docs/06) satisfy the connectivity invariant with no model in
    the loop.
    """
    return session.referenced_artifact_ids()


def validate_connectivity(session: SessionGraph) -> list[str]:
    """Check that all nodes have at least one edge. Returns a list of issues."""
    referenced = referenced_artifacts(session)
    return [
        f"Orphan artifact: '{artifact.identifier}' has no edges — "
        "reference it from a claim, thread, or the session's touched list, or remove it"
        for artifact in session.artifacts
        if artifact.identifier not in referenced
    ]


def validate_provenance(session: SessionGraph) -> list[str]:
    """Every node must resolve to a provenance envelope.

    A session extraction gets one by default (tier-1, sourced to the session), so this
    only fires when a node supplies provenance explicitly and supplies it badly. It will
    do real work the moment a feed writes tier-2 content (docs/06).
    """
    issues: list[str] = []
    nodes = [
        *((f"artifact '{a.identifier}'", a.provenance) for a in session.artifacts),
        *((f"claim '{c.description[:40]}'", c.provenance) for c in session.claims()),
        *((f"thread '{t.id}'", t.provenance) for t in session.threads),
    ]
    for label, provenance in nodes:
        if provenance is not None and not provenance.source:
            issues.append(f"Provenance without a source: {label} — no provenance, no write")
    return issues


def validate_scope(session: SessionGraph) -> list[str]:
    """Check that every edge this session implies is a legal one.

    Today a session writes within a single scope, so the only cross-scope edges are
    TOUCHES into the global Artifact vertex — which is not a scope crossing at all (see
    ontology.edge_crosses_scope). This check therefore passes trivially now and becomes
    load-bearing at M3, when consultation starts writing edges between scopes. It exists
    at M0.5 so the question "is this edge legal?" already has one place to live.
    """
    issues: list[str] = []
    if not session.scope:
        return ["Session declares no scope — every node must belong to one"]

    session_vid = vid("Session", session.session_id, session.scope)
    targets = [
        *(vid("Claim", claim.content_id(), session.scope) for claim in session.claims()),
        *(vid("Thread", thread.id, session.scope) for thread in session.threads),
    ]
    for target in targets:
        if edge_crosses_scope(session_vid, target):
            issues.append(
                f"Illegal cross-scope edge: {session_vid} -> {target}. Consultation must "
                "route through a session in the main scope, not a direct expert-to-expert "
                "edge (docs/02)."
            )
    return issues


def check_session(session: SessionGraph) -> list[str]:
    """Full contract check. The ancestor of `thalamus contract check <subgraph>`."""
    return [
        *validate_connectivity(session),
        *validate_provenance(session),
        *validate_scope(session),
    ]


def prune_orphan_artifacts(session: SessionGraph) -> SessionGraph:
    """Return a copy of the session with unreachable artifacts removed."""
    referenced = referenced_artifacts(session)
    pruned = [a for a in session.artifacts if a.identifier in referenced]
    if len(pruned) == len(session.artifacts):
        return session
    return session.model_copy(update={"artifacts": pruned})


def check_knowledge(batch) -> list[str]:
    """What an ingestion event must satisfy before it may be written (docs/06).

    Feeds are contract clients like everything else, held to a *stricter* standard
    than sessions: a session's provenance is derivable, a feed's must be explicit.
    """
    issues: list[str] = []

    if not batch.scope or batch.scope == "main":
        issues.append(
            "Feeds write into an expert's knowledge subgraph, never `main` — "
            "the main scope is episodic, and ingested content is not lived experience"
        )

    if not batch.source.origin:
        issues.append("Source has no origin — no provenance, no write (docs/05)")
    if not batch.source.content_hash:
        issues.append("Source has no content_hash — evidence must be retained first")

    if not batch.claims:
        issues.append(
            "Batch asserts nothing — an ingestion with no claims is archival, "
            "and archival alone does not need Thalamus (docs/06)"
        )

    declared_entities = {entity.name for entity in batch.entities}
    referenced = batch.referenced_entity_names()
    for name in sorted(declared_entities - referenced):
        issues.append(
            f"Orphan entity: '{name}' — no claim is about it; entities are reached "
            "through claims, or not at all"
        )
    for name in sorted(referenced - declared_entities):
        issues.append(f"Claim references undeclared entity: '{name}'")

    # Chunks are verbatim by definition, so the only thing to enforce is that they are
    # *reachable and located* — an anchor pointing at no chunk would strand the claim
    # it was meant to ground, which is the one failure that makes the edge worse than
    # its absence (lab/052).
    ordinals = {chunk.ordinal for chunk in batch.chunks}
    if len(ordinals) != len(batch.chunks):
        issues.append("Chunk ordinals are not unique — chunk identity is (source, ordinal)")
    for chunk in batch.chunks:
        if not chunk.text.strip():
            issues.append(f"Empty chunk at ordinal {chunk.ordinal} — a chunk is its text")
        if chunk.end <= chunk.start:
            issues.append(f"Chunk {chunk.ordinal} has a non-positive span ({chunk.start}:{chunk.end})")
    for claim_index, ordinal in sorted(batch.anchors.items()):
        if ordinal not in ordinals:
            issues.append(
                f"Claim {claim_index} anchors to chunk ordinal {ordinal}, which is not "
                "in this batch — a dangling anchor is worse than no anchor"
            )
        if claim_index >= len(batch.claims):
            issues.append(f"Anchor references claim index {claim_index}, out of range")

    for claim in batch.claims:
        if "/" not in claim.kind:
            issues.append(
                f"Knowledge claim kind must be namespaced (`literature/finding`), "
                f"got '{claim.kind}' — core kinds belong to episodic claims"
            )
        if claim.provenance is not None and claim.provenance.tier < 2:
            issues.append(
                f"Claim '{claim.description[:40]}' claims tier "
                f"{int(claim.provenance.tier)} — a feed cannot mint trust above "
                "CURATED; distillation does not launder, and neither does ingestion"
            )

    return issues


# --------------------------------------------------------------------------------------
# Live-graph audit — `thalamus contract check`
# --------------------------------------------------------------------------------------

_PROVENANCE_FIELDS = ("tier", "source", "ingested_at")


@dataclass(frozen=True)
class AuditVertex:
    """One vertex as the audit sees it: identity, label, flat properties."""

    vid: str
    label: str
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEdge:
    label: str
    from_vid: str
    from_label: str
    to_vid: str
    to_label: str
    properties: dict = field(default_factory=dict)


def audit_vertices(vertices: list[AuditVertex]) -> list[str]:
    """Per-vertex obligations: known label, provenance envelope, scope integrity."""
    issues: list[str] = []
    for vertex in vertices:
        node = NODES_BY_LABEL.get(vertex.label)
        if node is None:
            issues.append(f"Unknown vertex label: `{vertex.vid}` is a `{vertex.label}`, "
                          "which the ontology does not declare")
            continue

        missing = [f for f in _PROVENANCE_FIELDS if not vertex.properties.get(f)]
        if missing:
            issues.append(
                f"Provenance hole: `{vertex.vid}` lacks {', '.join(missing)} — "
                "no provenance, no write (docs/05)"
            )

        # The laundering floor, audit-time half (docs/05): a claim that admits its
        # substance came through the transcript's external ingress must not carry
        # first-party trust. The mark and the tier are both written by our own
        # pipeline, so a mismatch means something wrote around apply_ingress_floor.
        if vertex.label == "Claim" and vertex.properties.get("external") is True:
            tier = vertex.properties.get("tier")
            if isinstance(tier, int) and tier < 2:
                issues.append(
                    f"Laundered ingress: `{vertex.vid}` is marked external but carries "
                    f"tier {tier} — transcript-mediated content keeps third-party "
                    "trust (docs/05)"
                )

        vid_scope = scope_of(vertex.vid)
        declared = vertex.properties.get("scope")
        if node.scoped:
            if vid_scope is None:
                issues.append(f"Scope integrity: `{vertex.vid}` ({vertex.label} is scoped) "
                              "has no scope segment in its vertex ID")
            elif declared != vid_scope:
                issues.append(
                    f"Scope integrity: `{vertex.vid}` declares scope "
                    f"`{declared or '(none)'}` but its ID says `{vid_scope}` — "
                    "a node that lies about its scope defeats server-side scoping"
                )
        elif vid_scope is not None or declared:
            issues.append(
                f"Scope integrity: `{vertex.vid}` ({vertex.label} is global) "
                "carries a scope — globals are the join key and must not be claimed"
            )
    return issues


def audit_edges(edges: list[AuditEdge]) -> list[str]:
    """Per-edge obligations: known label, legal scope crossing, lineage endpoints."""
    issues: list[str] = []
    for edge in edges:
        declared = EDGES_BY_LABEL.get(edge.label)
        if declared is None:
            issues.append(
                f"Unknown edge label: `{edge.from_vid}` -[{edge.label}]-> `{edge.to_vid}`"
            )
            continue

        if not declared.may_cross_scope and edge_crosses_scope(edge.from_vid, edge.to_vid):
            issues.append(
                f"Illegal cross-scope edge: `{edge.from_vid}` -[{edge.label}]-> "
                f"`{edge.to_vid}`. Consultation routes through a main-scope session, "
                "never expert-to-expert (docs/02)"
            )

        # An Agent-written close carries its evidence in properties rather than in the
        # closer, so the safety property moves with it: the *basis* must be readable
        # from the thread's own scope. Topology already permits the edge — an Agent is
        # global, so `edge_crosses_scope` waves it through — and that is correct,
        # because a close moves no content. What would move content is a basis
        # pointing into a third scope: the thread's readers would then hold a citation
        # they cannot resolve, and the close would have smuggled a reference across a
        # boundary the partition exists to keep closed. Constrain the payload, not the
        # topology.
        if edge.label == "RESOLVES" and edge.from_label == "Agent":
            basis = edge.properties.get("basis")
            if not basis:
                issues.append(
                    f"Uncited close: `{edge.from_vid}` -[RESOLVES]-> `{edge.to_vid}` "
                    "carries no basis — an agent-written close cites the evidence it "
                    "rests on, or it is a status flip with a name on it"
                )
            else:
                basis_scope = scope_of(str(basis))
                thread_scope = scope_of(edge.to_vid)
                if basis_scope is not None and basis_scope != thread_scope:
                    issues.append(
                        f"Unreadable basis: `{edge.from_vid}` -[RESOLVES]-> "
                        f"`{edge.to_vid}` cites `{basis}` from scope `{basis_scope}`, "
                        f"which a reader confined to `{thread_scope}` cannot resolve"
                    )

        if edge.label == "SUPERSEDES" and (
            edge.from_label != "Source" or edge.to_label != "Source"
        ):
            issues.append(
                f"SUPERSEDES between non-Sources: `{edge.from_vid}` "
                f"({edge.from_label}) -> `{edge.to_vid}` ({edge.to_label}) — "
                "lineage is a fact about evidence snapshots only"
            )

        if edge.label == "CONSULTS" and (
            edge.from_label != "Session" or edge.to_label != "Exchange"
        ):
            issues.append(
                f"CONSULTS between wrong endpoints: `{edge.from_vid}` "
                f"({edge.from_label}) -> `{edge.to_vid}` ({edge.to_label}) — "
                "a consultation is a Session's edge to its Exchange record (docs/02)"
            )
    return issues


_EXCHANGE_STATUSES = frozenset({"open", "answered"})


def audit_exchanges(vertices: list[AuditVertex], edges: list[AuditEdge]) -> list[str]:
    """Exchange-record obligations — the ticket protocol's contract half (docs/02).

    An answered exchange must carry at least one `role: citation` REFERENCES edge:
    consult_answer only closes on validated citations, so an answered-but-uncited
    exchange in the live graph means something wrote around the protocol.
    """
    issues: list[str] = []
    cited = {
        edge.from_vid
        for edge in edges
        if edge.label == "REFERENCES" and edge.properties.get("role") == "citation"
    }
    for vertex in vertices:
        if vertex.label != "Exchange":
            continue
        status = str(vertex.properties.get("status") or "")
        if status not in _EXCHANGE_STATUSES:
            issues.append(
                f"Exchange `{vertex.vid}` has status `{status or '(none)'}` — "
                f"the protocol knows {', '.join(sorted(_EXCHANGE_STATUSES))}"
            )
        if status == "answered" and vertex.vid not in cited:
            issues.append(
                f"Exchange `{vertex.vid}` is answered but cites nothing — "
                "consult_answer is the only close path and it validates citations; "
                "this exchange was closed around the protocol"
            )
    return issues


def _edgeless_by_construction(vertex: AuditVertex) -> bool:
    """The one vertex the protocol creates with nothing to point at.

    A full ticket's Exchange is born connected: the server assembles a brief and each
    node it served becomes a `role: brief` REFERENCES edge. The quick tier drops the
    brief on purpose (docs/02), so an open quick exchange has no edges until it is
    answered and its citations land — which is the state a fork that never answered
    leaves behind. That is honest data, not an unreachable node: `brief_served: false`
    and `fork_error` say exactly what happened. An *answered* quick exchange is not
    exempt; it must cite, like any other.
    """
    return (
        vertex.label == "Exchange"
        and str(vertex.properties.get("protocol") or "") == "quick"
        and str(vertex.properties.get("status") or "") == "open"
    )


def audit_orphans(vertices: list[AuditVertex], edges: list[AuditEdge]) -> list[str]:
    """Every vertex must be reachable by at least one edge — the graph-level twin of
    the write-time orphan check."""
    connected = {e.from_vid for e in edges} | {e.to_vid for e in edges}
    return [
        f"Orphan vertex: `{v.vid}` ({v.label}) has no edges"
        for v in vertices
        if v.vid not in connected and not _edgeless_by_construction(v)
    ]


def audit_evidence(vertices: list[AuditVertex], archive_base: Path | None = None) -> list[str]:
    """Every Source URI must resolve to retained bytes.

    The provenance floor is only a floor if the bytes are actually there: a Source whose
    blob is gone is a belief chain terminating in a dangling pointer, which is precisely
    the fog docs/03's inspector exists to prevent.
    """
    from thalamus.archive import archive_dir

    root = archive_base or archive_dir()
    issues: list[str] = []
    for vertex in vertices:
        if vertex.label != "Source":
            continue
        content_hash = str(vertex.properties.get("content_hash") or "")
        if not content_hash:
            issues.append(f"Evidence floor: `{vertex.vid}` has no content_hash")
            continue
        if not any((root / content_hash[:2]).glob(f"{content_hash}*")):
            issues.append(
                f"Evidence floor: `{vertex.vid}` points at archive://{content_hash[:12]}… "
                "but no such blob is retained"
            )
    return issues


def check_graph(g, archive_base: Path | None = None) -> tuple[list[str], dict[str, int]]:
    """Audit the live graph against the contract. Returns (issues, counts)."""
    vertices, edges = _fetch(g)
    issues = [
        *audit_vertices(vertices),
        *audit_edges(edges),
        *audit_exchanges(vertices, edges),
        *audit_orphans(vertices, edges),
        *audit_evidence(vertices, archive_base),
    ]
    return issues, {"vertices": len(vertices), "edges": len(edges)}


def _fetch(g) -> tuple[list[AuditVertex], list[AuditEdge]]:
    """Pull the whole graph into plain rows. Fine at this graph's size (~10^3 nodes);
    pagination is a problem worth having later."""
    from gremlin_python.process.traversal import Direction, T

    vertices = []
    for row in g.V().value_map(True).to_list():
        properties = {
            str(key): (value[0] if isinstance(value, list) and value else value)
            for key, value in row.items()
            if key not in (T.id, T.label)
        }
        vertices.append(
            AuditVertex(vid=str(row[T.id]), label=str(row[T.label]), properties=properties)
        )

    edges = []
    for row in g.E().element_map().to_list():
        out_v = row.get(Direction.OUT) or {}
        in_v = row.get(Direction.IN) or {}
        edges.append(
            AuditEdge(
                label=str(row.get(T.label)),
                from_vid=str(out_v.get(T.id, "")),
                from_label=str(out_v.get(T.label, "")),
                to_vid=str(in_v.get(T.id, "")),
                to_label=str(in_v.get(T.label, "")),
                properties={
                    str(key): value
                    for key, value in row.items()
                    if key not in (T.id, T.label, Direction.OUT, Direction.IN)
                },
            )
        )
    return vertices, edges
