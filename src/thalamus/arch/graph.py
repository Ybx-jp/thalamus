"""Turn a scan into the things the graph keeps: one Source, and the findings only.

Three rules govern what crosses from a scan into memory, and all three exist to stop the
instrument from drowning the scope it is supposed to sharpen:

**Findings, never metrics.** Propagation cost is not a claim; it is a reading that a
future scan will replace. It stays in the retained model file, which is a Source anyone
can re-read at the commit it names. What lands as a Claim is a *finding* — a cycle, a
violated rule, a module the declared partition does not place — because those are
assertions someone can act on or refute.

**New or changed only, and identity does the enforcing.** A Claim's identity is the hash
of its kind and description, so a finding that persists lands on the same vertex every
scan and a changed one lands on a new vertex by construction — which is what "new or
changed" means once claims are content-addressed. The scope therefore grows by findings,
not by runs (lab/006-007). What each scan does add is one `DERIVED_FROM` edge per
finding, so a recurring problem accumulates evidence instead of duplicates, and `unseen`
reports which findings are genuinely new rather than gating the write.

**Attribution rides the provenance envelope, not a new edge.** The design named an Agent
called `arch-scanner` and left the mechanism for a round it never got: the ontology
declares no Agent->Claim or Agent->Source edge, and inventing one is a federation
contract change, not an implementation detail. So the scanner names itself in
`Provenance.source`, which already carries exactly this vocabulary
(`operator | session:<id> | feed:<name>`), and the Agent vertex waits for the round that
settles it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from gremlin_python.process.graph_traversal import GraphTraversalSource

from thalamus.arch.extractor import DependencyGraph
from thalamus.arch.metrics import Metrics
from thalamus.arch.model import ArchModel
from thalamus.contract.ontology import vid
from thalamus.substrate.schema import Problem, ProblemCategory, Provenance, Tier

ARCH_SCOPE = "architect"

# The scanner names itself here, in the vocabulary `Provenance.source` already uses.
SCANNER = "agent:arch-scanner"


@dataclass
class ScanPayload:
    """Everything one scan writes. Assembled here so the substrate imports nothing."""

    scope: str
    repo: str
    origin: str
    lineage: str
    title: str
    uri: str
    content_hash: str
    byte_size: int
    provenance: Provenance
    findings: list[Problem] = field(default_factory=list)


def findings(graph: DependencyGraph, metrics: Metrics, model: ArchModel) -> list[Problem]:
    """What this scan asserts. Empty is the healthy outcome, not a failed run.

    **No description names its scan.** A claim's identity is the hash of its kind and
    description, so folding the scan id into the sentence would mint a fresh vertex for
    the same unchanged cycle on every run — forty claims a run, which is precisely the
    unrecallable scope the design forbids. The commit anchor lives where it belongs: on
    the `DERIVED_FROM` edge to that scan's Source. A finding observed by six scans is
    one claim with six edges, and "this keeps coming up" is then a graph fact rather
    than six near-duplicate sentences.
    """
    provenance = Provenance(tier=Tier.FIRST_PARTY, source=SCANNER, derived_from=[])
    found: list[Problem] = []

    for cycle in metrics.cycles:
        found.append(
            Problem(
                description=(
                    f"Import cycle among {len(cycle)} modules: {', '.join(cycle)}."
                ),
                category=ProblemCategory.DESIGN,
                artifacts=list(cycle),
                provenance=provenance,
            )
        )

    for violation in model.violations(graph):
        found.append(
            Problem(
                description=f"Dependency rule violated: {violation.describe()}.",
                category=ProblemCategory.DESIGN,
                artifacts=[violation.from_path, violation.to_path],
                provenance=provenance,
            )
        )

    unplaced = model.unplaced(graph) if model.layers else []
    if unplaced:
        found.append(
            Problem(
                description=(
                    f"The declared layer partition does not place {len(unplaced)} of "
                    f"{len(graph.modules)} scanned modules."
                ),
                category=ProblemCategory.DESIGN,
                artifacts=sorted(unplaced)[:20],
                provenance=provenance,
            )
        )

    for note in graph.unresolved:
        found.append(
            Problem(
                description=f"Scanner could not read a module: {note}.",
                category=ProblemCategory.UNDERSTANDING,
                artifacts=[note.split(":")[0]],
                provenance=provenance,
            )
        )

    for note in model.stale_authored_paths():
        found.append(
            Problem(
                description=f"Authored model has rotted: {note}.",
                category=ProblemCategory.DESIGN,
                artifacts=[],
                provenance=provenance,
            )
        )
    return found


def unseen(g: GraphTraversalSource, scope: str, candidates: list[Problem]) -> list[Problem]:
    """The findings the graph does not already hold, by claim identity.

    A read failure returns everything rather than nothing: writing a claim that is
    already there is a no-op merge, while skipping one because a query failed loses a
    finding silently. Cheap error in the direction of the redundant write.
    """
    if not candidates:
        return []
    wanted = {vid("Claim", finding.content_id(), scope): finding for finding in candidates}
    try:
        present = {str(found) for found in g.V(*wanted.keys()).id_().to_list()}
    except Exception:
        return candidates
    return [finding for held, finding in wanted.items() if held not in present]


def payload(
    *,
    repo: str,
    origin: str,
    lineage: str,
    commit: str,
    content_hash: str,
    uri: str,
    byte_size: int,
    found: list[Problem],
    scope: str = ARCH_SCOPE,
) -> ScanPayload:
    """Assemble the write. Tier 1: a first-party mechanical observation of own code."""
    return ScanPayload(
        scope=scope,
        repo=repo,
        origin=origin,
        lineage=lineage,
        title=f"Architecture scan — {repo} @ {commit[:7]}",
        uri=uri,
        content_hash=content_hash,
        byte_size=byte_size,
        provenance=Provenance(
            tier=Tier.FIRST_PARTY,
            source=SCANNER,
            ingested_at=datetime.now(timezone.utc),
        ),
        findings=found,
    )


def citation(fact: str, scan: str, commit: str, policy_line: str, superseded_by: str = "") -> str:
    """Render a structural fact the way recall must serve it.

    The superseding line is not decoration. A structural number is true of the commit it
    was taken at and false of most others, so a citation that hides its supersession
    reads as current — which is the failure mode the whole scan-id scheme exists to
    prevent. A superseded citation is never silently refreshed; the reader is told.
    """
    lines = [
        f"Structural fact — `{scan}`",
        fact,
        f"Scanned at `{commit[:7]}`; policy {policy_line}.",
    ]
    if superseded_by:
        lines.append(
            f"*Superseded by `{superseded_by}` — this value held at the commit named.*"
        )
    return "\n".join(lines)
