"""Paths that belong to one scope, and to no other.

`WriteBoundary` (contract/manifest.py) answers "which paths may scope X not write",
declared per scope. This module answers the inverse — "who owns path P" — and the
inverse is not expressible there. A config root holds a manifest per expert and no
`main.yaml`, so the scope a directory boundary most needs to bind has nowhere to
declare it, and writing the owned glob into every other manifest stores one fact once
per scope. The rule therefore lives once, in the config root beside the manifests —
`ownership.json` — rather than inside them.

The table is configuration, not code: a row is one repository's decision about one of
its trees. This repository's `config/ownership.json` reserves `tests/qe/` for `qe`; a
config root without the file reserves nothing, which is what an installed wheel starts
with.

**Why this is admissible when a path allow-list was refused.** The 2026-08-11 ruling
(ticket `1ed468b61248497e`) held an allow-list incoherent inside a
guard that fails open, and that ruling stands for the global case. It does not reach
this one, and the discriminator is *does the rule change the default over its own
complement?* A global allow-list does: everything unenumerated becomes denied, over a
namespace nobody here owns. An ownership row does not. It is a deny with an owner
exception, its complement is untouched, and its own failure mode is *permit* — which
is the status quo. It cannot be worse than what ships without it. Settled in
`073d451b006e4a81`.

**Stdlib only, and that is load-bearing rather than stylistic.** This module is
imported by `role-guard.sh` on every `Edit`/`Write` in every session on the box,
including unpinned ones that reach no manifest. Measured on this machine, best of 15
fresh interpreters: bare 13.8 ms, `import json` 18.7 ms, `import yaml` 31.1 ms, and
importing `contract.manifest` 151 ms (its pydantic import, not its YAML read). The table
is JSON for that reason, and because the guard's degraded path reads the same file with
`jq` when Python is the thing that failed.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from thalamus.contract.paths import config_root

#: The table's file name in the config root. An object of row name to
#: `{"glob", "owner", "reason"}`; fnmatch over the ABSOLUTE POSIX path, matching
#: `WriteBoundary.denies` so the contract has one matching semantics rather than two —
#: `*` crosses `/`, and an absolute match survives `thalamus spawn --dir` into another
#: checkout where nothing repo-relative would resolve.
OWNERSHIP_FILE = "ownership.json"


def rows(root: Path | None = None) -> tuple[tuple[str, str, str], ...]:
    """The config root's ownership rows as (glob, owner, reason); none without the file.

    A file that is present and malformed raises, naming itself: a table nobody can read
    is a configuration error to report, not an empty table to act on silently.
    """
    path = (root or config_root()) / OWNERSHIP_FILE
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected an object of row name to row")
    out = []
    for name, row in raw.items():
        fields = [row.get(k) if isinstance(row, dict) else None
                  for k in ("glob", "owner", "reason")]
        if not all(isinstance(f, str) and f.strip() for f in fields):
            raise ValueError(f"{path}: row `{name}` needs a non-empty glob, owner and reason")
        out.append((fields[0], fields[1], fields[2]))
    return tuple(out)


def _normalise(file_path: str) -> str:
    return PurePosixPath(Path(file_path).as_posix()).as_posix()


def owner_of(file_path: str, root: Path | None = None) -> tuple[str, str, str] | None:
    """The ownership row claiming this path, or None if no row does."""
    if not file_path:
        return None
    target = _normalise(file_path)
    for row in rows(root):
        if fnmatch(target, row[0]):
            return row
    return None


def denies(scope: str, file_path: str,
           root: Path | None = None) -> tuple[str, str, str] | None:
    """The row blocking `scope` from writing `file_path`, or None.

    An unowned path is never blocked here, and the owner is never blocked from its
    own path. Every other scope is — `main` included, which is the whole point and
    the one thing `WriteBoundary` cannot express.
    """
    row = owner_of(file_path, root)
    if row is None or row[1] == scope:
        return None
    return row
