"""Remove the graph records of architecture scans, which memory no longer keeps.

`thalamus arch` measures structure into `arch/model.yaml` and writes nothing to the
graph. Scans taken before that landed one Source per run and one Claim per finding, and
those records outlive the commits they were true of — which is the reason the write path
retired, and the reason leaving them is not neutral. A structural finding that survives
its commit is a false memory served with a citation.

Two vocabulary strings appear here and nowhere else in the codebase: the Source kind
`scan` and the provenance source `agent:arch-scanner`. They name values that are still
in the *data*, and nothing else can select the vertices to remove.

**An Artifact is never removed for having been touched only by a scan.** Artifacts are
global and shared, so the module a finding pointed at is very often the same vertex a
session touched. Only an Artifact left with no incident edge at all goes, because that
one is unreachable by construction and `contract check`'s orphan audit would report it
forever. Anything with a surviving neighbour is reported and kept — a migration that
prints only its deletions cannot be checked for having been too eager.

**Retained bytes are reported, never deleted.** Dropping a Source leaves its archived
blob uncited, which is a category `thalamus arch growth` already measures and ranks by
size. Unlinking evidence quietly is the one thing the archive's scan-and-report posture
does not do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource
from gremlin_python.process.traversal import T

# Retired vocabulary, still present in stored data. See the module docstring.
RETIRED_SOURCE_KIND = "scan"
RETIRED_SCANNER = "agent:arch-scanner"


@dataclass(frozen=True)
class Doomed:
    """One vertex the plan will remove, and enough of it to recognise in a dry run."""

    vid: str
    label: str
    detail: str


@dataclass
class RetirementPlan:
    sources: list[Doomed] = field(default_factory=list)
    claims: list[Doomed] = field(default_factory=list)
    artifacts: list[Doomed] = field(default_factory=list)
    # (identifier, surviving neighbours) — kept, and said out loud.
    kept_artifacts: list[tuple[str, int]] = field(default_factory=list)
    # Archive URIs that no Source will cite once this runs. Reported, not touched.
    uncited_blobs: list[str] = field(default_factory=list)

    def doomed_vids(self) -> list[str]:
        return [d.vid for d in (*self.claims, *self.sources, *self.artifacts)]

    def total(self) -> int:
        return len(self.doomed_vids())


def decide(
    *,
    sources: list[dict],
    claims: list[dict],
    artifacts: list[dict],
) -> RetirementPlan:
    """Work out what goes, given rows already read. Pure, and the part worth testing.

    `artifacts` rows carry a `neighbours` list of adjacent vertex ids. An Artifact
    survives on one neighbour that is not itself being removed — the asymmetry is
    deliberate, because keeping a vertex that could have gone costs an orphan report
    while removing one that should have stayed costs a file's identity.
    """
    plan = RetirementPlan()
    doomed: set[str] = {str(row["vid"]) for row in sources}
    doomed |= {str(row["vid"]) for row in claims}

    for row in sources:
        plan.sources.append(
            Doomed(vid=str(row["vid"]), label="Source", detail=str(row.get("origin", "")))
        )
        uri = str(row.get("uri", ""))
        if uri:
            plan.uncited_blobs.append(uri)

    for row in claims:
        plan.claims.append(
            Doomed(
                vid=str(row["vid"]),
                label="Claim",
                detail=str(row.get("description", ""))[:100],
            )
        )

    for row in artifacts:
        survivors = [n for n in row.get("neighbours", ()) if str(n) not in doomed]
        identifier = str(row.get("identifier", row["vid"]))
        if survivors:
            plan.kept_artifacts.append((identifier, len(survivors)))
        else:
            plan.artifacts.append(
                Doomed(vid=str(row["vid"]), label="Artifact", detail=identifier)
            )

    plan.kept_artifacts.sort()
    plan.uncited_blobs.sort()
    return plan


def plan(g: GraphTraversalSource) -> RetirementPlan:
    """Read what a scan left behind and decide what goes."""
    source_rows = [
        {
            "vid": row.get(T.id),
            "origin": row.get("origin", ""),
            "uri": row.get("uri", ""),
        }
        for row in (
            g.V()
            .has_label("Source")
            .has("kind", RETIRED_SOURCE_KIND)
            .element_map()
            .to_list()
        )
    ]
    source_vids = [str(row["vid"]) for row in source_rows]

    # Both selectors, unioned: provenance names the scanner, and derivation points at a
    # scan Source. Either alone would miss a record the other's writer got to first.
    claim_rows: dict[str, dict] = {}
    for row in (
        g.V().has_label("Claim").has("source", RETIRED_SCANNER).element_map().to_list()
    ):
        claim_rows[str(row.get(T.id))] = {
            "vid": row.get(T.id),
            "description": row.get("description", ""),
        }
    if source_vids:
        for row in (
            g.V(*source_vids)
            .in_("DERIVED_FROM")
            .has_label("Claim")
            .dedup()
            .element_map()
            .to_list()
        ):
            claim_rows.setdefault(
                str(row.get(T.id)),
                {"vid": row.get(T.id), "description": row.get("description", "")},
            )

    artifact_rows: list[dict] = []
    if claim_rows:
        for row in (
            g.V(*claim_rows.keys())
            .out("TOUCHES")
            .has_label("Artifact")
            .dedup()
            .element_map()
            .to_list()
        ):
            artifact_vid = str(row.get(T.id))
            artifact_rows.append(
                {
                    "vid": artifact_vid,
                    "identifier": row.get("identifier", ""),
                    "neighbours": [
                        str(other) for other in g.V(artifact_vid).both().id_().to_list()
                    ],
                }
            )

    return decide(
        sources=source_rows, claims=list(claim_rows.values()), artifacts=artifact_rows
    )


def retire(g: GraphTraversalSource, retirement: RetirementPlan) -> int:
    """Drop the planned vertices. Incident edges go with them.

    Returns how many vertices were removed. Idempotent: a second run plans nothing,
    because the selectors find nothing left to select.
    """
    doomed = retirement.doomed_vids()
    if not doomed:
        return 0
    g.V(*doomed).drop().iterate()
    return len(doomed)
