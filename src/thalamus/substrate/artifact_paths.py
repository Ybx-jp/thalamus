"""Project an `Artifact`'s raw identifier onto `(repo, path)` — without re-keying it.

`Artifact` is global so two experts touching one file land on one vertex; it is the join
key between scopes (docs/index). Raw tool-call strings do not deliver that: the same
file arrives absolute from one call, repo-relative from the next, and via a worktree
from a third, and `artifact_audit.py` measures the damage.

**The identifier is not re-keyed, and that is a constraint rather than a preference.**
It drives `vid("Artifact", identifier)` in `writer._upsert_artifacts`, so changing it
breaks every citation ever minted; it is a tier-1 observation — the raw string the tool
call actually carried — and deriving over it turns an observation into an inference
(docs/09); and it cannot be undone if the anchoring rule is wrong. So `repo` and `path`
land beside the identifier as derived properties. The 620 duplicate spellings then group
correctly and their stranded touch edges come back with no vertex ID moving, and
`README.md` claimed by five projects becomes five `(repo, path)` groups — which is
correct, and turns the audit's collision count into a queryable fact rather than a
defect. A hard merge stays available later, as a choice rather than a prerequisite.

**Resolution is a registry, not a scalar.** Cutting a path against *one* project name is
what splits identities: with `project="ybx"`, `/home/ybx/code/thalamus/docs/x.md` cuts
at `/ybx/` while the same file's relative spelling cuts nowhere, yielding two identities
for one file. Longest-prefix match against every known checkout root is order-independent
and gets the nesting right — a vendored subrepo wins over its parent because its root is
longer.

**Only proven roots enter the registry.** A root is admitted from a `Session` whose
`project_evidence` says the value was reached by evidence (`cwd` or `touch`), never from
one carrying an unexplained project. This is the consumer side of that field: rather
than a rule that rejects values which do not look like repo names, the anchor simply
declines to rest on anything unproven. Nothing goes red, and the guarantee lands where
the damage would occur.

**"Belongs to no repo" is an outcome, not a failure.** Scratchpads under
`/tmp/claude-*/`, `~/.claude/skills/...`, `/usr/local/bin/...` and the service names
among the identifiers are not repo files. 327 artifacts are in this state, and a rule
without an explicit empty outcome invents 327 phantom repo-relative paths for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import P, T

from thalamus.substrate.schema import ProjectEvidence

# The evidence kinds an anchor may rest on. Absent evidence means unknown, never proven,
# so it is not a member — see `schema.ProjectEvidence`.
PROVEN = frozenset({ProjectEvidence.CWD.value, ProjectEvidence.TOUCH.value})

# How a Claim or Thread reaches the Session that produced it. Those are the vertices
# that name files relatively, so this is the edge set the anchoring actually travels.
_CLAIM_AND_THREAD_OWNERS = ("CONTAINS", "SPAWNS", "CONTINUES", "RESOLVES")


@dataclass
class Projection:
    """One artifact's derived `(repo, path)`, and whether anything was resolved."""

    vid: str
    identifier: str
    repo: str = ""
    path: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.repo)


