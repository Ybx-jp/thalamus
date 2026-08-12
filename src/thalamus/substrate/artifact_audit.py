"""Measure how badly `Artifact` identity is fragmented, and why it cannot be repaired yet.

`Artifact` is global so two experts touching one file land on one vertex — it is the
join key between scopes (docs/index.md, 2026-07-14). The join is leaky, because raw
tool-call strings are not identity: the same file arrives absolute from one call,
repo-relative from the next, and via a worktree from a third.

This module reports the damage over the raw identifiers, which is still the honest place
to measure it: the identifiers are what the tool calls carried, and they are never
re-keyed. The join is repaired *beside* them by the `(repo, path)` projection
(`substrate/artifact_paths.py`), anchored on `Session.repo_root` and admitted only from
sessions whose `project_evidence` proves it — so the numbers here are the fragmentation
that projection has to reach, not a backlog waiting on a decision.

Read the two together. A split pair that shares a `(repo, path)` is joined and its
stranded touches are reachable; one that does not is a file the registry cannot anchor,
and that is the residue worth looking at.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import T


TOUCH_EDGE = "TOUCHES"


@dataclass
class ArtifactAudit:
    """What the graph's artifact identity looks like, measured rather than asserted."""

    total: int = 0
    # A file named by an absolute path that some other vertex already names relatively.
    # These are the unambiguous duplicates: same file, two vertices, no judgement call.
    split_pairs: list[tuple[str, str, int]] = field(default_factory=list)
    # Relative paths that more than one project claims. Repo furniture, mostly.
    collisions: dict[str, set[str]] = field(default_factory=dict)
    # Distinct project values, with how many artifacts carry each. Printed in full
    # because the audit's own reliability depends on these being real repo names, and
    # a reader can tell at a glance that `tmp` and `code` are not.
    projects: dict[str, int] = field(default_factory=dict)

    @property
    def stranded_touches(self) -> int:
        return sum(touches for _, _, touches in self.split_pairs)


def _artifact_rows(g: GraphTraversalSource) -> list[dict]:
    return (
        g.V()
        .has_label("Artifact")
        .project("identifier", "project", "touches")
        .by("identifier")
        .by(__.coalesce(__.values("project"), __.constant("")))
        .by(__.in_e(TOUCH_EDGE).count())
        .to_list()
    )


def audit_artifact_identity(g: GraphTraversalSource) -> ArtifactAudit:
    """Report identity fragmentation without depending on `project` being trustworthy.

    The split count is derived by suffix matching — an absolute path is a duplicate of a
    relative one when the relative one is a path-boundary suffix of it. That test needs
    no anchor and no project name, so it holds even for the sessions whose `project` is
    junk, which is exactly why it is the number worth quoting.
    """
    audit = ArtifactAudit()
    rows = _artifact_rows(g)
    audit.total = len(rows)

    relative = {row["identifier"]: row for row in rows if not row["identifier"].startswith("/")}
    claims: dict[str, set[str]] = defaultdict(set)
    projects: dict[str, int] = defaultdict(int)

    for row in rows:
        projects[row["project"] or "<none>"] += 1
        if row["project"] and not row["identifier"].startswith("/"):
            claims[row["identifier"]].add(row["project"])

    for row in rows:
        identifier = row["identifier"]
        if not identifier.startswith("/"):
            continue
        # Longest relative identifier that this absolute path ends with, on a path
        # boundary — `.../src/cli.py` matches `src/cli.py` but never `i.py`.
        match = max(
            (
                candidate
                for candidate in relative
                if identifier.endswith("/" + candidate)
            ),
            key=len,
            default="",
        )
        if match:
            audit.split_pairs.append((identifier, match, row["touches"]))
            # Resolve the absolute spelling onto the relative path it duplicates before
            # counting owners — otherwise a file whose second repo only ever names it
            # absolutely looks uncontested.
            if row["project"]:
                claims[match].add(row["project"])

    audit.collisions = {
        path: owners for path, owners in claims.items() if len(owners) > 1
    }
    audit.projects = dict(sorted(projects.items(), key=lambda item: -item[1]))
    return audit
