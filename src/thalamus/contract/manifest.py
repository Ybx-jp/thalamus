"""Expert manifests — the contract surface a federated subgraph publishes.

A manifest declares what a scope is, what its feeds may write, and where its content
may come from. The one-sentence test: a new expert plugs in by conforming
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

    MAST names "Disobey Role Specification" as a distinct failure mode, at 1.5%
    prevalence against 11.8% for disobeying the *task* specification
    (`scope:literature:claim:d675b5b74b2cdd34`). Its ChatDev repair is **not** a
    warrant for preferring a hook to prose, and was read that way here until
    2026-08-15: the +9.4% (`scope:literature:claim:db0928fe2cfd3616`) came from
    "refining role-specific prompts to enforce hierarchy and role adherence," and the
    paper reports the same figure for improving role specifications alone, with the
    same user prompt and model (`scope:literature:claim:88a0a8431c91e57e`). A
    well-stated role is what that study measured working.

    The warrant for this field is first-party instead, and narrower: a `domain`
    paragraph is advisory to the session it binds, and the scope most likely to read
    past it is the one whose charter the boundary contradicts. Measured over 1,132
    subagent tool calls, environment-only scope resolution named the right scope 6.4%
    of the time — a boundary nobody can resolve is not a boundary. This field is
    declared tier-0 beside the rest of the contract and enforced by the `role-guard`
    PreToolUse hook, as defence in depth over the `domain` statement, never instead
    of it. A scope whose defining property is a *grant* rather than a deny has no
    field here at all and states it in `domain` (`frontend`).

    Patterns match the **absolute** POSIX path of the file being written, via
    `fnmatch`, so `*` crosses `/`: `*.py` denies every Python file anywhere, and
    `*/src/*` denies any conventionally-laid-out source tree. Matching the absolute
    path is what lets the boundary survive `thalamus spawn --dir` into another
    repository, where nothing repo-relative would resolve.

    The under-enforcement is named rather than closed: a repository that does not
    put implementation under `src/` escapes a `*/src/*` deny. The guard is
    defence-in-depth over a boundary the operator also states in `domain`, and the
    standing trade applies — a false positive teaches route-around, which
    costs more than a miss.

    `allow_globs` is the narrow instrument for the one case a deny list reads wrongly:
    a scope whose *artifact* is source code, where the file constitutes the deliverable
    rather than implementing it. The alternative is to drop the extension from
    `deny_globs`, which buys that one tree by unbinding the boundary everywhere — the
    exact failure the boundary exists to prevent. An allow entry names the tree
    instead, so the same extension stays denied outside it.

    Evaluated **before** the denies, because the other order cannot express an
    exception: a deny that already matched has nothing left to exempt it. That makes
    an allow entry strictly widening, so it is written per scope and never defaulted.
    """

    allow_globs: list[str] = Field(
        default_factory=list,
        description=(
            "fnmatch patterns over the absolute POSIX path; a match exempts the "
            "path from deny_globs"
        ),
    )
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
        for pattern in self.allow_globs:
            if fnmatch(target, pattern):
                return None
        for pattern in self.deny_globs:
            if fnmatch(target, pattern):
                return pattern
        return None


class CapabilityBoundary(BaseModel):
    """Tools and named skills a scope's sessions may not invoke.

    The same structural answer as `WriteBoundary`, on the same warrant recorded
    there, applied to capability rather than to path. It instantiates what the
    Agentverse gap analysis names as two High
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

    `allow_tools` inverts that residual, deliberately, for a namespace that is
    first-party and actively growing rather than upstream-owned and stable: an MCP
    server's tool surface. `deny_tools=["mcp__penpot__*"]` denies every tool a
    Penpot MCP server exposes, and `allow_tools` names the specific ones a scope may
    still call — the read/comment surface for `frontend`, architect consultation
    ticket `ca061c54581c4698`. The direction is reversed on purpose: for `Artifact`
    and the design skills, an unrecognised name should fall through permitted
    (the residual above), because that namespace belongs to Anthropic or a skill
    author and a boundary that broke on every upstream rename would teach
    route-around. For a scope's own MCP server, the opposite failure is the
    dangerous one — a tool the *server* adds later (a new `create_*` or `modify_*`)
    must default to blocked for a scope that may only read and comment, not fall
    through to permitted the way an unrecognised skill does. `allow_tools` is
    consulted only once `deny_tools` has already matched, so it narrows a deny; it
    never grants a tool nothing else denies.
    """

    deny_tools: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the tool name; a match blocks the call",
    )
    deny_skills: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the invoked skill's name",
    )
    allow_tools: list[str] = Field(
        default_factory=list,
        description="fnmatch patterns over the tool name; a match un-blocks a call "
        "that deny_tools would otherwise deny. Checked only when deny_tools matches — "
        "it narrows a deny, it does not grant on its own.",
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
        """The pattern that blocks this tool, or None.

        `allow_tools` is checked second and only on a match: it carves permitted
        names back out of a deny pattern, so a scope can be handed the read/comment
        slice of an MCP server's tools while the server's write tools — named and
        unnamed, including ones added after this boundary was written — stay denied
        by default.
        """
        if not tool:
            return None
        pattern = next((p for p in self.deny_tools if fnmatch(tool, p)), None)
        if pattern and any(fnmatch(tool, p) for p in self.allow_tools):
            return None
        return pattern


# One roster-wide decision, stored once. Six identical manifest blocks would be a
# normalization error, and duplicated declarations have drifted in this codebase
# before — `install.py`'s prose parity claim went stale unnoticed, which is why that
# count is now derived rather than stated. Every pinned expert inherits this;
# `designer` opts out in its own manifest; `main` never reaches the guard.
ROSTER_CAPABILITY_DEFAULT = CapabilityBoundary(
    deny_tools=["Artifact", "mcp__penpot__*"],
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
        "the artifact itself matters, open a thread for `designer`. The Penpot MCP "
        "tools are `designer`'s authoring surface for the same reason and are denied "
        "roster-wide for the same charter argument, narrower than the skill/Artifact "
        "denial only in that a scope can carve a slice back out via its own "
        "`allow_tools` — `frontend`'s read/comment grant is the one declared case."
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
        "an operator hand-feeding a file IS the curation decision.",
    )
    write_boundary: WriteBoundary = Field(
        default_factory=WriteBoundary,
        description="Paths this scope's sessions may not edit. Absent means "
        "unbounded — the honest default for a scope whose role is to write code.",
    )
    capability_boundary: CapabilityBoundary | None = Field(
        None,
        description="Tools and skills this scope may not invoke. Absent means "
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
    return base or (Path(override).expanduser() if override else _DEFAULT_CONFIG)


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
