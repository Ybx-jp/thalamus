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
