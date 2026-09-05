"""The CI triage loop's host side: what notices a red master, and what it may start.

A red `qe-fast` on master is a report nobody is obliged to read. Measured before this
existed: the suite was red on fifteen consecutive pushes to master and none of them
carried a new regression, so the gate stopped carrying information long before anyone
decided to ignore it. This module is the consumer that was missing — it watches for the
red, and spawns one pinned `qe` session to triage it.

## The filter is the whole self-trigger guard

`qe-fast`, `qe-linux`, `qe-macos` and `verify` all trigger on **both** `push` and
`pull_request`. The loop's own remediation lands as a PR, and that PR produces CI runs
under `pull_request` on its own branch. So a watcher that fires on "any red run" fires on
its own output, before a human has looked at it — a self-feeding loop whose input is its
own exhaust.

`red_master_runs` therefore filters on `event == "push"` AND `head_branch == "master"`,
and nothing downstream re-widens it. There is no second mechanism doing this job; this
predicate is it.

## Why the state is a replaced file and not an append log

`harness/closes.py` and `harness/ceremonies.py` both append a line per event, and both
carry the defect filed as #169: a crash leaving a partial line with no trailing newline
makes the next writer's valid append merge onto it, and the reader drops the merged line
whole — losing the *post*-crash row, not just the in-flight one. This state is small,
bounded, and always rewritten in full, so `os.replace` over a temp file in the same
directory gets durability from the filesystem's rename atomicity and never enters that
class at all. An append log here would buy history nobody reads at the cost of a known
corruption mode.

## What bounds it

`ESCALATE_AFTER` is **inferred, not measured** — deliberately so, and the reasoning is
recorded rather than hidden. No attempt-count-to-success curve exists for this loop,
because the loop does not exist yet. The nearest evidence is SlopCodeBench (arXiv
2603.24755), which measured agents extending their own prior output across checkpoints
with no human between iterations: structural erosion rose in 77% of trajectories and
verbosity in 75.5%, and the one intervention tested (explicit quality guidance) cut the
*initial* level by up to a third without moving the degradation rate. That is a different
intervention on a different task shape, so it is not a measurement of this loop — but it
argues against assuming one more unattended attempt reliably helps. A small bound costs
an escalation; a large one compounds.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

TRIAGE_DIR = Path.home() / ".thalamus" / "ci-triage"
STATE_FILE = TRIAGE_DIR / "state.json"

# Written by `tests/qe/ledger.py`, read here. The suite does not ship in the wheel — a
# released package carrying known-red entries would hand every installer a working
# oracle for the defects in the release they just installed — so this reader restates
# the path instead of importing the writer.
QE_LEDGER = Path.home() / ".thalamus" / "qe" / "runs.jsonl"

# The branch and event a dispatchable red must carry. Both, not either.
WATCHED_BRANCH = "master"
WATCHED_EVENT = "push"

# Consecutive dispatches against one (case, witness) before the loop stops trying and
# says so. See the module docstring: inferred, not measured.
ESCALATE_AFTER = 2

# Ledger verdicts that mean a case is unresolved and worth a session. `fixed` is
# deliberately included: exit 2 demands an expectation be deleted, and that deletion is
# one of the two things `qe` may do without asking.
ACTIONABLE_VERDICTS = ("new-failure", "drifted", "fixed", "malformed")


class TriageRefused(Exception):
    """A dispatch was refused, or a report failed independent verification.

    Raised rather than returned wherever a caller could otherwise mistake the refusal
    for "nothing to do" — the two have opposite meanings for an unattended loop.
    """


@dataclass(frozen=True)
class RedRun:
    """One failed CI run, as the forge reports it."""

    run_id: str
    workflow: str
    branch: str
    event: str
    head_sha: str
    url: str

    @property
    def dispatchable(self) -> bool:
        """The self-trigger guard, as a property so no caller has to remember it."""
        return self.branch == WATCHED_BRANCH and self.event == WATCHED_EVENT


def _gh(*args: str, repo: str | None = None) -> tuple[int, str]:
    argv = ["gh", *args]
    if repo:
        argv += ["--repo", repo]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TriageRefused(f"`gh` is not usable here, so no run state can be read: {exc}")
    return out.returncode, out.stdout.strip()


def red_master_runs(repo: str | None = None, limit: int = 20) -> list[RedRun]:
    """Failed runs from a push to master, newest first. Never PR runs, never other refs.

    The filter is applied here rather than by the caller so that a caller cannot widen it
    by accident — see the module docstring on why widening it feeds the loop its own
    output.
    """
    rc, raw = _gh(
        "run", "list", "--limit", str(limit), "--json",
        "databaseId,workflowName,headBranch,event,conclusion,headSha,url",
        repo=repo,
    )
    if rc != 0 or not raw:
        raise TriageRefused(
            "`gh run list` returned nothing; a watcher that cannot see CI must not "
            "report the branch as green"
        )
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TriageRefused(f"`gh run list` did not return JSON: {exc}")

    out: list[RedRun] = []
    for row in rows if isinstance(rows, list) else []:
        if row.get("conclusion") != "failure":
            continue
        run = RedRun(
            run_id=str(row.get("databaseId", "")),
            workflow=str(row.get("workflowName", "")),
            branch=str(row.get("headBranch", "")),
            event=str(row.get("event", "")),
            head_sha=str(row.get("headSha", "")),
            url=str(row.get("url", "")),
        )
        if run.dispatchable:
            out.append(run)
    return out


def witness_key(case: str, witness: str) -> str:
    """`(case, witness)` as one string, the witness hashed because it runs to kilobytes.

    Keyed on the witness and not on the case alone: a case that fails a second time with
    a *different* witness is a different defect at the same site, and giving it the
    previous attempt's budget would retire it before it had been tried once.
    """
    digest = hashlib.sha256(witness.encode("utf-8", "replace")).hexdigest()[:12]
    return f"{case}|{digest}"


@dataclass
class TriageState:
    """Host-local, not in git, not visible to CI — the same placement and reason as
    `harness/closes.py`'s ledger: it records what this box did, and CI must not be able
    to read it as authorization."""

    open_prs: dict[str, int] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    seen_runs: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> TriageState:
        target = path or STATE_FILE
        if not target.is_file():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A state file that cannot be read is treated as empty rather than fatal:
            # the worst it costs is one duplicate dispatch, which the open-PR check
            # catches, whereas refusing to run leaves a red master unattended.
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            open_prs={str(k): int(v) for k, v in (data.get("open_prs") or {}).items()},
            attempts={str(k): int(v) for k, v in (data.get("attempts") or {}).items()},
            seen_runs=[str(r) for r in (data.get("seen_runs") or [])][-200:],
        )

    def save(self, path: Path | None = None) -> None:
        """Write in full, then rename. See the module docstring on why not an append."""
        target = path or STATE_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        payload = {
            "open_prs": self.open_prs,
            "attempts": self.attempts,
            "seen_runs": self.seen_runs[-200:],
        }
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)

    def attempts_for(self, case: str, witness: str) -> int:
        return self.attempts.get(witness_key(case, witness), 0)

    def record_dispatch(self, case: str, witness: str, run_id: str = "") -> None:
        key = witness_key(case, witness)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if run_id and run_id not in self.seen_runs:
            self.seen_runs.append(run_id)

    def record_pr(self, case: str, number: int) -> None:
        self.open_prs[case] = int(number)

    def clear_pr(self, case: str) -> None:
        self.open_prs.pop(case, None)

    def forget(self, case: str, witness: str) -> None:
        """Drop a case's attempt budget once its defect is actually gone."""
        self.attempts.pop(witness_key(case, witness), None)
        self.clear_pr(case)


