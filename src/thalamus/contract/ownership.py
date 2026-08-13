"""Paths that belong to one scope, and to no other.

`WriteBoundary` (contract/manifest.py) answers "which paths may scope X not write",
declared per scope. This module answers the inverse — "who owns path P" — and the
inverse is not expressible there. `config/experts/` holds seven manifests and no
`main.yaml`, so the scope a directory boundary most needs to bind has nowhere to
declare it, and writing the owned glob into the other six stores one fact six times.
The rule therefore lives once, here, beside the roster rather than inside it, the
way `ROSTER_CAPABILITY_DEFAULT` does for capability.

**Why this is admissible when a path allow-list was refused.** The 2026-08-11 ruling
(`docs/index.md`, ticket `1ed468b61248497e`) held an allow-list incoherent inside a
guard that fails open, and that ruling stands for the global case. It does not reach
this one, and the discriminator is *does the rule change the default over its own
complement?* A global allow-list does: everything unenumerated becomes denied, over a
namespace nobody here owns. An ownership row does not. It is a deny with an owner
exception, its complement is untouched, and its own failure mode is *permit* — which
is the status quo. It cannot be worse than what ships without it. Settled in
`073d451b006e4a81`.

**No pydantic, and that is load-bearing rather than stylistic.** This module is
imported by `role-guard.sh` on every `Edit`/`Write` in every session on the box,
including unpinned ones that reach no manifest. Measured on this machine: bare
interpreter 15 ms, this module ~15 ms, a `dataclasses` version 30 ms, and importing
`contract.manifest` **151 ms** — of which the YAML read is only 24 ms, so the cost
that the guard's `main` short-circuit was written to avoid is the pydantic import
itself, not the manifest load. A typed table here would make the ownership test more
expensive than the check it is ordered ahead of. Rows are plain tuples for that
reason; `contract.manifest` re-exports a typed view for callers already paying the
import.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

# (glob, owner, reason). fnmatch over the ABSOLUTE POSIX path, matching
# `WriteBoundary.denies` so the contract has one matching semantics rather than two —
# `*` crosses `/`, and an absolute match survives `thalamus spawn --dir` into another
# checkout where nothing repo-relative would resolve.
#
# Keep this table short. Every row is a path main cannot write, and main is the scope
# that writes this repository.
PATH_OWNERSHIP: tuple[tuple[str, str, str], ...] = (
    (
        "*/tests/qe/*",
        "qe",
        "The oracle is not edited by the party it indicts. `qe` holds the adversarial "
        "suite and its triage file; the scope whose implementation those cases assert "
        "against does not get to adjust what they assert. This is the mirror of qe's "
        "own `*/src/*` deny, and until both directions hold there is no partition — "
        "only a scope that cannot fix its own findings.",
    ),
)


def _normalise(file_path: str) -> str:
    return PurePosixPath(Path(file_path).as_posix()).as_posix()


def owner_of(file_path: str) -> tuple[str, str, str] | None:
    """The ownership row claiming this path, or None if no row does."""
    if not file_path:
        return None
    target = _normalise(file_path)
    for row in PATH_OWNERSHIP:
        if fnmatch(target, row[0]):
            return row
    return None


def denies(scope: str, file_path: str) -> tuple[str, str, str] | None:
    """The row blocking `scope` from writing `file_path`, or None.

    An unowned path is never blocked here, and the owner is never blocked from its
    own path. Every other scope is — `main` included, which is the whole point and
    the one thing `WriteBoundary` cannot express.
    """
    row = owner_of(file_path)
    if row is None or row[1] == scope:
        return None
    return row


def fallback_markers() -> tuple[str, ...]:
    """Literal substrings for the guard's degraded path, one per row.

    `role-guard.sh` searches the raw payload for these when it cannot parse a target
    out of the hook input — the `write-guard.sh` degradation, applied to this rule:
    when the structured read fails the raw payload is searched instead, so the rule
    fails CLOSED even though the guard around it fails open. The guard cannot call
    this function in that state (it is the Python that is unavailable), so the same
    literals are inlined there and `test_ownership.py` asserts the two agree. The
    duplication is real and is checked rather than denied.
    """
    return tuple(row[0].strip("*") for row in PATH_OWNERSHIP)
