"""The reporting structure: which scope reports to which, as one checked tree.

Each expert manifest names its superior in `reports_to`, `main` when absent. This
module reads every manifest and builds the tree they describe, rooted at `main`.

`main` has no manifest and reports to nothing. Every other scope's chain has to end
at `main`: a superior that names no declared scope, a scope that reports to itself, or
a loop fails the build. There is no limit on depth.

The manifests are the only place this is stored. The tree is rebuilt from them on every
read and never saved anywhere else, so it cannot disagree with them.

A manifest's `rules` travel down the tree. A scope's charter is its own `domain`
followed by the `rules` of every scope above it and its own, top-most first, so a
manager's rules bind its whole group at any depth, and a subordinate can add a rule and
cannot remove one. This is the shape of a service control policy in AWS Organizations:
a policy attached to a unit applies to every account under it, and nothing granted
lower down can exceed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thalamus.contract.manifest import (
    ExpertManifest,
    available_scopes,
    experts_dir,
    load_manifest,
)
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


def inherited_rules(
    manifest: ExpertManifest, base: Path | None = None
) -> list[tuple[str, str]]:
    """Every `rules` text binding this scope, as (origin scope, text), top-most first.

    The chain runs from the scope's superior up to `main` and ends with the scope's own
    `rules`; a scope with no text is skipped. `base` defaults to the config root the
    manifest was loaded from. A scope reporting to `main` reads no other manifest. Any
    other reads the whole tree, checked by `build`, so a loop or an undeclared superior
    anywhere in it is refused here as it is by `thalamus reporting`.
    """
    base = base if base is not None else manifest._base
    chain = [manifest]
    if manifest.reports_to != MAIN_SCOPE:
        graph = reporting_graph(base)
        if manifest.scope not in graph.superiors:
            raise ValueError(
                f"`{manifest.scope}` is not declared under {experts_dir(base)}, so the "
                f"rules above it cannot be read"
            )
        up = graph.superior(manifest.scope)
        while up is not None and up != MAIN_SCOPE:
            chain.append(load_manifest(up, base))
            up = graph.superior(up)
    return [(m.scope, m.rules.strip()) for m in reversed(chain) if m.rules.strip()]


def charter_domain(manifest: ExpertManifest, base: Path | None = None) -> str:
    """The domain a scope's charter states: its own `domain`, then each rule set binding it.

    Every carrier of a charter reads this rather than `domain`: the pinned agent file
    and codex profile, the delegated prompt, and the consultation brief. A rule a
    carrier left out would bind a pinned session and not a delegated one
    (A0261, cites-as-live).
    """
    parts = [manifest.domain.strip()]
    for origin, text in inherited_rules(manifest, base):
        if origin == manifest.scope:
            heading = (
                "Rules binding this scope and every scope that reports to it, "
                "at any depth:"
            )
        else:
            heading = (
                f"Rules binding this scope, from `{origin}`, which it reports to. "
                "Nothing in this charter relaxes them; where they and the charter "
                "differ, the stricter governs:"
            )
        parts.append(f"{heading}\n\n{text}")
    return "\n\n".join(p for p in parts if p)
