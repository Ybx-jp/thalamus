"""Conformance checks a subgraph must pass before it may be written.

This is the seed of the federation contract (docs/01-federation-contract.md). Today
it enforces exactly one invariant, inherited from the base memory system: **every
node must be reachable by at least one edge.** Orphans are rejected at write time,
not filtered at read time — which is the enforcement posture the contract doc
specifies for every obligation it will grow.

The obligations that do not exist yet, and where they will land:

- provenance (`tier`, `source`, `ingested_at`) — docs/05-trust-model.md
- scope (`expert_id`) and cross-scope edge legality — docs/01, docs/02
- manifest validation (declared node/edge types vs. what is actually written)
- projection grants (what the plane may read from a scope)

Keeping them in one module is the point: the contract is meant to be a single
artifact, not a set of checks scattered across writers and readers.
"""

from __future__ import annotations

from thalamus.substrate.schema import SessionGraph


def referenced_artifacts(session: SessionGraph) -> set[str]:
    """Artifact identifiers that at least one node in the session points at."""
    referenced: set[str] = set()
    for decision in session.decisions:
        referenced.update(decision.artifacts)
    for problem in session.problems:
        referenced.update(problem.artifacts)
    for solution in session.solutions:
        referenced.update(solution.artifacts)
    for thread in session.threads:
        referenced.update(thread.artifacts)
    return referenced


def validate_connectivity(session: SessionGraph) -> list[str]:
    """Check that all nodes have at least one edge. Returns a list of issues."""
    referenced = referenced_artifacts(session)
    return [
        f"Orphan artifact: '{artifact.identifier}' has no edges — "
        "add it to a decision/problem/solution/thread artifacts list or remove it"
        for artifact in session.artifacts
        if artifact.identifier not in referenced
    ]


def prune_orphan_artifacts(session: SessionGraph) -> SessionGraph:
    """Return a copy of the session with unreachable artifacts removed."""
    referenced = referenced_artifacts(session)
    pruned = [a for a in session.artifacts if a.identifier in referenced]
    if len(pruned) == len(session.artifacts):
        return session
    return session.model_copy(update={"artifacts": pruned})
