"""Named corpus pins — the reproducibility floor under the *trajectory* corpus.

`snapshots.py` pins the graph. Nothing pinned the run log, and a study over
`~/.thalamus/counterfactuals/runs.jsonl` therefore names no state at all: the file
is appended to by every campaign and has been **rewritten in place** by every
re-scoring pass. Measured on the corpus as found (2026-08-01, 140 records):

- `runs.jsonl.pre-voidfix` holds 90 records; all 90 survive in the current file and
  23 of them differ, on exactly `void`, `infra_fault`, `attributable` and
  `restamped_by`. The other 50 are appends. Appends and rewrites are tangled in one
  artifact, which is why it cannot answer "what did record X say on date D".
- Both hand-made backups already carry all 88 `rescored_at` stamps — a single
  timestamp, one rescore event — so **neither predates the contamination rescore**.
  The pre-rescore judgements of those 88 records exist nowhere on disk.

So this module does not backfill; it cannot. It seals the present under a name and
makes every future revision recoverable. The 88 stay a hole, reported as one, on
lab/037's rule that an absence *is* the measurement.

Three pieces, mirroring the snapshot registry so the two read the same way:

- `seal()` copies the run log to an immutable pinned file, writes a per-record
  **manifest**, and appends a registry row: record count, digests, git ref, note.
- `manifest()` maps each record's `run_id` to the digest of its body. A whole-file
  digest says *changed*; the manifest says *which records changed and which are new*
  — the diff a single root hash destroys.
- `diff()` reads that difference back, separating legitimate appends from in-place
  rewrites.

**Identity is derived, never assigned.** The corpus carries no `run_id` field and
adding one by rewriting the file would be the very mutation this module exists to
end. `run_id()` digests the fields fixed at the moment an arm is born — when it ran,
which task, which arm, which ref, which model, its worktree and its position in the
campaign order — so all 140 existing records acquire a stable identity without a byte
of the file moving. Verified unique across the corpus as found.

**A Merkle tree is deliberately not used.** Its payoff is logarithmic inclusion and
consistency proofs to a verifier who does not trust the log operator (RFC 6962). One
operator, no adversary, 140 records — and a Merkle *root* destroys exactly the
per-record diff that makes the manifest worth keeping. Revisit if the corpus is ever
published or a second writer appears.

Prior work: AuditWeave (arXiv 2607.09682) specifies a single append-only,
hash-chained ledger in which "any modification, reordering, insertion, or deletion of
events is detectable through chain verification", and measured that chain
verification flagged every injected mutation across four mutation classes over 2,000
randomized trials. ESAA (arXiv 2602.23193) specifies the append-only-log-plus-
materialized-view shape and `esaa verify` replay hashing — cited for its
specification only, since its evidence is two small case studies (9 tasks/49 events;
50 tasks/86 events) with no comparison against in-place update. Croissant Tasks
(arXiv 2605.29786) supplies the pinning boundary this module draws in
`derivation_fingerprint`, and its "checklists ... fail to scale" is why the pin is a
command rather than a line in `experiments/README.md`. The registry is committed and
the sealed copies are not, on the same rule as `snapshots.py`: the graph and the run
log are one operator's history and are never shipped.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from thalamus.eval.arms import RUNS_BASE

REGISTRY = Path.home() / ".thalamus" / "corpora.jsonl"
MANIFEST_DIR = Path.home() / ".thalamus" / "corpora"

# Sealed copies sit beside the live log, outside git — the same split the snapshot
# registry draws between the committed ledger and the uncommitted `.kryo`.
PINNED_DIR = RUNS_BASE / "pinned"

# A pin name is part of a filename and of a published citation, so it is restricted
# rather than sanitised — a name that needs escaping is a name that will be quoted
# wrong somewhere.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

# The fields fixed when an arm is born. Everything else about a record is a verdict
# about it, and a verdict is exactly what supersession is allowed to change.
BIRTH_FIELDS = ("ts", "task", "arm", "scope", "ref", "model", "worktree", "order_index")

# Bookkeeping the corpus layer adds. Excluded from the body digest so that stamping a
# revision does not change the digest of the body it is stamping.
REVISION_FIELDS = ("run_id", "revision", "supersedes", "superseded_at", "scorer_config")

# Legible rather than hashed, for the reason `judge_config` is (lab/037): a straddled
# window should say *which* dial moved. Bump when a detector's verdict can change.
DETECTOR_CONFIG = "d1:escape-v1+history-reach-v1"


class CorpusError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorpusRow:
    name: str
    taken_at: str
    records: int
    sha256: str
    byte_size: int
    git_ref: str
    manifest_sha256: str
    note: str

    @property
    def pinned_path(self) -> Path:
        return PINNED_DIR / f"{self.name}.jsonl"

    @property
    def manifest_path(self) -> Path:
        return MANIFEST_DIR / f"{self.name}.jsonl"


@dataclass(frozen=True)
class ManifestRow:
    run_id: str
    body_sha256: str
    revision: int


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def run_id(record: dict) -> str:
    """Stable identity for one arm run, derived from its birth fields.

    Derived rather than stored: the corpus predates this module and rewriting it to
    add an identity column would be an in-place mutation of the evidence base, which
    is the failure being fixed. Two records agreeing on all of `BIRTH_FIELDS` would
    be the same run; verified unique across the 140 records as found.
    """
    material = _canonical({field: record.get(field) for field in BIRTH_FIELDS})
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def body_digest(record: dict) -> str:
    """Digest of the record's substance, excluding corpus-layer bookkeeping.

    Allowed to change under supersession — that is the point. What must not change
    silently is which `run_id` it belongs to.
    """
    body = {k: v for k, v in record.items() if k not in REVISION_FIELDS}
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


def load_records(path: Path | None = None) -> list[dict]:
    target = path or (RUNS_BASE / "runs.jsonl")
    if not target.is_file():
        return []
    return [json.loads(line) for line in target.read_text().splitlines() if line.strip()]


def head_revisions(records: list[dict]) -> list[dict]:
    """The current view: the last revision of each run, in first-appearance order.

    Every existing analysis reads the run log as one record per run. Supersession
    appends, so this filter is what keeps that true — the commutation property that
    lets the write-side change land without rewriting the readers.
    """
    latest: dict[str, dict] = {}
    order: list[str] = []
    for record in records:
        key = record.get("run_id") or run_id(record)
        if key not in latest:
            order.append(key)
        previous = latest.get(key)
        if previous is None or record.get("revision", 0) >= previous.get("revision", 0):
            latest[key] = record
    return [latest[key] for key in order]


def manifest(records: list[dict]) -> list[ManifestRow]:
    """One row per run, sorted by `run_id` so two manifests diff line-for-line."""
    rows = [
        ManifestRow(
            run_id=record.get("run_id") or run_id(record),
            body_sha256=body_digest(record),
            revision=int(record.get("revision", 0)),
        )
        for record in head_revisions(records)
    ]
    return sorted(rows, key=lambda row: row.run_id)


def supersede(record: dict, prior: dict, *, scorer_config: str, at: str = "") -> dict:
    """Build the revision that replaces `prior`, instead of overwriting it.

    Generalizes the one record in the corpus that already did this correctly: the
    2026-07-31 memo-echo rescore kept `memo_echoed_prior` beside the fresh value and
    stamped `judge_config`, while the 23 records the void fix touched kept only a
    `restamped_by` marker and lost what they had said. A marker that records *that*
    something changed, and not *what*, is not provenance.
    """
    revised = dict(record)
    revised["run_id"] = prior.get("run_id") or run_id(prior)
    revised["revision"] = int(prior.get("revision", 0)) + 1
    revised["supersedes"] = body_digest(prior)
    revised["superseded_at"] = at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    revised["scorer_config"] = scorer_config
    return revised


def derivation_fingerprint(
    task,
    repo: Path,
    *,
    fix_paths: frozenset[str] | None = None,
    tasks_base: Path | None = None,
) -> dict:
    """What a contamination verdict was computed against, pinned onto the record.

    lab/037 finding #5, closed. A campaign record stored `ref` and nothing else about
    its own oracle, so editing a task YAML afterwards silently re-scoped every prior
    contamination verdict, and the fix-touched path set was re-derived on read from a
    git diff over the operator's *live* repo.

    The boundary applied here: config may be re-derived iff the artifact is a pure
    function of the pinned inputs and the code at the pinned `git_ref`, **and** every
    input to that derivation is itself pinned and immutable. The path set fails on
    the second clause — the repo is mutable — which is not hypothetical: the
    2026-07-29 `git-filter-repo` rewrite changed every SHA and left both task refs
    pointing at objects that no longer existed, remapped by hand through
    `commit-map`. Croissant Tasks' conceptual-reproducibility goalpost (arXiv
    2605.29786) is the licence to leave implementation detail unpinned; it does not
    reach a verdict whose inputs move.
    """
    from thalamus.eval.arms import fix_touched_paths

    source_ref = task.source.ref
    fix_ref = task.source.fix_ref
    if fix_paths is None:
        try:
            fix_paths = fix_touched_paths(repo, source_ref, fix_ref)
        except Exception:
            fix_paths = frozenset()
    paths = sorted(fix_paths)

    return {
        "task_digest": task_digest(task, tasks_base),
        "fix_ref": fix_ref,
        "fix_paths": paths,
        "fix_paths_digest": hashlib.sha256(_canonical(paths).encode()).hexdigest()[:16],
        "detector_config": DETECTOR_CONFIG,
    }


def task_digest(task, tasks_base: Path | None = None) -> str:
    """Digest of the task definition the oracle came from.

    The highest-value field in the fingerprint, because it is the one that re-scopes
    verdicts *already recorded*. Taken over the YAML **bytes** where they can be
    found — `load_battery` enforces that the filename is the id, so the path is
    resolvable from the task alone — because the comments are load-bearing here: the
    2026-07-29 ref remapping lives in a comment block, and a parsed-model digest
    would call that edit no change. Falls back to the parsed model for a task with no
    file behind it, which is honest about being a weaker digest rather than refusing.
    """
    from thalamus.eval.tasks import tasks_dir

    path = tasks_dir(tasks_base) / f"{task.id}.yaml"
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    payload = task.model_dump(mode="json") if hasattr(task, "model_dump") else dict(task)
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()[:16]


def seal(name: str, *, note: str = "", runs_path: Path | None = None) -> CorpusRow:
    """Pin the run log under `name` and record what was pinned.

    Refuses to overwrite: a name that has been cited must keep meaning what it meant.
    Re-pinning a later state is a new name, not a mutation of an old one.
    """
    if not _NAME_RE.match(name):
        raise CorpusError(
            f"invalid corpus name `{name}` — lowercase letters, digits and hyphens, 3-64 chars"
        )
    if any(row.name == name for row in registry()):
        raise CorpusError(f"corpus `{name}` already exists; corpus pins are immutable")

    source = runs_path or (RUNS_BASE / "runs.jsonl")
    if not source.is_file():
        raise CorpusError(f"no run log at {source}")

    records = load_records(source)
    if not records:
        raise CorpusError(f"{source} holds no records")

    PINNED_DIR.mkdir(parents=True, exist_ok=True)
    target = PINNED_DIR / f"{name}.jsonl"
    if target.exists():
        raise CorpusError(f"{target} exists but `{name}` is not in the registry")
    shutil.copy2(source, target)
    target.chmod(0o444)

    rows = manifest(records)
    manifest_text = "".join(_canonical(asdict(row)) + "\n" for row in rows)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / f"{name}.jsonl").write_text(manifest_text)

    payload = source.read_bytes()
    row = CorpusRow(
        name=name,
        taken_at=datetime.now(timezone.utc).isoformat(),
        records=len(rows),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        git_ref=_git_ref(),
        manifest_sha256=hashlib.sha256(manifest_text.encode()).hexdigest(),
        note=note,
    )
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open("a") as handle:
        handle.write(json.dumps(asdict(row)) + "\n")
    return row


def registry() -> list[CorpusRow]:
    if not REGISTRY.is_file():
        return []
    return [
        CorpusRow(**json.loads(line))
        for line in REGISTRY.read_text().splitlines()
        if line.strip()
    ]


def find(name: str) -> CorpusRow:
    for row in registry():
        if row.name == name:
            return row
    raise CorpusError(f"no pinned corpus named `{name}`")


def verify(name: str) -> tuple[bool, bool]:
    """`(corpus intact, manifest intact)` for a pinned name.

    Two answers rather than one: a sealed file that still hashes to its citation and
    a manifest that no longer matches it are different failures, and pooling them
    would hide the worse one.
    """
    row = find(name)
    path = row.pinned_path
    corpus_ok = (
        path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == row.sha256
    )
    manifest_path = row.manifest_path
    manifest_ok = (
        manifest_path.is_file()
        and hashlib.sha256(manifest_path.read_bytes()).hexdigest() == row.manifest_sha256
    )
    return corpus_ok, manifest_ok


def read_manifest(name: str) -> list[ManifestRow]:
    row = find(name)
    if not row.manifest_path.is_file():
        raise CorpusError(f"manifest for `{name}` is missing at {row.manifest_path}")
    return [
        ManifestRow(**json.loads(line))
        for line in row.manifest_path.read_text().splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class CorpusDiff:
    added: list[str]
    rewritten: list[str]
    superseded: list[str]
    removed: list[str]
    unchanged: int

    @property
    def clean(self) -> bool:
        """No record present at seal time has changed except by supersession."""
        return not self.rewritten and not self.removed


def diff(name: str, records: list[dict] | None = None) -> CorpusDiff:
    """What has happened to the corpus since `name` was sealed.

    The distinction the whole module exists to draw: **appends are legitimate and
    in-place rewrites are not**, and a whole-file digest reports both as one bit.
    A record whose body moved *and* whose revision advanced is a supersession — the
    write-side discipline working. A record whose body moved at the same revision was
    rewritten underneath its own identity.
    """
    pinned = {row.run_id: row for row in read_manifest(name)}
    current = {row.run_id: row for row in manifest(records if records is not None else load_records())}

    added, rewritten, superseded, removed = [], [], [], []
    unchanged = 0
    for key, row in current.items():
        was = pinned.get(key)
        if was is None:
            added.append(key)
        elif was.body_sha256 == row.body_sha256:
            unchanged += 1
        elif row.revision > was.revision:
            superseded.append(key)
        else:
            rewritten.append(key)
    removed = [key for key in pinned if key not in current]

    return CorpusDiff(
        added=sorted(added),
        rewritten=sorted(rewritten),
        superseded=sorted(superseded),
        removed=sorted(removed),
        unchanged=unchanged,
    )


def _git_ref() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[3]),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""