def refusal_for(case: str, witness: str, state: TriageState) -> str:
    """Why this case must not be dispatched now, or "" if it may be.

    Both refusals are the same hazard seen from two ends: an open PR means a fix is
    already in flight for this case, and a spent attempt budget means the loop has
    already tried twice and is not owed a third by anything measured.
    """
    if case in state.open_prs:
        return (
            f"{case} already has PR #{state.open_prs[case]} open and undecided — a "
            f"second session would work a case someone is already working"
        )
    spent = state.attempts_for(case, witness)
    if spent >= ESCALATE_AFTER:
        return (
            f"{case} has had {spent} unattended attempt(s) against this exact witness "
            f"and is still red; escalating rather than trying again"
        )
    return ""


@dataclass(frozen=True)
class Disagreement:
    """One case where a report and the ledger do not say the same thing."""

    case: str
    claimed: str
    ledger: str

    def __str__(self) -> str:
        return f"{self.case}: report says {self.claimed!r}, ledger says {self.ledger!r}"


def verify_report(
    claims: Mapping[str, str], ledger_rows: Sequence[Mapping[str, object]]
) -> list[Disagreement]:
    """Check a triage report against the ledger it claims to describe.

    `main` does not act on `qe`'s classification because `qe` asserted it — it re-derives
    the verdict from the ledger rows and acts only where the two agree. This is the step
    the loop's falsifier is aimed at: a report claiming a case is triaged and harmless
    while the ledger records `new-failure` for that same case must be refused, not
    merged.

    Returns every disagreement rather than the first, because a report is refused as a
    whole and the operator reading the refusal needs all of it.
    """
    by_case: dict[str, str] = {}
    for row in ledger_rows:
        case = str(row.get("case", ""))
        if case:
            by_case[case] = str(row.get("verdict", ""))

    out: list[Disagreement] = []
    for case, claimed in claims.items():
        actual = by_case.get(case, "")
        if not actual:
            out.append(Disagreement(case=case, claimed=str(claimed), ledger="<absent>"))
        elif str(claimed) != actual:
            out.append(Disagreement(case=case, claimed=str(claimed), ledger=actual))
    return out


