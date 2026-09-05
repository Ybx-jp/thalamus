"""Conformance checks a subgraph must pass before it may be written.

The federation contract in its current form. Obligations are enforced **at
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

Both layers check written data **against** the ontology. `audit_declarations` runs the
comparison the other way — the ontology against what writers produce — which is the only
direction that catches a declaration nothing backs. `audit_reader_projection` closes the
third side of the same triangle, declared → written → read: a field the writer puts on a
vertex that no read path ever names is persisted and structurally unreachable. Findings
in both directions are `ADVISORY`: absence in one graph, or in one scan, is not proof,
and a check that can fail forever on unfixable history is a check that gets ignored.
`audit_content_addresses` asks the one question that needs no second party at all —
whether a content-addressed vertex's id still agrees with the content it was hashed
from — and reports on the same terms.

Not yet enforced (needs a second scope to be meaningful):
  - projection grants — what the plane may read from a scope
"""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import TypeVar, Union, get_args, get_origin

from pydantic import BaseModel

from thalamus.contract.ontology import (
    CORE_EDGES,
    CORE_NODES,
    EDGES_BY_LABEL,
    MAIN_SCOPE,
    NODES_BY_LABEL,
    edge_crosses_scope,
    scope_of,
    vid,
)
from thalamus.substrate.schema import (
    Artifact,
    Chunk,
    Claim,
    Entity,
    SessionGraph,
    Source,
    Thread,
    Touch,
)

VIOLATION = "violation"
ADVISORY = "advisory"

_M = TypeVar("_M", bound=BaseModel)


class Issue(str):
    """A contract finding, carrying whether it may fail the run.

    A `str` subclass rather than a wrapper: every consumer that prints, joins or
    substring-tests an issue keeps working unchanged, and only the code that has to
    route on severity needs to know severity exists.

    `VIOLATION` is the default here and in `severity_of`, so a finding raised by code
    that predates severity — or by code that forgets it — fails the run. Fail-closed is
    the only safe default for a gate.
    """

    severity: str

    def __new__(cls, message: str, severity: str = VIOLATION) -> Issue:
        issue = super().__new__(cls, message)
        issue.severity = severity
        return issue


def severity_of(issue: str) -> str:
    """Severity of an issue, defaulting to VIOLATION for a plain string."""
    return getattr(issue, "severity", VIOLATION)


def advisory(message: str) -> Issue:
    return Issue(message, ADVISORY)


