"""Conformance checks a subgraph must pass before it may be written.

The federation contract (docs/01) in its current form. Obligations are enforced **at
write time, not filtered at read time** — that stance is inherited from the base memory
system's orphan check and is the posture every obligation here adopts.

Enforced today:
  - connectivity — every node reachable by at least one edge
  - provenance   — every node resolves to a tier, a source, and an ingestion time
  - scope        — declared, and cross-scope edges are legal ones only

Not yet enforced (they need a second scope to be meaningful):
  - manifest validation — declared node/edge types vs. what is actually written
  - projection grants   — what the plane may read from a scope (docs/09 G4)
"""

from __future__ import annotations

from thalamus.contract.ontology import edge_crosses_scope, vid
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
