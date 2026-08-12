"""Re-anchor `project` values that named a directory instead of a repo.

`project` was the basename of a session's working directory
(`harness/transcripts.py`, fixed forward 2026-08-12), so any session that ran from
somewhere that was not a checkout filed its memory under that directory's name. The
graph carries the result: `ybx`, `tmp`, `code`, a 64-char content hash, five
`thalamus-extract-*` sandboxes, `Avatar - The Last Airbender - Season 2`,
`test_settings_load`, and `resumes` — which is a *subdirectory* of the
`resume-workbench` checkout and therefore wrong in the other direction.

The forward fix does not touch any of them, and they matter because `project` is the
anchor a repo-relative path is cut against: a wrong anchor does not fail to merge, it
splits one file into two identities (`artifact_audit.py`).

**Nothing here is inferred from the value itself.** Each session's working directory is
recovered as evidence — the pin ledger first, the archived transcript second — and only
then resolved to a checkout. That ordering matters: `resumes` and `ybx` are equally
directory-shaped, and only the recovered cwd says one belongs to a repo and the other
does not.

**The verdict is reached about a value, not about a vertex,** and only a disproved
value is touched anywhere. A value is disproved when some session carrying it stood in
a directory that still exists, and no session carrying it ever stood in a checkout of
that name.

Both halves were learned by getting them wrong against the live graph. Without the
first, a value whose directories have all vanished reads as disproved, and
`thalamus-plane` — a repo that was *moved* into `code/graveyard/`, not deleted — loses
53 correct labels, because `git rev-parse` answers "no repo" identically for a path
that is gone and one that never had a repo. Without the second, four sessions that ran
from `$HOME` while labelled `thalamus` or `stepmania-chart-generator` would blank names
a hundred other sessions confirm; the pin ledger records no project, so a label
`basename(cwd)` could not have produced is indistinguishable from a deliberate
`THALAMUS_PROJECT` override.

The asymmetry is deliberate. This migration is allowed to be too timid and is not
allowed to be too eager: a wrong value that survives is still repairable, and a right
value overwritten with an empty one is not.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from gremlin_python.process.graph_traversal import GraphTraversalSource, __
from gremlin_python.process.traversal import T

PIN_LEDGER = Path.home() / ".thalamus" / "pins" / "pins.jsonl"
ARCHIVE = Path.home() / ".thalamus" / "archive"

# Threads belong to the session that raised them; these are the edges that say so.
_SESSION_TO_THREAD = ("SPAWNS", "CONTINUES", "RESOLVES")


@dataclass
class Change:
    """One vertex's project, and the evidence for moving it."""

    vid: str
    label: str
    before: str
    after: str
    evidence: str


@dataclass
class RepairPlan:
    changes: list[Change] = field(default_factory=list)
    # Vertices whose current value could not be disproved. Reported rather than
    # silently skipped: an unexplained survivor is the shape a bad migration takes.
    left_alone: list[tuple[str, str, str]] = field(default_factory=list)

    def by_label(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for change in self.changes:
            counts[change.label] = counts.get(change.label, 0) + 1
        return counts


def resolve_repo_root(path: str) -> str:
    """The checkout containing `path`, or `""`. Never raises."""
    if not path:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _exists(path: str) -> bool:
    """`Path.exists()` that treats an unreadable path as absent rather than raising.

    The graph names files under directories this process cannot stat — one artifact
    lives in `/var/lib/transmission-daemon/info/`. Unreadable is not evidence either
    way, and it lands in the same bucket as gone: no repo is claimed for it.
    """
    try:
        return Path(path).exists()
    except OSError:
        return False


def _ledger_cwds(ledger: Path) -> dict[str, str]:
    """session_id -> cwd, first line wins. Our own hook wrote these at session start."""
    found: dict[str, str] = {}
    if not ledger.exists():
        return found
    for line in ledger.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict) and row.get("session_id") and row.get("cwd"):
            found.setdefault(str(row["session_id"]), str(row["cwd"]))
    return found