def referenced_artifacts(session: SessionGraph) -> set[str]:
    """Artifact identifiers that at least one node in the session points at.

    Includes `touched` — a session that edited a file has a direct TOUCHES edge to it, so
    the artifact is reachable even before any claim is extracted. This is what lets the
    deterministic bootstrap satisfy the connectivity invariant with no model in
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
    do real work the moment a feed writes tier-2 content.
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
                "edge."
            )
    return issues


def check_session(session: SessionGraph) -> list[str]:
    """Full contract check. The ancestor of `thalamus contract check <subgraph>`."""
    return [
        *validate_connectivity(session),
        *validate_provenance(session),
        *validate_scope(session),
    ]


class ContractViolation(RuntimeError):
    """A session that does not satisfy the contract was offered to the write path."""

    def __init__(self, session_id: str, issues: list[str]) -> None:
        self.session_id = session_id
        self.issues = list(issues)
        detail = "\n".join(f"  - {issue}" for issue in self.issues)
        super().__init__(
            f"Session {session_id} does not satisfy the federation contract:\n{detail}"
        )


def write_session_checked(g, session: SessionGraph) -> str:
    """Check the contract, then write. The gated entry point to `write_session`.

    The gate cannot live in `substrate/writer.py`, which is where it would most
    obviously belong: the substrate sits *below* the contract — it knows nodes and
    edges, not scopes, tiers or federation — and importing `conformance` there would
    invert the layering the whole boundary rests on. So the gate sits here, one level
    up, and the obligation on callers changes from "remember to check" to "use this
    door".

    That obligation was previously discharged by convention and unevenly: of the three
    `write_session` call sites, two checked and `thalamus write` — the one that takes
    an operator-supplied JSON file, the least trustworthy input of the three — did not.

    Callers that need the issues for reporting should still call `check_session`
    themselves and handle them; re-checking here is pure over an in-memory model and
    costs nothing.
    """
    from thalamus.substrate.writer import write_session

    issues = [issue for issue in check_session(session) if severity_of(issue) != ADVISORY]
    if issues:
        raise ContractViolation(session.session_id, issues)
    return write_session(g, session)


def prune_orphan_artifacts(session: SessionGraph) -> SessionGraph:
    """Return a copy of the session with unreachable artifacts removed."""
    referenced = referenced_artifacts(session)
    pruned = [a for a in session.artifacts if a.identifier in referenced]
    if len(pruned) == len(session.artifacts):
        return session
    return session.model_copy(update={"artifacts": pruned})


def check_knowledge(batch) -> list[str]:
    """What an ingestion event must satisfy before it may be written.

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
        issues.append("Source has no origin — no provenance, no write")
    if not batch.source.content_hash:
        issues.append("Source has no content_hash — evidence must be retained first")

    if not batch.claims:
        issues.append(
            "Batch asserts nothing — an ingestion with no claims is archival, "
            "and archival alone does not need Thalamus"
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
    # its absence.
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

# Every vertex property key a rule in this module reads by name. `_fetch` asks the graph
# for these and nothing else.
#
# The reason it is a list rather than "everything": `g.V().valueMap(true)` ships every
# property of every vertex, and ~58% of the vertices here are Chunks carrying ~1,500
# characters of `text` apiece. Measured on the live graph (47,450 vertices), asking for
# these nine instead took the vertex read from a 5,054 ms median to 2,443 ms.
#
# **It fails open.** A rule that reads a key missing from this tuple sees `None` and
# passes silently rather than erroring — the check would go on reporting green while no
# longer checking. `tests/test_contract_fetch.py` closes that by deriving the read set
# from this module's own source and asserting this tuple covers it, so adding a rule
# that reads a new key fails the suite rather than disabling itself.
_AUDIT_VERTEX_KEYS = (
    "tier", "source", "ingested_at", "external", "scope",
    "kind", "status", "protocol", "content_hash",
)

# The two edge property keys read by name: `basis` on an Agent's RESOLVES, `role` on
# REFERENCES. The full edge property *vocabulary* is a separate question, asked as an
# aggregate — see `edge_property_vocabulary`.
_AUDIT_EDGE_KEYS = ("role", "basis", "verified")


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
                "no provenance, no write"
            )

        # The laundering floor, audit-time half: a claim that admits its
        # substance came through the transcript's external ingress must not carry
        # first-party trust. The mark and the tier are both written by our own
        # pipeline, so a mismatch means something wrote around apply_ingress_floor.
        if vertex.label == "Claim" and vertex.properties.get("external") is True:
            tier = vertex.properties.get("tier")
            if isinstance(tier, int) and tier < 2:
                issues.append(
                    f"Laundered ingress: `{vertex.vid}` is marked external but carries "
                    f"tier {tier} — transcript-mediated content keeps third-party "
                    "trust"
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
                "never expert-to-expert"
            )

        # A cross-scope `USES` nothing served is the only reading of a reference this
        # audit can make. Not a rule on the target's shape: a session-contained claim
        # in another scope is a legal, routine target — the ticket grant serves expert
        # episodic memory into the consulting session, and a REFERENCES {citation}
        # edge already points at 1,025 of them. What separates a citation from a
        # fabrication is provenance, and `verified` is where sync records it.
        #
        # Advisory, and deliberately so. `verified: false` is also what a legitimate
        # acquisition looks like when it arrived by a channel the tap does not watch —
        # a file read, an issue body, the ambient injection at session start — so this
        # says look, never fail. Absent is not false: an unsynced edge is unexamined,
        # and reporting it would count sync's backlog as findings.
        if (
            edge.label == "USES"
            and edge.properties.get("verified") is False
            and edge_crosses_scope(edge.from_vid, edge.to_vid)
        ):
            issues.append(advisory(
                f"Unverified cross-scope USES: `{edge.from_vid}` -[USES]-> "
                f"`{edge.to_vid}` reaches another scope, and no trace served that "
                "target into any session containing the claim"
            ))

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

        issues.extend(_endpoint_issues(edge, declared))
    return issues


