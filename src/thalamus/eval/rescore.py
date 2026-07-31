"""Retroactive contamination stamping for campaigns that ran before the detectors.

`detect_worktree_escape` and `detect_history_reach` were added after lab/020, so
they stamp **going forward** only. Every campaign already on disk carries a
now-known leak channel that nobody has re-derived: lab/021 corrected lab/020's
rate to 3-of-24 by hand, and lab/022 measured 9-of-88 history reaches by hand,
but neither number is in the records themselves. A rate derived by hand in a lab
entry is not queryable and does not survive the next analysis.

This module applies the existing detectors backwards over `runs.jsonl`. It
introduces no metric: the classes (`answer_key` / `operator_repo` /
`history_reach`), the flag-never-exclude stance (arXiv 2111.03382, 2605.05564)
and the `contaminated` exclusion key are lab/021's, unchanged. Only the stamps'
provenance differs, which is why a re-scored record is marked `rescored_at` —
a stamp derived retroactively from a retained transcript is not the same
evidence as one taken at run time, and a later reader must be able to tell.

**A record is stamped only when its evidence is complete.** An unreadable
transcript, an unknown task, or a ref that no longer resolves yields a refusal
with a reason, never a clean stamp. The failure this guards against is the one
lab/022 caught in `transcript_text`: a default that returns a plausible value
instead of failing, which files an arm that reached for the answer key as one
that never tried. Re-scoring is the exact operation where that failure would be
invisible, since there is no live run to contradict it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from thalamus.eval.arms import (
    RUNS_BASE,
    ArmError,
    _git,
    detect_history_reach,
    detect_worktree_escape,
    fix_touched_paths,
    transcript_text,
)
from thalamus.eval.tasks import load_battery

RUNS_FILE = RUNS_BASE / "runs.jsonl"

# Refusal reasons. Each means "the evidence is incomplete", never "clean".
NO_TRANSCRIPT = "no-transcript"
NO_SESSION = "no-session-id"
UNKNOWN_TASK = "unknown-task"
UNRESOLVABLE_REF = "unresolvable-ref"

STAMPED = "stamped"
ALREADY = "already-stamped"


@dataclass
class Outcome:
    """What re-scoring concluded about one run record."""

    index: int
    task: str
    arm: str
    date: str
    status: str
    escapes: list[dict] = field(default_factory=list)
    contaminated: bool | None = None
    memo_echoed: dict | None = None
    detail: str = ""

    @property
    def stamped(self) -> bool:
        return self.status == STAMPED

    @property
    def campaign(self) -> tuple[str, str]:
        """A campaign is one task's arms, not one day's work — two tasks ran on
        2026-07-26 and reporting them together would merge distinct experiments."""
        return (self.task, self.date)

    @property
    def history_hits(self) -> list[dict]:
        """Escapes from `detect_history_reach`, which alone carries `command`.

        Counted separately because that detector splits its own hits across two
        kinds: a git command naming the task's `fix_ref` is filed `answer_key`,
        not `history_reach`. Counting only the latter undercounts the git
        channel — the channel's size is the arms that used it, whatever the
        read turned out to be worth.
        """
        return [e for e in self.escapes if "command" in e]


def _ref_resolves(repo: Path, ref: str) -> bool:
    if not ref.strip():
        return False
    try:
        _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except ArmError:
        return False
    return True


def load_records(path: Path | None = None) -> list[dict]:
    target = path or RUNS_FILE
    if not target.is_file():
        return []
    return [
        json.loads(line)
        for line in target.read_text().splitlines()
        if line.strip()
    ]


def rescore_records(
    records: list[dict],
    repo: Path,
    tasks_base: Path | None = None,
    projects_base: Path | None = None,
    force: bool = False,
) -> list[Outcome]:
    """Derive contamination stamps for records that lack them.

    Pure: computes outcomes and leaves `records` untouched. `apply_outcomes`
    does the mutation, so a dry run and a write share one derivation.
    """
    tasks, _ = load_battery(tasks_base)
    by_id = {t.id: t for t in tasks}
    # Refs and fix-path sets are per-task, not per-record, and a git call per
    # record would repeat identical work 88 times.
    fix_paths_cache: dict[str, frozenset[str]] = {}
    ref_ok_cache: dict[tuple[str, str], bool] = {}

    outcomes: list[Outcome] = []
    for i, record in enumerate(records):
        task_id = record.get("task") or ""
        outcome = Outcome(
            index=i,
            task=task_id,
            arm=record.get("arm") or "",
            date=(record.get("ts") or "")[:10],
            status=STAMPED,
        )

        if not force and record.get("contaminated") is not None:
            outcome.status = ALREADY
            outcomes.append(outcome)
            continue

        task = by_id.get(task_id)
        if task is None:
            outcome.status = UNKNOWN_TASK
            outcome.detail = f"`{task_id}` is not in the battery"
            outcomes.append(outcome)
            continue

        source_ref, fix_ref = task.source.ref, task.source.fix_ref
        # An authored task legitimately has no fix_ref; a replayed task whose
        # fix_ref no longer resolves would silently yield an empty answer-key
        # set and downgrade every answer_key hit to operator_repo.
        if fix_ref.strip():
            key = (source_ref, fix_ref)
            if key not in ref_ok_cache:
                ref_ok_cache[key] = _ref_resolves(repo, source_ref) and _ref_resolves(
                    repo, fix_ref
                )
            if not ref_ok_cache[key]:
                outcome.status = UNRESOLVABLE_REF
                outcome.detail = f"{source_ref}..{fix_ref} no longer resolves in {repo}"
                outcomes.append(outcome)
                continue

        session_id = (record.get("agent") or {}).get("session_id") or ""
        if not session_id:
            outcome.status = NO_SESSION
            outcome.detail = "record carries no agent.session_id"
            outcomes.append(outcome)
            continue

        transcript = transcript_text(
            Path(record.get("worktree") or ""), session_id, projects_base
        )
        if not transcript:
            outcome.status = NO_TRANSCRIPT
            outcome.detail = f"no transcript on disk for session {session_id}"
            outcomes.append(outcome)
            continue

        if task_id not in fix_paths_cache:
            fix_paths_cache[task_id] = fix_touched_paths(repo, source_ref, fix_ref)

        outcome.escapes = detect_worktree_escape(
            transcript,
            Path(record.get("worktree") or ""),
            repo,
            fix_paths_cache[task_id],
        ) + detect_history_reach(transcript, source_ref, fix_ref)
        outcome.contaminated = any(
            e["kind"] == "answer_key" for e in outcome.escapes
        )
        outcomes.append(outcome)

    return outcomes


NOT_INJECTED = "not-injected"
NO_MEMO = "no-memo-recorded"


def memo_echo_outcomes(
    records: list[dict],
    *,
    tasks_base: Path | None = None,
    projects_base: Path | None = None,
) -> list[Outcome]:
    """Re-derive `memo_echoed` under the current judge, for arms that carry one.

    Why this exists: the probe's node key changed. It was `"memo"`, which layer 1's
    substring-on-id path matched against any arm that said the word — so the verdict
    could come back "cited by vertex ID" on prose that cited nothing. The key is now
    `__injected_memo__`, named so it cannot occur in prose. Four records on disk still
    carry the old key's output, and nothing in them says which judge produced it
    (lab/037).

    The ratios are unaffected — `matched / len(terms)` is computed the same way under
    both keys — so this is not a correction of lab/036's reading, which rests on
    ratios. What it corrects is the evidence string and the `used` flag beside it.

    Same evidence discipline as contamination re-scoring: an arm whose transcript is
    gone gets a refusal with a reason, never a fresh-looking verdict. And the result
    is stamped with `judge_config`, so the next reader can tell which instrument
    produced it instead of inferring it from an impossible evidence string.
    """
    from thalamus.eval.arms import arm_home_for, memo_echo, parse_arm
    from thalamus.eval.attribution import judge_fingerprint
    from thalamus.contract.manifest import available_scopes

    tasks, _ = load_battery(tasks_base)
    by_id = {t.id: t for t in tasks}
    scopes = available_scopes()

    outcomes: list[Outcome] = []
    for i, record in enumerate(records):
        task_id = record.get("task") or ""
        outcome = Outcome(
            index=i,
            task=task_id,
            arm=record.get("arm") or "",
            date=(record.get("ts") or "")[:10],
            status=STAMPED,
        )
        if record.get("memo_echoed") is None:
            outcome.status = NOT_INJECTED if not record.get("arm", "").startswith(
                "ceiling"
            ) else NO_MEMO
            outcomes.append(outcome)
            continue

        task = by_id.get(task_id)
        if task is None:
            outcome.status = UNKNOWN_TASK
            outcome.detail = f"`{task_id}` is not in the battery"
            outcomes.append(outcome)
            continue

        session_id = (record.get("agent") or {}).get("session_id") or ""
        if not session_id:
            outcome.status = NO_SESSION
            outcome.detail = "record carries no agent.session_id"
            outcomes.append(outcome)
            continue

        # A confined arm wrote its transcript into the container's HOME beside the
        # worktree, not the operator's, so looking only in ~/.claude/projects reports
        # every sandboxed run as evidence-gone. Try the arm home first, exactly as
        # `run_arm` does at run time, and fall back to the operator's.
        worktree = Path(record.get("worktree") or "")
        arm_projects = arm_home_for(worktree) / ".claude" / "projects"
        transcript = ""
        if arm_projects.is_dir():
            transcript = transcript_text(worktree, session_id, arm_projects)
        if not transcript:
            transcript = transcript_text(worktree, session_id, projects_base)
        if not transcript:
            outcome.status = NO_TRANSCRIPT
            outcome.detail = f"no transcript on disk for session {session_id}"
            outcomes.append(outcome)
            continue

        try:
            framing = parse_arm(record.get("arm") or "", scopes).framing
        except ArmError:
            framing = "conclusion"
        fresh = memo_echo(task, transcript, framing)
        fresh["judge_config"] = judge_fingerprint()
        outcome.memo_echoed = fresh
        old = record.get("memo_echoed") or {}
        outcome.detail = (
            f"used {old.get('used')}->{fresh.get('used')}, "
            f"evidence was {str(old.get('evidence'))[:34]!r}"
            if old.get("used") != fresh.get("used")
            or old.get("evidence") != fresh.get("evidence")
            else "unchanged"
        )
        outcomes.append(outcome)

    return outcomes


def apply_outcomes(records: list[dict], outcomes: list[Outcome]) -> int:
    """Stamp the records that earned a stamp. Returns how many changed."""
    stamped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = 0
    for outcome in outcomes:
        if not outcome.stamped:
            continue
        record = records[outcome.index]
        if outcome.memo_echoed is not None:
            # Kept beside the fresh verdict rather than overwritten. The old value
            # is the only evidence of which judge the corpus used to carry, and
            # discarding it while fixing a provenance gap would be the same mistake
            # in the other direction (lab/037).
            record.setdefault("memo_echoed_prior", record.get("memo_echoed"))
            record["memo_echoed"] = outcome.memo_echoed
            record["memo_echo_rescored_at"] = stamped_at
            changed += 1
            continue
        record["escapes"] = outcome.escapes
        record["contaminated"] = outcome.contaminated
        # The stamp's provenance: derived from a retained transcript after the
        # fact, not observed at run time.
        record["rescored_at"] = stamped_at
        changed += 1
    return changed


def write_records(records: list[dict], path: Path | None = None) -> Path:
    """Rewrite the run log atomically, keeping the previous copy alongside.

    The run log is the campaign evidence base; a partial write from a crash
    mid-rewrite would corrupt records that were never being re-scored.
    """
    target = path or RUNS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        backup = target.with_suffix(target.suffix + ".pre-rescore")
        backup.write_text(target.read_text())
    with NamedTemporaryFile(
        "w", dir=str(target.parent), prefix=".runs-", suffix=".jsonl", delete=False
    ) as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp = Path(handle.name)
    temp.replace(target)
    return target


def render_rescore(outcomes: list[Outcome], wrote: bool) -> str:
    """Per-campaign rates, in arms, with refusals named rather than folded in.

    Every rate is `arms / arms`. lab/022's "9 of 88" mixed units — 9 was git
    reach *events*, 88 was arms — and an arm that reached twice is still one
    contaminated arm, so events are reported alongside, never as the numerator.
    """
    lines: list[str] = []
    campaigns = sorted({o.campaign for o in outcomes})

    lines.append(
        f"Re-scored {len(outcomes)} run record(s) across {len(campaigns)} campaign(s)."
    )
    lines.append("A campaign is one task's arms; rates are arms/arms.\n")
    for campaign in campaigns:
        group = [o for o in outcomes if o.campaign == campaign]
        gradeable = [o for o in group if o.stamped]
        refused = [o for o in group if not o.stamped and o.status != ALREADY]
        already = [o for o in group if o.status == ALREADY]

        task, date = campaign
        lines.append(f"  {task} — {date} — {len(group)} arm(s)")
        if gradeable:
            contaminated = [o for o in gradeable if o.contaminated]
            git_arms = [o for o in gradeable if o.history_hits]
            git_events = sum(len(o.history_hits) for o in gradeable)
            operator = [
                o for o in gradeable
                if any(e["kind"] == "operator_repo" for e in o.escapes)
            ]
            lines.append(
                f"    contaminated (answer_key): {len(contaminated)}/{len(gradeable)} arms"
            )
            lines.append(
                f"    reached past pinned ref:   {len(git_arms)}/{len(gradeable)} arms"
                f" ({git_events} event(s))"
            )
            lines.append(
                f"    operator repo (other):     {len(operator)}/{len(gradeable)} arms"
            )
        for outcome in refused:
            lines.append(
                f"    REFUSED [{outcome.status}] {outcome.arm}"
                f" — {outcome.detail}"
            )
        if already:
            lines.append(f"    {len(already)} already stamped, left alone")
        lines.append("")

    total_gradeable = [o for o in outcomes if o.stamped]
    total_refused = [o for o in outcomes if not o.stamped and o.status != ALREADY]
    if total_gradeable:
        contaminated = sum(1 for o in total_gradeable if o.contaminated)
        git_arms = sum(1 for o in total_gradeable if o.history_hits)
        git_events = sum(len(o.history_hits) for o in total_gradeable)
        lines.append(
            f"Overall: {contaminated}/{len(total_gradeable)} arms contaminated;"
            f" {git_arms}/{len(total_gradeable)} arms reached past their pinned ref"
            f" ({git_events} event(s))."
        )
    if total_refused:
        lines.append(
            f"{len(total_refused)} record(s) refused a stamp — evidence incomplete,"
            f" NOT clean. They stay unstamped."
        )
    lines.append(
        "\nThe detector reads absolute paths and git subcommands out of transcripts."
        "\nA symlink, a `cd` then a relative path, or a shell variable slips past it,"
        "\nso every rate here is a LOWER BOUND (lab/022)."
    )
    if not wrote:
        lines.append("\nDRY RUN — no record modified. Re-run with --write to stamp.")
    return "\n".join(lines)