@dataclass
class ProjectionPlan:
    projections: list[Projection] = field(default_factory=list)
    registry: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Totals that partition the artifacts rather than overlapping them.

        Absolute and relative are counted separately on both sides of resolved: a
        relative identifier can now be anchored through the session behind whatever
        claimed it, so "resolved" and "relative" are no longer disjoint and subtracting
        one from the other reports a negative population.
        """
        absolute = [p for p in self.projections if p.identifier.startswith("/")]
        relative = [p for p in self.projections if not p.identifier.startswith("/")]
        return {
            "artifacts": len(self.projections),
            "anchored by path": sum(1 for p in absolute if p.resolved),
            "anchored by its session": sum(1 for p in relative if p.resolved),
            "absolute, in no known checkout": sum(1 for p in absolute if not p.resolved),
            "relative, no single owner": sum(1 for p in relative if not p.resolved),
        }

    def groups(self) -> dict[tuple[str, str], list[str]]:
        """`(repo, path)` -> the identifiers that project onto it.

        A group with more than one member is the same file under more than one spelling
        — the fragmentation, made addressable without moving a vertex.
        """
        grouped: dict[tuple[str, str], list[str]] = {}
        for projection in self.projections:
            if projection.resolved:
                grouped.setdefault((projection.repo, projection.path), []).append(
                    projection.identifier
                )
        return grouped


def checkout_registry(g: GraphTraversalSource) -> list[str]:
    """Every checkout root the graph can prove, longest first.

    Longest first is what makes `relativize` order-independent: the first member that
    matches is the deepest one, so a vendored subrepo claims its own files rather than
    losing them to the parent checkout that also contains them.
    """
    roots = (
        g.V().has_label("Session").has("repo_root")
        .project("root", "evidence").by("repo_root")
        .by(__.coalesce(__.values("project_evidence"), __.constant("")))
        .to_list()
    )
    proven = {
        str(row["root"]).rstrip("/")
        for row in roots
        if str(row["root"]) and str(row["evidence"]) in PROVEN
    }
    return sorted(proven, key=len, reverse=True)


def relativize(identifier: str, registry: list[str]) -> tuple[str, str]:
    """`(repo, repo-relative path)` for an absolute identifier, or `("", "")`."""
    if not identifier.startswith("/"):
        return "", ""
    candidate = PurePosixPath(identifier)
    for root in registry:
        if candidate == PurePosixPath(root):
            continue
        if candidate.is_relative_to(root):
            return PurePosixPath(root).name, str(candidate.relative_to(root))
    return "", ""


def anchor_from_touches(roots) -> str:
    """The one proven checkout every session that touched this artifact worked in.

    A relative identifier carries no anchor of its own, and this is where it gets one.
    It is also the half that does the work: the fragmentation being repaired is an
    absolute spelling and a relative spelling of the *same file*, so resolving only the
    absolute one leaves every pair as far apart as it started — the derived properties
    would be tidy and group nothing.

    Unanimity again, and for the same reason as the session-level rule: an artifact
    touched from two checkouts has no single answer, and inventing one here would
    fabricate exactly the false merge that re-keying the identifier was rejected for.
    """
    distinct = {str(root).rstrip("/") for root in roots if str(root)}
    return PurePosixPath(distinct.pop()).name if len(distinct) == 1 else ""


def plan(g: GraphTraversalSource) -> ProjectionPlan:
    """What `(repo, path)` every artifact would carry. Reads only."""
    registry = checkout_registry(g)
    rows = (
        g.V().has_label("Artifact")
        .project("vid", "identifier", "roots").by(T.id).by("identifier")
        # Whatever touched this artifact, resolved back to the session behind it. A
        # Session names files the way tool calls do — usually absolutely — while Claims
        # and Threads name them the way a model writes them, which is relative. So the
        # spellings that most need an anchor are precisely the ones no Session points
        # at: 3,808 of the relative identifiers are reached from a Claim and 7 from a
        # Session. Stopping at the direct toucher anchors almost none of them.
        .by(__.in_("TOUCHES")
              .union(__.has_label("Session"),
                     __.in_(*_CLAIM_AND_THREAD_OWNERS).has_label("Session"))
              .has("project_evidence", P.within(sorted(PROVEN)))
              .values("repo_root").dedup().fold())
        .to_list()
    )
    result = ProjectionPlan(registry=registry)
    for row in rows:
        identifier = str(row["identifier"])
        repo, path = relativize(identifier, registry)
        if not repo and not identifier.startswith("/"):
            # A relative spelling, anchored by the sessions that touched it. The path is
            # already repo-relative — that is what makes it the same key its absolute
            # twin resolves to, which is the whole point of the projection.
            repo, path = anchor_from_touches(row["roots"]), identifier
            if not repo:
                path = ""
        result.projections.append(Projection(str(row["vid"]), identifier, repo, path))
    return result


def apply(g: GraphTraversalSource, projection_plan: ProjectionPlan) -> int:
    """Write `repo` and `path` beside each identifier. Returns how many resolved.

    Every artifact is written, including the unresolved ones: an explicitly empty `repo`
    is the belongs-to-no-repo outcome, and leaving the property off would make "not a
    repo file" indistinguishable from "not yet processed".
    """
    for projection in projection_plan.projections:
        (g.V(projection.vid)
          .property("repo", projection.repo)
          .property("path", projection.path)
          .iterate())
    return sum(1 for p in projection_plan.projections if p.resolved)
