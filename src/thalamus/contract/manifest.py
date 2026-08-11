"""Expert manifests — the contract surface a federated subgraph publishes (docs/01).

A manifest declares what a scope is, what its feeds may write, and where its content
may come from. The one-sentence test from docs/01: a new expert plugs in by conforming
to the contract, with zero bespoke glue — concretely, expert #2 should be a new YAML
file under config/experts/ and nothing else.

The manifest is deliberately an operator-owned file, not a graph node: it is tier-0
configuration (curation decisions), and tier-0 lives outside what any feed or model
can write.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field

# src/thalamus/contract/manifest.py -> parents[3] is the repo root. Local-first
# project; THALAMUS_CONFIG_DIR overrides for anything fancier.
_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config"


class WriteBoundary(BaseModel):
    """Paths a scope's own sessions may not edit — the role boundary made structural.

    A role boundary stated only in `domain` prose is the configuration that was
    measured failing: MAST names "Disobey Role Specification" as a distinct failure
    mode, and the repair that worked in the studied system was structural authority
    rather than a better prompt (`scope:literature:claim:db0928fe2cfd3616`). This
    field is the structure — declared tier-0 beside the rest of the contract,
    enforced by the `role-guard` PreToolUse hook.

    Patterns match the **absolute** POSIX path of the file being written, via
    `fnmatch`, so `*` crosses `/`: `*.py` denies every Python file anywhere, and
    `*/src/*` denies any conventionally-laid-out source tree. Matching the absolute
    path is what lets the boundary survive `thalamus spawn --dir` into another
    repository, where nothing repo-relative would resolve.

    The under-enforcement is named rather than closed: a repository that does not
    put implementation under `src/` escapes a `*/src/*` deny. The guard is
    defence-in-depth over a boundary the operator also states in `domain`, and
    lab/008's standing trade applies — a false positive teaches route-around, which
    costs more than a miss.
    """

    deny_globs: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the absolute POSIX path; a match blocks the write",
    )
    reason: str = Field(
        "", description="Shown to the blocked session — why this scope does not write here"
    )

    def denies(self, file_path: str) -> str | None:
        """The pattern that blocks this path, or None. Empty globs deny nothing."""
        if not file_path:
            return None
        target = PurePosixPath(Path(file_path).as_posix()).as_posix()
        for pattern in self.deny_globs:
            if fnmatch(target, pattern):
                return pattern
        return None


class CapabilityBoundary(BaseModel):
    """Tools and named skills a scope's sessions may not invoke.

    The same structural answer as `WriteBoundary` to the same measured failure
    (`scope:literature:claim:db0928fe2cfd3616`), applied to capability rather than
    to path. It instantiates what the Agentverse gap analysis names as two High
    gaps in agent platforms — no capability permissions (cloud analogue: IAM
    least-privilege) and no policy engine (cloud analogue: org SCPs), arXiv
    2606.20570 — for one roster rather than for a platform.

    **Omission does not mean unbounded, unlike `WriteBoundary`.** The operator's
    decision here was made once for the whole roster, so the default lives in
    `ROSTER_CAPABILITY_DEFAULT` and a manifest that declares nothing inherits it;
    an explicit block overrides it, and an explicit empty block is the opt-out.
    Three states, each with a written meaning — LSP's rule for omitted capability
    properties (`scope:architect:claim:5d76e83a27802b2f`). The defaults differ
    because the spaces do: path-space is infinite and project-specific, so a
    default deny over paths is unwritable, while tool- and skill-space are small
    and enumerable.

    Patterns are fnmatch, matching as `WriteBoundary` does so the contract has one
    matching semantics rather than two. Glob rather than equality because the skill
    namespace is owned upstream: `artifact-*` survives a rename to
    `artifact-design-web`, and `frontend-design*` matches the plugin-prefixed form
    (`frontend-design:frontend-design`) that an exact list would already miss.

    The residual is named rather than closed: a skill this list has never heard of
    is permitted, silently and in the permissive direction, because a boundary that
    is never hit looks identical to one that is respected. Reading a `SKILL.md`
    with `Read` also reaches the procedure without a `Skill` call, and no tool-name
    matcher can see that.
    """

    deny_tools: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the tool name; a match blocks the call",
    )
    deny_skills: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the invoked skill's name",
    )
    reason: str = Field(
        "", description="Shown to the blocked session — why this scope does not invoke this"
    )

    def denies_skill(self, skill: str) -> str | None:
        """The pattern that blocks this skill, or None."""
        if not skill:
            return None
        return next((p for p in self.deny_skills if fnmatch(skill, p)), None)

    def denies_tool(self, tool: str) -> str | None:
        """The pattern that blocks this tool, or None."""
        if not tool:
            return None
        return next((p for p in self.deny_tools if fnmatch(tool, p)), None)


# One roster-wide decision, stored once. Six identical manifest blocks would be a
# normalization error, and duplicated declarations have drifted in this codebase
# before — `install.py`'s prose parity claim went stale unnoticed, which is why that
# count is now derived rather than stated. Every pinned expert inherits this;
# `designer` opts out in its own manifest; `main` never reaches the guard.
ROSTER_CAPABILITY_DEFAULT = CapabilityBoundary(
    deny_tools=["Artifact"],
    deny_skills=[
        "artifact-*",
        "frontend-design*",
        "dataviz",
        "author-repo-diagram",
    ],
    reason=(
        "Design is the `designer` scope's deliverable, and a pinned expert that "
        "spends a design budget trades its own charter for presentation. Hand back "
        "a markdown file and its path, and the operator can read or publish it; if "
        "the artifact itself matters, open a thread for `designer`."
    ),
)


class ExpertManifest(BaseModel):
    contract: str = "v0"
    scope: str
    name: str
    domain: str = ""
    tier: int = Field(2, description="Origin tier of this expert's content sources")
    claim_kinds: list[str] = Field(
        default_factory=list, description="Namespaced kinds this expert's feeds may write"
    )
    allowlist: list[str] = Field(
        default_factory=list,
        description="Host suffixes ingestion may fetch from. Local files bypass this — "
        "an operator hand-feeding a file IS the curation decision (docs/06).",
    )
    write_boundary: WriteBoundary = Field(
        default_factory=WriteBoundary,
        description="Paths this scope's sessions may not edit (docs/08). Absent means "
        "unbounded — the honest default for a scope whose role is to write code.",
    )
    capability_boundary: CapabilityBoundary | None = Field(
        None,
        description="Tools and skills this scope may not invoke (docs/08). Absent means "
        "inherit ROSTER_CAPABILITY_DEFAULT — the opposite of write_boundary's default, "
        "because this decision was made once for the whole roster rather than per scope. "
        "An explicit empty block is the opt-out.",
    )

    @property
    def effective_capability_boundary(self) -> CapabilityBoundary:
        """What actually binds this scope — the declared block, or the roster default.

        Read this rather than the field: the field's `None` is a real third state,
        and a caller that treats it as an empty boundary silently unbinds every
        scope that never declared one, which is all of them but `designer`.
        """
        if self.capability_boundary is not None:
            return self.capability_boundary
        return ROSTER_CAPABILITY_DEFAULT

    def allows(self, origin: str) -> bool:
        """Is this origin inside the allowlist? Non-URL origins are operator-fed."""
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https"):
            return True
        host = (parsed.hostname or "").lower()
        return any(
            host == suffix or host.endswith(f".{suffix}")
            for suffix in (s.lower().lstrip(".") for s in self.allowlist)
        )

    def check_batch(self, batch) -> list[str]:
        """Manifest-level obligations, on top of conformance.check_knowledge."""
        issues: list[str] = []
        if batch.scope != self.scope:
            issues.append(
                f"Batch is for scope `{batch.scope}` but this manifest governs "
                f"`{self.scope}`"
            )
        origin = batch.source.origin or ""
        if origin and not self.allows(origin):
            issues.append(
                f"Origin not allowlisted for `{self.scope}`: {origin} — "
                "curation is the gate; edit the manifest's allowlist if this source "
                "belongs (config/experts/)"
            )
        declared = set(self.claim_kinds)
        if declared:
            for claim in batch.claims:
                if claim.kind not in declared:
                    issues.append(
                        f"Claim kind `{claim.kind}` is not declared by the "
                        f"`{self.scope}` manifest ({', '.join(sorted(declared))})"
                    )
        return issues


def config_root(base: Path | None = None) -> Path:
    """The tier-0 configuration directory — manifests and anything beside them."""
    override = os.environ.get("THALAMUS_CONFIG_DIR")
    return base or (Path(override) if override else _DEFAULT_CONFIG)


def experts_dir(base: Path | None = None) -> Path:
    return config_root(base) / "experts"


def load_manifest(scope: str, base: Path | None = None) -> ExpertManifest:
    path = experts_dir(base) / f"{scope}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(available_scopes(base))) or "(none)"
        raise FileNotFoundError(
            f"No manifest for scope `{scope}` at {path}. Available: {available}"
        )
    manifest = ExpertManifest(**yaml.safe_load(path.read_text()))
    if manifest.scope != scope:
        raise ValueError(f"{path} declares scope `{manifest.scope}`, not `{scope}`")
    return manifest


def available_scopes(base: Path | None = None) -> list[str]:
    directory = experts_dir(base)
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.yaml"))