def _endpoint_issues(edge: AuditEdge, declared) -> list[str]:
    """Endpoint typing, from the ontology's declared `from_labels`/`to_labels`.

    These were documentation for twelve of the fourteen edge types — direction strings
    in a `note`, which nothing could check, so an edge written backwards or between the
    wrong labels passed the contract. Promoting them to fields makes the same intent an
    invariant, and the severity is per-type: strict where the whole live graph has been
    measured conforming, advisory where it has not.
    """
    wrong: list[str] = []
    if declared.from_labels and edge.from_label not in declared.from_labels:
        wrong.append(f"source is a {edge.from_label}, not {_or_list(declared.from_labels)}")
    if declared.to_labels and edge.to_label not in declared.to_labels:
        wrong.append(f"target is a {edge.to_label}, not {_or_list(declared.to_labels)}")
    if not wrong:
        return []

    message = (
        f"{edge.label} between wrong endpoints: `{edge.from_vid}` ({edge.from_label}) "
        f"-> `{edge.to_vid}` ({edge.to_label}) — {'; '.join(wrong)}"
    )
    return [Issue(message) if declared.strict_endpoints else advisory(message)]


def _or_list(labels: tuple[str, ...]) -> str:
    return " or ".join(labels) if len(labels) < 3 else ", ".join(labels)


_EXCHANGE_STATUSES = frozenset({"open", "answered"})