def _archived_cwd(content_hash: str, archive: Path) -> str:
    """The first `cwd` in an archived transcript.

    First, not last, because that is what the parser records and what the transcript
    was filed under — a session that stepped into a worktree and exited there must not
    be re-anchored to where it stopped.
    """
    if not content_hash:
        return ""
    path = archive / content_hash[:2] / f"{content_hash}.jsonl"
    if not path.exists():
        return ""
    try:
        with path.open(errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(record, dict) and record.get("cwd"):
                    return str(record["cwd"])
    except OSError:
        return ""
    return ""


def plan(
    g: GraphTraversalSource,
    *,
    ledger: Path | None = None,
    archive: Path | None = None,
) -> RepairPlan:
    """What would change, and on what evidence. Reads only."""
    ledger_cwds = _ledger_cwds(ledger or PIN_LEDGER)
    archive_dir = archive or ARCHIVE
    result = RepairPlan()

    sessions = (
        g.V().has_label("Session").has("project")
        .project("vid", "project", "sid", "hashes")
        .by(T.id).by("project").by("session_id")
        .by(__.out("DERIVED_FROM").has_label("Source").values("content_hash").fold())
        .to_list()
    )

    # session vid -> the project it should carry, for the threads hanging off it.
    settled: dict[str, str] = {}
    # What the evidence says about each *value*, not each vertex. A value is disproved
    # as a repo name when some session carrying it stood in a directory that still
    # exists, and no session carrying it ever stood in a checkout of that name.
    #
    # Both halves are load-bearing. Without the first, a value whose directories have
    # all vanished reads as disproved and `thalamus-plane` loses 53 correct labels to a
    # repo that was merely moved. Without the second, four sessions that ran from
    # `$HOME` while labelled `thalamus` would blank a name that a hundred other
    # sessions confirm — and since the pin ledger records no project, a label that
    # `basename(cwd)` could not have produced is indistinguishable from a deliberate
    # `THALAMUS_PROJECT` override. A real repo's name is not this migration's business
    # whatever one session's cwd says.
    confirmed: set[str] = set()
    testable: set[str] = set()
    verdicts: dict[str, list[bool]] = {}
    for row in sessions:
        before = str(row["project"])
        cwd = ledger_cwds.get(str(row["sid"]), "")
        source = "pin ledger"
        if not cwd:
            for content_hash in row["hashes"]:
                cwd = _archived_cwd(str(content_hash), archive_dir)
                if cwd:
                    source = "archived transcript"
                    break
        # A recovered cwd is only evidence while it still exists. `git rev-parse` on a
        # path that is gone answers "no repo", which is indistinguishable from the
        # answer for a path that never had one — and the two demand opposite actions.
        # `thalamus-plane` is the case: its sessions ran in `code/thalamus-plane`, the
        # repo was moved to `code/graveyard/`, and treating the vanished path as
        # evidence blanks 53 correctly-labelled vertices.
        if not cwd or not _exists(cwd):
            result.left_alone.append((str(row["vid"]), "Session", before))
            continue

        root = resolve_repo_root(cwd)
        after = Path(root).name if root else ""
        settled[str(row["vid"])] = after
        testable.add(before)
        if after == before:
            confirmed.add(before)
        verdicts.setdefault(before, []).append((str(row["vid"]), after, f"{source} cwd={cwd}"))

    disproved = {value for value in testable if value and value not in confirmed}

    for value, seen in verdicts.items():
        for vid, after, evidence in seen:
            if value not in disproved:
                if after != value:
                    result.left_alone.append((vid, "Session", value))
                continue
            if after != value:
                result.changes.append(Change(vid, "Session", value, after, evidence))

    _plan_threads(g, settled, disproved, result)
    _plan_artifacts(g, disproved, result)
    return result


def _plan_threads(g, settled: dict[str, str], disproved: set[str], result: RepairPlan) -> None:
    """A thread takes its session's project — it is that session's continuation point.

    Only threads carrying a disproved value. A thread labelled `thalamus` is labelled
    with a real checkout's name, and whether *that particular* thread belongs to that
    particular repo is a different question from the one this migration answers.
    """
    rows = (
        g.V().has_label("Thread").has("project")
        .project("vid", "project", "sessions")
        .by(T.id).by("project")
        .by(__.in_(*_SESSION_TO_THREAD).has_label("Session").id_().fold())
        .to_list()
    )
    for row in rows:
        before = str(row["project"])
        if before not in disproved:
            continue
        owners = {settled[str(s)] for s in row["sessions"] if str(s) in settled}
        # One unambiguous owner, or nothing. A thread continued by sessions from two
        # different repos has no single answer and is not one this migration invents.
        if len(owners) != 1:
            result.left_alone.append((str(row["vid"]), "Thread", before))
            continue
        after = owners.pop()
        if after != before:
            result.changes.append(
                Change(str(row["vid"]), "Thread", before, after, "session it belongs to")
            )


def _plan_artifacts(g, disproved: set[str], result: RepairPlan) -> None:
    """Artifacts carrying a disproved value, and only those.

    The value is what is being corrected here, not the artifact's identity. A path that
    is gone today proves nothing about which repo it was in — resolving against the
    current filesystem would blank `charlie-things` on eleven artifacts whose files have
    since been deleted, which is the one outcome the module docstring forbids. So a
    surviving path may still name a repo, and everything else falls to `""`: the value
    it carries is a working directory's name, already disproved as a repo by every
    session that wrote it.

    Re-anchoring an artifact to the repo its path is *actually* in is the separate
    question of Artifact identity, which the architect ruled must be answered with
    derived `repo`/`path` properties rather than by mutating what is already there
    (ticket b5ed9cc5693f4225).
    """
    rows = (
        g.V().has_label("Artifact").has("project")
        .project("vid", "project", "identifier").by(T.id).by("project").by("identifier")
        .to_list()
    )
    for row in rows:
        before, identifier = str(row["project"]), str(row["identifier"])
        if before not in disproved:
            continue
        after = ""
        if identifier.startswith("/") and _exists(identifier):
            root = resolve_repo_root(str(Path(identifier).parent))
            after = Path(root).name if root else ""
        if after != before:
            evidence = f"path {identifier}" if identifier.startswith("/") else "not a path"
            result.changes.append(
                Change(str(row["vid"]), "Artifact", before, after, evidence)
            )


def apply(g: GraphTraversalSource, repair: RepairPlan) -> int:
    """Write the planned changes. Returns how many vertices moved."""
    for change in repair.changes:
        g.V(change.vid).property("project", change.after).iterate()
    return len(repair.changes)