def actionable_cases(ledger_rows: Iterable[Mapping[str, object]]) -> list[tuple[str, str]]:
    """`(case, witness)` for every row whose verdict the loop exists to act on."""
    out: list[tuple[str, str]] = []
    for row in ledger_rows:
        if str(row.get("verdict", "")) in ACTIONABLE_VERDICTS:
            case = str(row.get("case", ""))
            if case:
                out.append((case, str(row.get("witness", ""))))
    return out


def read_ledger(path: Path | None = None) -> list[dict]:
    """The rows of the most recent run in the qe ledger.

    The suite owns the writer (`tests/qe/ledger.py`), which does not ship in the wheel,
    so the path is restated here rather than imported. Only the newest run's rows are
    returned: the ledger is append-only across runs, and a verdict from three runs ago
    is not evidence about the tree as it stands.
    """
    target = path or QE_LEDGER
    if not target.is_file():
        return []
    rows: list[dict] = []
    with target.open(errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("case"):
                rows.append(row)
    if not rows:
        return []
    newest = rows[-1].get("run_id")
    return [row for row in rows if row.get("run_id") == newest]


def escalate(pr_number: int, message: str, repo: str | None = None) -> None:
    """Say why the loop stopped, on the PR, where the operator already looks.

    Not an issue: once the remediation PR exists it is already the tracker entry, and a
    parallel issue for something visible as an open PR duplicates the artifact instead of
    adding to it.
    """
    rc, out = _gh("pr", "comment", str(pr_number), "--body", message, repo=repo)
    if rc != 0:
        raise TriageRefused(f"could not comment on PR #{pr_number}: {out}")


def dispatch(project_root: Path, scope: str = "qe") -> None:
    """Open one pinned session to triage the red. No new spawn path.

    `pin.spawn` is already the plane's spawn button: it opens one detached window, writes
    the derived agent files so `--agent` resolves regardless of cwd, sets
    `THALAMUS_SCOPE`, and returns only after the session has actually started. A second
    launcher here would be a second thing to keep correct.
    """
    from thalamus.harness import pin

    pin.spawn(scope=scope, cwd=project_root)


def run_once(
    project_root: Path,
    repo: str | None = None,
    state_path: Path | None = None,
    spawn: bool = True,
) -> RedRun | None:
    """One poll. Returns the run it dispatched for, or None if there was nothing new.

    A run is dispatched at most once ever, which is what `seen_runs` buys: the watcher
    polls on an interval, and the same red run stays red on every subsequent poll until
    something merges. Without this, a five-minute interval means twelve sessions an hour
    against one failure.

    `spawn=False` reports what it would do and starts nothing, and — the part that would
    be a wart if it were left out — does not consume the dedup either. A dry run that
    marked the run seen would make the next real poll skip the very failure it was run to
    preview, so the rehearsal would suppress the performance.
    """
    state = TriageState.load(state_path)
    unseen = [run for run in red_master_runs(repo) if run.run_id not in state.seen_runs]
    if not unseen:
        return None

    target = unseen[0]
    if not spawn:
        return target

    dispatch(project_root)
    state.seen_runs.append(target.run_id)
    state.save(state_path)
    return target