def audit_exchanges(vertices: list[AuditVertex], edges: list[AuditEdge]) -> list[str]:
    """Exchange-record obligations — the ticket protocol's contract half.

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
    brief on purpose, so an open quick exchange has no edges until it is
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
    the fog the inspector exists to prevent.
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


def audit_declarations(
    vertices: list[AuditVertex],
    edges: list[AuditEdge],
    edge_properties: dict[str, set[str]] | None = None,
) -> list[Issue]:
    """Audit the *ontology* against what writers produce — the other direction.

    Every other check here reads the ontology as ground truth and judges the graph by
    it. Nothing judged the ontology, so a declaration could stop matching reality and
    no run would say so. Three did at once: `DERIVED_FROM.anchors` was declared across
    31,042 edges that carry no properties at all, `ANCHORS` was documented as carrying
    character offsets the data model has no field for, and `RETURNS.judged_terms` was
    written by the eval loop while the ontology named neither it nor half the labels
    RETURNS actually points at. A design that reads `ontology.py` and plans against a
    declared property is planning against nothing.

    Everything here is ADVISORY, for a reason worth keeping straight: absence proves
    nothing on its own. A property legitimately unused in a small graph, an edge type
    declared ahead of the writer that will produce it, an expert kind no feed has
    exercised yet — each is a false positive waiting to happen, and a check that can
    fail forever on unfixable history is a check that gets switched off. What this
    reports is a *count to explain*, not a verdict.
    """
    issues: list[Issue] = []

    vertex_labels = {v.label for v in vertices}
    kinds_seen: dict[str, set[str]] = defaultdict(set)
    for vertex in vertices:
        kind = vertex.properties.get("kind")
        if kind:
            kinds_seen[vertex.label].add(str(kind))

    for node in CORE_NODES:
        if node.label not in vertex_labels:
            issues.append(
                advisory(
                    f"Unwritten node type: `{node.label}` is declared and no vertex "
                    "carries the label"
                )
            )
            continue
        unwritten = [k for k in node.kinds if k not in kinds_seen[node.label]]
        if unwritten:
            issues.append(
                advisory(
                    f"Unwritten {node.label} kind(s): {', '.join(sorted(unwritten))} — "
                    f"declared, and no {node.label} carries them"
                )
            )
        # The other direction. `Claim.kind` is open by design — an expert manifest's
        # `claim_kinds` adds namespaced values without touching this module — so only
        # a bare kind is drift there. Entity and Source have no such extension
        # surface, which makes any undeclared value on them a writer escaping its
        # vocabulary: `literature/finding`, a *claim* kind, sits on 2 Entities today.
        if node.kinds:
            undeclared = sorted(
                k
                for k in kinds_seen[node.label]
                if k not in node.kinds and not (node.label == "Claim" and "/" in k)
            )
            if undeclared:
                issues.append(
                    advisory(
                        f"Undeclared {node.label} kind(s): {', '.join(undeclared)} — "
                        "written, and the ontology does not declare them"
                    )
                )

    edge_labels = {e.label for e in edges}
    # The property vocabulary per edge label. `edge_properties` is the aggregate form,
    # asked of the graph directly because deriving it here requires every edge to carry
    # every property it has — which is the whole reason the row scan cannot be narrowed
    # without it. Deriving from the rows stays the default so that a caller holding
    # complete rows, including every test in this suite, needs to pass nothing.
    properties_seen: dict[str, set[str]]
    if edge_properties is None:
        properties_seen = defaultdict(set)
        for edge in edges:
            properties_seen[edge.label].update(str(key) for key in edge.properties)
    else:
        properties_seen = defaultdict(set, {k: set(v) for k, v in edge_properties.items()})

    for edge_type in CORE_EDGES:
        if edge_type.label not in edge_labels:
            issues.append(
                advisory(
                    f"Unwritten edge type: `{edge_type.label}` is declared and no edge "
                    "carries the label"
                )
            )
            continue
        unwritten = [p for p in edge_type.properties if p not in properties_seen[edge_type.label]]
        if unwritten:
            issues.append(
                advisory(
                    f"Unwritten {edge_type.label} propert(ies): "
                    f"{', '.join(sorted(unwritten))} — declared, and no "
                    f"{edge_type.label} edge sets them"
                )
            )
        undeclared = sorted(
            p for p in properties_seen[edge_type.label] if p not in edge_type.properties
        )
        if undeclared:
            issues.append(
                advisory(
                    f"Undeclared {edge_type.label} propert(ies): "
                    f"{', '.join(undeclared)} — written, and the ontology does not "
                    "declare them"
                )
            )

    return issues


def audit_content_addresses(rows: Sequence[tuple[str, str, str]]) -> list[Issue]:
    """Does a content-addressed Claim still live at the address its content produces?

    `Claim.content_id` hashes `(kind, normalized description)` and `vid` puts that hash
    in the vertex id, so the id is a claim *about* the content — and the only claim in
    the graph that can be re-asked from the vertex alone. Nothing re-asked it. It goes
    stale two ways, both outside the live write path: an identity formula that changed
    under vertices already written, and an identity-bearing property rewritten in place
    without re-minting the id.

    The consequence is not cosmetic. A vertex left behind by a re-key keeps whatever
    edges it acquired afterwards but not the `CONTAINS` the re-key moved to its twin, so
    a provenance walk from it dead-ends with no session — a retrieved claim whose
    evidence chain cannot be walked, which is the property the tier model rests on.
    Whether a twin exists is therefore reported, not just the disagreement: it is what
    separates a duplicate that can be retired from a vertex that is the live record and
    is simply at the wrong address.

    Recomputed through `Claim.content_id` rather than by restating the hash here, so a
    change to the identity function moves this check with it instead of past it.

    ADVISORY on the terms `audit_declarations` states, and for the sharper reason: this
    fires on history no write path can now produce, and every repair is a data decision
    rather than a code one.
    """
    issues: list[Issue] = []
    known = {vertex_id for vertex_id, _, _ in rows}
    twinned: list[str] = []
    orphaned: list[str] = []
    for vertex_id, kind, description in rows:
        expected = Claim(kind=kind, description=description).content_id()
        if vertex_id.rsplit(":", 1)[-1] == expected:
            continue
        twin = vid("Claim", expected, scope=scope_of(vertex_id) or MAIN_SCOPE)
        (twinned if twin in known else orphaned).append(vertex_id)

    if twinned:
        issues.append(
            advisory(
                f"Stale claim address: {len(twinned)} Claim(s) sit at an id their own "
                "(kind, description) no longer produces, and a live twin holds the "
                f"recomputed id — {', '.join(sorted(twinned))}"
            )
        )
    if orphaned:
        issues.append(
            advisory(
                f"Wrong claim address: {len(orphaned)} Claim(s) sit at an id their own "
                "(kind, description) no longer produces, with no vertex at the "
                f"recomputed id — {', '.join(sorted(orphaned))}"
            )
        )
    return issues


# Vertex-producing schema models that are not Claim subtypes, by the graph label they
# land on. `Touch` is the odd one: it becomes TOUCHES edge properties rather than a
# vertex, and it is checked here because an edge property is reachable or unreachable on
# exactly the same terms.
_NODE_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("Artifact", Artifact),
    ("Source", Source),
    ("Entity", Entity),
    ("Thread", Thread),
    ("Chunk", Chunk),
    ("Session", SessionGraph),
    ("TOUCHES", Touch),
)


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_writer_path() -> Path:
    return _package_root() / "substrate" / "writer.py"


def _default_read_paths() -> list[Path]:
    """The code that turns vertex properties back into something a caller sees.

    `substrate` owns graph access, so every module in it apart from the writer and the
    schema is a read path. `conformance` itself is one too: the ingress floor reads
    `Claim.external` off the vertex, which makes that property reachable and used even
    though no retrieval surface renders it. `ontology` is deliberately absent — it
    declares property names, it does not project them, and counting a declaration as a
    read would make the check unable to see the very gap it exists for.
    """
    root = _package_root()
    substrate = sorted(
        path
        for path in (root / "substrate").glob("*.py")
        if path.name not in ("writer.py", "schema.py", "__init__.py")
    )
    return [*substrate, root / "contract" / "conformance.py"]


def _string_constants(path: Path) -> set[str]:
    """Every string literal in a module. A name that appears anywhere in a read path is
    counted as projected — generous on purpose, because a missed read would make this
    check accuse code that works."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _writer_property_names(path: Path) -> set[str]:
    """Property names the writer states literally: dict-literal keys and subscript
    assignments onto a property dict. Both spellings are in use — the artifact
    projection sets `properties["repo"]` after the dict is built."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            names.update(
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                names.add(node.slice.value)
    return names


def _placeholder(annotation: object) -> object:
    """A non-None value of the annotated type.

    Optional fields are what makes this necessary: the writer drops `None`, so a model
    left at its defaults would under-report the fields it actually serializes.
    """
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        for arg in get_args(annotation):
            if arg is not type(None):
                return _placeholder(arg)
        return "x"
    if origin in (list, set, frozenset, tuple):
        args = get_args(annotation)
        return [_placeholder(args[0])] if args else ["x"]
    if origin is dict:
        return {}
    if isinstance(annotation, type):
        # Enum first: this schema's enums subclass `str` and `int` as well.
        if issubclass(annotation, Enum):
            return next(iter(annotation))
        if issubclass(annotation, bool):
            return True
        if issubclass(annotation, datetime):
            return datetime.now(timezone.utc)
        if issubclass(annotation, (int, float)):
            return 1
        if issubclass(annotation, str):
            return "x"
        if issubclass(annotation, BaseModel):
            return _populated(annotation)
    return "x"


def _populated(model: type[_M]) -> _M:
    """An instance with every field set, so nothing drops out as absent.

    Generic in the model so a caller that passed a `Claim` subtype gets one back:
    `_claim_written_fields` hands the result to `writer._claim_properties`, which takes
    a `Claim` and should not be widened to accept anything a `BaseModel` might be.
    """
    return model(**{name: _placeholder(f.annotation) for name, f in model.model_fields.items()})


def _claim_written_fields() -> dict[str, set[str]]:
    """What the writer flattens onto a Claim vertex, per subtype.

    Asked of `_claim_properties` rather than restated from the model, because the
    exclusions are the writer's own: `artifacts` and `about` become edges, `provenance`
    is flattened separately, and a restatement here would drift from all three. This is
    also the half a name-matching tool cannot see — the fields arrive through
    `model_dump`, so no subtype field is ever named as a literal on the write side.
    """
    from thalamus.substrate.writer import _claim_properties

    written: dict[str, set[str]] = {}
    for model in (Claim, *Claim.__subclasses__()):
        try:
            written[model.__name__] = set(_claim_properties(_populated(model)))
        except Exception:
            continue
    return written


def audit_reader_projection(
    read_paths: Sequence[Path] | None = None,
    writer_path: Path | None = None,
) -> list[Issue]:
    """Audit what writers produce against what readers project — the third direction.

    `audit_declarations` asks whether a declaration has a writer behind it. This asks
    the same question one step further along: a field can be declared, written to every
    vertex of its label, and still be unreachable, because nothing on the read side ever
    names it. The value is persisted and no caller can obtain it, which is worse than an
    absent field — the graph carries a fact it cannot answer with, and a design reading
    the schema will plan against a property no retrieval path can return.

    The two sides are asymmetric, which is why a generic static tool misses this. Claim
    subtype fields reach the graph through `model_dump`, so the write side never names
    them; the read side selects a fixed list of properties, so a field nothing projects
    is not mentioned once in any reader. Absence of a *name* is the whole signal, and it
    is only visible by asking the writer what it produces and the read path what it
    mentions, then differencing the two.

    Static by construction — no graph, no connection. What is written is a property of
    the code, not of any one corpus, so a live graph would only add the question of
    whether the corpus happens to exercise the field.

    Everything here is ADVISORY, on the same terms `audit_declarations` states: absence
    proves nothing on its own, and this reads absence twice over.

    Reach limits, reported rather than papered over:
      - A read path outside `substrate` — the CLI, the console, the eval loop, and the
        out-of-repo viewer all query the graph — is not scanned, so a property only
        those project reports here anyway.
      - A reader that projects dynamically, by building property names at runtime or by
        taking whatever `value_map(True)` returns, names nothing and is invisible.
      - Only the writer's literal property names and the Claim serializer are read on
        the write side; a property assembled dynamically is not seen as written.
      - Claim subtypes must be imported to be enumerated, so an expert extension living
        outside `substrate.schema` is checked only if something already loaded it.
      - Declared node types with no schema model are named in their own advisory.
    """
    issues: list[Issue] = []

    projected: set[str] = set()
    for path in read_paths if read_paths is not None else _default_read_paths():
        projected |= _string_constants(path)

    def report(name: str, written: set[str]) -> None:
        unread = sorted(written - projected)
        if unread:
            issues.append(
                advisory(
                    f"Unprojected {name} field(s): {', '.join(unread)} — written to the "
                    "graph, and no read path names them"
                )
            )

    claim_fields = _claim_written_fields()
    base = claim_fields.get("Claim", set())
    report("Claim", base)
    for name in sorted(claim_fields):
        if name != "Claim":
            # Subtype fields only. The shared ones are Claim's to answer for, and
            # repeating them once per subtype would report one gap four times.
            report(name, claim_fields[name] - base)

    writer_names = _writer_property_names(
        writer_path if writer_path is not None else _default_writer_path()
    )
    modelled = {"Claim"}
    for label, model in _NODE_MODELS:
        modelled.add(label)
        report(label, set(model.model_fields) & writer_names)

    unmodelled = sorted(node.label for node in CORE_NODES if node.label not in modelled)
    if unmodelled:
        issues.append(
            advisory(
                f"Outside projection reach: {', '.join(unmodelled)} — declared node "
                "types with no schema model, so nothing compares what is written on "
                "them against what is read"
            )
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
        *audit_declarations(vertices, edges, edge_property_vocabulary(g)),
        *audit_content_addresses(claim_identity_rows(g)),
        *audit_reader_projection(),
    ]
    return issues, {"vertices": len(vertices), "edges": len(edges)}


def claim_identity_rows(g) -> list[tuple[str, str, str]]:
    """Every Claim as `(vertex id, kind, description)` — identity's three columns.

    Asked as its own narrow traversal rather than by widening `_AUDIT_VERTEX_KEYS`.
    `description` is the largest property in the graph — 4.2 MB across 17,559 Claims —
    and no other rule here reads it, so adding it to the shared vertex scan would make
    every audit pay for one. Measured on the live graph: 404 ms median (n=3) for this
    scan against the 2,443 ms the shared vertex read costs. Same trade
    `edge_property_vocabulary` makes in the other direction.
    """
    from gremlin_python.process.traversal import T

    rows = (
        g.V().has_label("Claim")
        .project("vid", "kind", "description")
        .by(T.id).by("kind").by("description")
        .to_list()
    )
    return [(str(r["vid"]), str(r["kind"]), str(r["description"])) for r in rows]


def edge_property_vocabulary(g) -> dict[str, set[str]]:
    """Which property keys each edge label carries, as one aggregate.

    `audit_declarations` needs the vocabulary and nothing else — roughly fourteen
    strings. Deriving it from rows requires shipping all 161,904 edges with all their
    properties; asking the graph for it directly costs a 230 ms median against the
    10,600 ms that scan costs. The scan is narrowed to the keys rules read by name only
    because this question is answered separately.
    """
    from gremlin_python.process.graph_traversal import __
    from gremlin_python.process.traversal import T

    grouped = g.E().group().by(T.label).by(__.properties().key().dedup().fold()).next()
    return {str(label): {str(key) for key in keys} for label, keys in (grouped or {}).items()}


def _fetch(g) -> tuple[list[AuditVertex], list[AuditEdge]]:
    """Pull the graph into plain rows — only the columns a rule reads.

    Both sides are full scans and cannot be anything else: TinkerGraph's only index is
    an exact-value hash map, none is declared, and `hasLabel` has no index there at all.
    So what is controllable is not how many elements are walked but how much of each one
    crosses the wire, which is what both narrowings below do.

    Measured on the live graph, 47,450 vertices and 161,904 edges, medians:
    the vertex read 5,054 ms as `valueMap(true)` and 2,443 ms as `elementMap` over
    `_AUDIT_VERTEX_KEYS`; the edge read 10,611 ms as `elementMap()` and 6,299 ms as the
    `project` below. Narrowing the edge *properties* alone was measured at 1.1x and
    rejected: most edges carry no properties, so `elementMap`'s cost is the 161,904
    nested maps themselves, not their contents.
    """
    from gremlin_python.process.graph_traversal import __
    from gremlin_python.process.traversal import T

    vertices = []
    # `element_map` returns scalars where `value_map` returned single-element lists.
    for row in g.V().element_map(*_AUDIT_VERTEX_KEYS).to_list():
        properties = {
            str(key): value for key, value in row.items() if key not in (T.id, T.label)
        }
        vertices.append(
            AuditVertex(vid=str(row[T.id]), label=str(row[T.label]), properties=properties)
        )

    # `project` rather than `element_map`: five flat strings beat a nested map carrying
    # two endpoint sub-maps, on the wire and in deserialisation, even though it adds a
    # sub-traversal per clause where `element_map` resolves endpoints natively.
    # `coalesce` supplies "" for an absent property, since `by(values(k))` would drop
    # the whole edge from the result rather than leave the column empty.
    edges = []
    rows = (
        g.E()
        .project("label", "from", "to", "from_label", "to_label", *_AUDIT_EDGE_KEYS)
        .by(T.label)
        .by(__.out_v().id_())
        .by(__.in_v().id_())
        .by(__.out_v().label())
        .by(__.in_v().label())
        .by(__.coalesce(__.values("role"), __.constant("")))
        .by(__.coalesce(__.values("basis"), __.constant("")))
        .by(__.coalesce(__.values("verified"), __.constant("")))
        .to_list()
    )
    for row in rows:
        edges.append(
            AuditEdge(
                label=str(row["label"]),
                from_vid=str(row["from"]),
                from_label=str(row["from_label"]),
                to_vid=str(row["to"]),
                to_label=str(row["to_label"]),
                # An absent property is absent, not "": a rule testing `.get("role") ==
                # "citation"` must not see a value the edge does not carry.
                properties={key: row[key] for key in _AUDIT_EDGE_KEYS if row[key] != ""},
            )
        )
    return vertices, edges
