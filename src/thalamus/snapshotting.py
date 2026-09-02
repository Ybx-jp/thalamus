"""Naming an artifact by its content, so a published number can cite what produced it.

A measurement is only reproducible if the things it was measured against can be named
and re-checked. Thalamus already does this for one artifact — a named graph snapshot
— and the vocabulary that makes it work is not specific to graphs: a name that is
restricted rather than sanitised, a digest taken when it is made, a registry that refuses
to overwrite a name, and a verification that asks whether the bytes still are what the
registry said.

This module is that vocabulary. It owns no artifact kind of its own. Each kind keeps
its own row shape, because the fields worth recording differ — a graph snapshot has
vertex and edge counts, a VM image has neither and a build's own provenance instead —
and collapsing them into one table would make every kind carry the others' columns.
What they share is how a name is checked, how a duplicate is refused, and what a
digest mismatch means.

Taking the digest is the kind's own business, because only the kind knows where its
artifact lives — a graph snapshot is hashed inside the container that holds it, a VM
image on the host that built it. What is shared is that `sha256` and `byte_size` mean
the same two things in every row.

WHAT A DIGEST PROVES, AND WHAT IT DOES NOT. That two artifacts are the same bytes.
Not that either can be rebuilt: an artifact assembled from a package index or a
network fetch is not bit-reproducible without deliberate discipline about timestamps
and mirror state. A registry row pins the artifact that was made. A run record that
cites one should say that, rather than letting "sha256" imply the stronger claim.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

#: A snapshot name is part of a filename and of a published citation, so it is restricted
#: rather than sanitised — a name that needs escaping is a name that will be quoted
#: wrong somewhere.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

Row = TypeVar("Row")


class SnapshotError(RuntimeError):
    """A snapshot could not be taken, found, or verified."""


def check_name(name: str, *, noun: str = "snapshot") -> None:
    """Refuse a name that cannot be safely used as a filename or a citation.

    `noun` names the artifact kind in the message. A generic vocabulary that told
    the operator their "snapshot name" was invalid when they asked about a VM image would
    make them translate; each kind says its own word.
    """
    if not NAME_RE.match(name or ""):
        raise SnapshotError(
            f"invalid {noun} name `{name}` — lowercase letters, digits and hyphens, 3-64 chars"
        )


def now() -> str:
    """The time a snapshot was taken, UTC and ISO-8601. One spelling, so rows sort as text."""
    return datetime.now(timezone.utc).isoformat()


def check_digest(name: str, actual: str, recorded: str, *, noun: str = "snapshot",
                 consequence: str = "it is not the artifact that was cited") -> None:
    """Refuse unless the artifact still hashes to what its row says it did.

    The failure this exists for is silent: an artifact that changed under a name
    already cited turns every published number citing it into a claim about
    something else. Both digests go in the message, because "it changed" without
    saying to what leaves the reader unable to tell a rebuild from a corruption.

    `consequence` is the caller's half of the sentence — what this mismatch means
    for the operation they were attempting. A refusal that says only that two hashes
    differ makes the reader work out why they should care.
    """
    if actual != recorded:
        raise SnapshotError(
            f"{noun} `{name}` no longer hashes to its registry entry "
            f"({actual[:12]} != {recorded[:12]}) — {consequence}"
        )


def git_ref(start: Path) -> str:
    """The short commit of the checkout an artifact was captured from, or `unknown`.

    Advisory context, never identity — the digest is the identity. A snapshot taken from
    a dirty tree still records the ref it was nearest to, which is more use to a
    reader than nothing and less than they would get from the hash.
    """
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=start, capture_output=True, text=True, check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


class Registry(Generic[Row]):
    """An append-only, name-immutable ledger of pins of one artifact kind.

    Operator state rather than repository state: a snapshot belongs to whoever took it,
    not to the checkout it was taken from, so the file lives outside any repo and
    two checkouts of the same source do not disagree about what has been taken.

    Immutability is the property the whole mechanism rests on. A name that has been
    cited must keep meaning what it meant; re-taking the same artifact under a new name is a new
    name, never a mutation of an old one.
    """

    def __init__(self, path: Path, row_type: Callable[..., Row], *,
                 noun: str = "snapshot", plural: str = "snapshots") -> None:
        self.path = path
        self.row_type = row_type
        self.noun = noun
        self.plural = plural

    def rows(self) -> list[Row]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(self.row_type(**json.loads(line)))
        return out

    def names(self) -> list[str]:
        return [getattr(row, "name") for row in self.rows()]

    def find(self, name: str) -> Row:
        for row in self.rows():
            if getattr(row, "name") == name:
                return row
        known = ", ".join(self.names()) or "none"
        raise SnapshotError(f"unknown {self.noun} `{name}`; registered: {known}")

    def refuse_duplicate(self, name: str) -> None:
        """Called before an artifact is produced, so a clash costs nothing."""
        if name in self.names():
            raise SnapshotError(f"{self.noun} `{name}` already exists; {self.plural} are immutable")

    def append(self, row: Row) -> Row:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(_as_dict(row)) + "\n")
        return row


def _as_dict(row: Any) -> dict:
    try:
        return asdict(row)
    except TypeError:  # not a dataclass; a kind may use any row it can round-trip
        return dict(row)
