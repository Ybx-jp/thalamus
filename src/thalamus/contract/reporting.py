"""The reporting structure: which scope reports to which, as one checked tree.

Each expert manifest names its superior in `reports_to`, `main` when absent. This
module reads every manifest and builds the tree they describe, rooted at `main`.

`main` has no manifest and reports to nothing. Every other scope's chain has to end
at `main`: a superior that names no declared scope, a scope that reports to itself, or
a loop fails the build. There is no limit on depth.

The manifests are the only place this is stored. The tree is rebuilt from them on every
read and never saved anywhere else, so it cannot disagree with them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thalamus.contract.manifest import available_scopes, experts_dir, load_manifest
from thalamus.contract.ontology import MAIN_SCOPE


@dataclass(frozen=True)
class ReportingGraph:
    """Each scope's superior, for every declared scope. `main` is the root and has none."""

    superiors: dict[str, str]

    def superior(self, scope: str) -> str | None:
        """The scope `scope` reports to; None for `main`. Raises KeyError on an unknown scope."""
        if scope == MAIN_SCOPE:
            return None
        return self.superiors[scope]

    def reports(self, scope: str) -> list[str]:
        """The scopes that report directly to `scope`, sorted."""
        return sorted(s for s, up in self.superiors.items() if up == scope)

    def as_dict(self) -> dict:
        """The tree as data, for `thalamus reporting --json`."""
        return {
            "root": MAIN_SCOPE,
            "reports_to": dict(sorted(self.superiors.items())),
            "reports": {
                s: self.reports(s)
                for s in [MAIN_SCOPE, *sorted(self.superiors)]
                if self.reports(s)
            },
        }

    def lines(self) -> list[str]:
        """The tree as indented text, `main` first, each scope under its superior."""
        out: list[str] = []

        def walk(scope: str, depth: int) -> None:
            out.append("  " * depth + scope)
            for child in self.reports(scope):
                walk(child, depth + 1)

        walk(MAIN_SCOPE, 0)
        return out


def build(superiors: dict[str, str], where: dict[str, Path] | None = None) -> ReportingGraph:
    """Check a scope → superior map and return its graph. Raises ValueError naming the scope.

    `where` maps a scope to its manifest's path, so the message says which file to fix.
    """
    where = where or {}

    def named(scope: str) -> str:
        return f"{where[scope]}: " if scope in where else ""

    if MAIN_SCOPE in superiors:
        raise ValueError(f"{named(MAIN_SCOPE)}`{MAIN_SCOPE}` is the root and reports to nothing")
    for scope, up in superiors.items():
        if up == scope:
            raise ValueError(f"{named(scope)}`{scope}` reports to itself")
        if up != MAIN_SCOPE and up not in superiors:
            raise ValueError(
                f"{named(scope)}`{scope}` reports to `{up}`, which is neither "
                f"`{MAIN_SCOPE}` nor a declared scope"
            )
    for scope in superiors:
        seen = [scope]
        up = superiors[scope]
        while up != MAIN_SCOPE:
            if up in seen:
                loop = " → ".join([*seen[seen.index(up):], up])
                raise ValueError(f"{named(scope)}reporting loop: {loop}")
            seen.append(up)
            up = superiors[up]
    return ReportingGraph(superiors=dict(superiors))


def reporting_graph(base: Path | None = None) -> ReportingGraph:
    """The reporting tree the config root's manifests declare, checked."""
    scopes = available_scopes(base)
    superiors = {scope: load_manifest(scope, base).reports_to for scope in scopes}
    where = {scope: experts_dir(base) / f"{scope}.yaml" for scope in scopes}
    return build(superiors, where)
