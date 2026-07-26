"""The arm runner — layer 2's execution half (docs/04).

One run = one task from the pre-registered battery (eval/tasks.py), one arm, one
disposable git worktree at the task's ref, one headless `claude -p` session, then
the task's own oracles: acceptance commands in the worktree, consequence probes
against the captured transcript and diff. Every run appends one JSONL record to
`~/.thalamus/counterfactuals/runs.jsonl` — the same tap-then-report pattern as
traces, guards, and conditioning.

The arm is applied by editing the *worktree's* harness files, never the repo's:
per-process arming (lab/001) works in the runner's favor — each headless run is a
fresh process that arms from whatever its worktree declares. Before that, the
worktree's copy of the hook *scripts themselves* (not `.claude/settings.json`,
which stays pinned to the task's ref) is synced from the current repo
(`sync_runner_hooks`) — runner-side fixes must reach every worktree regardless
of which historical ref a task is pinned to (lab/012/013) — and the worktree's
own venv is pre-synced with the `dev` extra (`sync_worktree_env`) so `pytest`
exists in it before anyone runs `uv run pytest` (lab/013: it doesn't by
default, so that command silently ran the unrelated system pytest instead).

Two hygiene rules, both measurement-motivated:

- **No arm writes memory.** Distillation (SessionEnd) and the trace taps
  (PostToolUse) are stripped in *every* arm, memory-on included: an arm session
  distilling into the live graph would let later arms recall earlier arms' work
  (cross-arm leakage), and tap lines from never-distilled sessions would sit in
  `eval report` as pending forever. Memory-on means the *read* surface is on.
- **Neutral discipline stays on everywhere.** `timestamp.sh` and
  `gremlin-guard.sh` are not the memory surface; stripping them in one arm would
  confound the contrast.

Known residual, named not hidden: a memory-on arm can still write via the
`memorize` MCP tool, and reads hit the *live* graph — snapshot pinning (the
freshness arm's prerequisite) is not built, which is why `freshness-degraded`
and `volume-degraded` are refused rather than approximated.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thalamus.eval.cost import project_slug
from thalamus.eval.tasks import Task

DEFAULT_MODEL = "sonnet"
DEFAULT_MAX_TURNS = 40
DEFAULT_TIMEOUT = 1800
RUNS_BASE = Path.home() / ".thalamus" / "counterfactuals"

# The scripts that ARE the memory read surface (stripped only in memory-off).
MEMORY_SURFACE_HOOKS = {"session-start.sh", "conditioning.sh", "pin-engaged.sh"}
# Write-back paths stripped in every arm — runs must not write memory.
WRITE_BACK_HOOKS = {"session-end.sh", "post-tool-use.sh", "gremlin-tap.sh"}

UNBUILT_ARMS = ("freshness-degraded", "volume-degraded")


class ArmError(RuntimeError):
    pass


class AuthFault(ArmError):
    """Headless credentials died. Distinct because it must stop the campaign.

    lab/012: an OAuth token expired mid-campaign and the runner cheerfully
    launched the next arm against dead credentials, recording a 1-turn/$0.00
    run that is indistinguishable at a glance from a genuine 1-turn success.
    Every arm after the expiry is void, so the campaign must halt, not
    continue producing records that look like data.
    """


# ---------------------------------------------------------------------------
# Infra-fault classification
# ---------------------------------------------------------------------------
#
# Prior work: CI research separates *legitimate* failures from failures the
# change under test cannot explain — "false alerts" in Fair (arXiv 2111.03382),
# "unrelated build failures" in the Apache PU-learning study (arXiv 2605.05564).
# Two things transfer directly. First, both classify from the **failure
# symptom** (error text, failure properties) rather than by re-running, which
# is exactly the affordance available here — an arm's worktree is destroyed
# after the run, so a rerun would not even be the same experiment. Second, both
# *flag and attribute*; neither deletes the record. A flagged run stays in
# runs.jsonl with its verdict intact and an `attributable: false` stamp beside
# it, because the whole point of docs/04's discipline is that a measurement the
# runner distrusts must be visible, not absent.
#
# Where this instantiation diverges, and why: both papers learn a classifier
# (Fair's ML model, the study's PU learning) because at CI scale the symptoms
# are ambiguous and the label set is huge. Here the fault signatures are few,
# known, and deterministic — each was root-caused by hand in lab/012-013 — and
# a campaign is n=4, so there is nothing to learn from and no rerun budget to
# save. Deterministic symptom matching is the same idea at a different scale,
# not a weaker version of it.

AUTH_FAULT_MARKER = "Failed to authenticate"

# Missing *first-party* submodules are excluded deliberately: a candidate that
# deletes or renames `thalamus/reader.py` genuinely breaks `thalamus.reader`,
# and calling that infra would excuse a real defect. A missing third-party
# distribution — or the top-level `thalamus` package itself, which the worktree
# venv sync installs and no candidate edit can uninstall — is a fault the
# candidate's diff cannot explain (2605.05564's "unrelated to my patch").
_MISSING_MODULE = re.compile(r"No module named ['\"]([\w.]+)['\"]")
_COLLECTION_ERROR = re.compile(r"errors? during collection|INTERNALERROR|"
                               r"ImportError while loading conftest")


def classify_infra_fault(tail: str, exit_code: int | None) -> str | None:
    """Name the infra fault a failure tail betrays, or None if it looks genuine.

    Conservative by construction: an unrecognized failure is reported as a
    candidate defect, which is the pre-existing behavior. Only signatures
    actually observed and root-caused in a campaign are encoded.
    """
    if exit_code == 127:
        return "command_not_found"
    missing = _MISSING_MODULE.findall(tail)
    if missing and not any(m.startswith("thalamus.") for m in missing):
        return "missing_dependency"
    if _COLLECTION_ERROR.search(tail):
        return "collection_error"
    return None


def classify_auth_fault(agent: AgentRun) -> str | None:
    """Distinguish the two auth-expiry shapes lab/012 had to separate by hand.

    An expiry on the *closing* turn leaves a real worktree behind — lab/012
    confirmed from the raw transcript that the candidate's fixtures were
    already passing when the token died, so the oracles run against that state
    are trustworthy and only the model's own summary is lost. An expiry before
    any work leaves nothing: 1 turn, $0.00, ~100ms. Both must stop the
    campaign; only the second voids its own record.
    """
    if AUTH_FAULT_MARKER not in agent.result:
        return None
    if agent.num_turns <= 1 and agent.cost_usd == 0.0:
        return "auth_failed_void"
    return "auth_failed_at_close"


@dataclass
class Arm:
    """A parsed arm spec: `memory-on`, `memory-off`, `scoping-degraded:<scope>`."""

    spec: str
    name: str
    scope: str
    mcp: bool
    strip_hooks: set[str] = field(default_factory=set)


def parse_arm(spec: str, scopes: list[str]) -> Arm:
    if spec == "memory-on":
        return Arm(spec, "memory-on", "main", mcp=True, strip_hooks=set(WRITE_BACK_HOOKS))
    if spec == "memory-off":
        return Arm(
            spec, "memory-off", "main", mcp=False,
            strip_hooks=set(WRITE_BACK_HOOKS) | set(MEMORY_SURFACE_HOOKS),
        )
    if spec.startswith("scoping-degraded:"):
        scope = spec.split(":", 1)[1]
        if scope == "main" or scope not in scopes:
            raise ArmError(
                f"scoping-degraded needs a real non-main expert scope, got `{scope}` "
                f"(available: {', '.join(s for s in scopes if s != 'main') or 'none'})"
            )
        return Arm(
            spec, "scoping-degraded", scope, mcp=True, strip_hooks=set(WRITE_BACK_HOOKS)
        )
    if spec.split(":", 1)[0] in UNBUILT_ARMS:
        raise ArmError(
            f"arm `{spec}` is designed but not built — it needs graph-snapshot "
            "pinning (docs/04 open questions); refusing beats approximating"
        )
    raise ArmError(
        f"unknown arm `{spec}` (memory-on, memory-off, scoping-degraded:<scope>)"
    )


# ---------------------------------------------------------------------------
# Worktree + arm application
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise ArmError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


HOOKS_REL_PATH = Path("src") / "thalamus" / "harness" / "hooks"


def prepare_worktree(repo: Path, ref: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "--detach", str(dest), ref)
    sync_runner_hooks(repo, dest)
    sync_worktree_env(dest)


def sync_worktree_env(worktree: Path, timeout: int = 300) -> None:
    """Pre-sync the worktree's own venv with the `dev` extra before any session runs.

    `pytest` (and pytest-asyncio, ruff, httpx) live under
    `[project.optional-dependencies] dev`, not the base `dependencies` list. A
    worktree's `.venv` is created fresh per run and `uv run <cmd>` only
    auto-syncs base dependencies — so an un-presynced worktree has no `pytest`
    in `.venv/bin/`, and `uv run pytest` silently falls through to PATH,
    finding the unrelated system `python3-pytest` package instead. That
    process can't see anything installed in the worktree's venv, so every
    acceptance run and every candidate-invoked `uv run pytest` fails with
    `ModuleNotFoundError: No module named 'thalamus'` — indistinguishable at a
    glance from a genuine candidate regression (lab/013). The operator's own
    checkout masks this because it was synced with `--extra dev` at some past
    setup step; a disposable worktree never is unless told to be.
    """
    proc = subprocess.run(
        ["uv", "sync", "--extra", "dev"],
        cwd=worktree, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise ArmError(f"uv sync --extra dev failed in worktree: {proc.stderr.strip()[:300]}")


def sync_runner_hooks(repo: Path, worktree: Path) -> None:
    """Overwrite the worktree's harness hook scripts with the current repo's.

    The worktree is checked out at the *task's* ref, which is intentionally
    historical — that's what makes the candidate's fix meaningful to grade. But
    it also freezes the runner's own tooling (session-start.sh's project
    resolution, etc.) at whatever state existed when the task was authored,
    silently reverting any later fix to the harness itself (lab/012/013: the
    THALAMUS_PROJECT fix landed in the repo but never reached a worktree pinned
    to a pre-fix ref). This is eval-runner infrastructure, not candidate code
    under test — `.claude/settings.json` (also worktree-pinned) still decides
    which of these scripts actually fire, so newly added hooks with no wiring
    at the task's ref stay inert; only the *content* of already-wired scripts
    is refreshed.
    """
    src = repo / HOOKS_REL_PATH
    dst = worktree / HOOKS_REL_PATH
    if src.is_dir() and dst.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def remove_worktree(repo: Path, dest: Path) -> None:
    try:
        _git(repo, "worktree", "remove", "--force", str(dest))
    except ArmError:
        shutil.rmtree(dest, ignore_errors=True)
        _git(repo, "worktree", "prune")


def apply_arm(worktree: Path, arm: Arm) -> dict:
    """Edit the worktree's harness files to realize the arm. Returns what changed,
    for the run record — an arm you can't see applied is an arm you can't trust."""
    applied: dict = {"stripped_hooks": [], "mcp_removed": False}

    settings_path = worktree / ".claude" / "settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        for event in list(hooks):
            kept_entries = []
            for entry in hooks[event]:
                kept = []
                for hook in entry.get("hooks", []):
                    script = Path(hook.get("command", "")).name
                    if script in arm.strip_hooks:
                        applied["stripped_hooks"].append(f"{event}:{script}")
                    else:
                        kept.append(hook)
                if kept:
                    kept_entries.append({**entry, "hooks": kept})
            if kept_entries:
                hooks[event] = kept_entries
            else:
                del hooks[event]
        settings_path.write_text(json.dumps(settings, indent=2))

    mcp_path = worktree / ".mcp.json"
    if not arm.mcp and mcp_path.is_file():
        mcp_path.unlink()
        applied["mcp_removed"] = True
    return applied


# ---------------------------------------------------------------------------
# The headless session
# ---------------------------------------------------------------------------


@dataclass
class AgentRun:
    session_id: str
    result: str
    cost_usd: float
    duration_ms: int
    num_turns: int
    is_error: bool


def run_agent(
    worktree: Path,
    prompt: str,
    *,
    scope: str,
    project: str,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout: int = DEFAULT_TIMEOUT,
    full_auto: bool = False,
) -> AgentRun:
    import os

    env = dict(os.environ)
    env["THALAMUS_SCOPE"] = scope
    # session-start.sh resolves project from basename(cwd), which is the repo
    # root in a normal session but the disposable worktree dir here — never a
    # project any session has ever distilled under, so session-start recall
    # silently found nothing in every arm run to date (lab/012). THALAMUS_PROJECT
    # overrides that resolution to the real repo's project.
    env["THALAMUS_PROJECT"] = project
    # The picked agent is the pin (decision log 2026-07-18); a leaked agent name
    # from the operator's own session would override the arm's scope.
    env.pop("CLAUDE_CODE_AGENT", None)

    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--max-turns", str(max_turns)]
    cmd += (
        ["--dangerously-skip-permissions"] if full_auto
        else ["--permission-mode", "acceptEdits"]
    )
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=worktree, env=env,
        )
    except FileNotFoundError as exc:
        raise ArmError("`claude` CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ArmError(f"arm session timed out after {timeout}s") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise ArmError(f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ArmError(f"unparseable claude -p output: {proc.stdout[:200]}") from exc
    return AgentRun(
        session_id=str(envelope.get("session_id", "")),
        result=str(envelope.get("result", "")),
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        duration_ms=int(envelope.get("duration_ms") or 0),
        num_turns=int(envelope.get("num_turns") or 0),
        is_error=bool(envelope.get("is_error")),
    )


def transcript_text(worktree: Path, session_id: str, projects_base: Path | None = None) -> str:
    """The harness transcript of the arm session — the probe/judging capture."""
    base = projects_base or (Path.home() / ".claude" / "projects")
    path = base / project_slug(worktree) / f"{session_id}.jsonl"
    return path.read_text() if path.is_file() else ""


# ---------------------------------------------------------------------------
# Oracles
# ---------------------------------------------------------------------------


def evaluate_acceptance(task: Task, worktree: Path, timeout: int = 900) -> list[dict]:
    results = []
    for acc in task.acceptance:
        try:
            proc = subprocess.run(
                acc.run, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=worktree,
            )
            exit_code: int | None = proc.returncode
            tail = (proc.stdout + proc.stderr)[-400:]
        except subprocess.TimeoutExpired:
            exit_code, tail = None, f"timed out after {timeout}s"
        passed = exit_code == acc.expect_exit
        results.append({
            "run": acc.run.strip().splitlines()[0][:80],
            "exit": exit_code,
            "passed": passed,
            # Only a *failure* can be an infra fault. A passing command that
            # happens to print one of these strings is still a pass.
            "infra_fault": None if passed else classify_infra_fault(tail, exit_code),
            "tail": tail,
        })
    return results


def evaluate_probes(
    task: Task, transcript: str, diff: str, worktree: Path, timeout: int = 300
) -> list[dict]:
    results = []
    for probe in task.probes:
        if probe.kind == "transcript_regex":
            hit = bool(re.search(probe.pattern, transcript))
        elif probe.kind == "diff_regex":
            hit = bool(re.search(probe.pattern, diff))
        else:  # command
            try:
                proc = subprocess.run(
                    probe.run, shell=True, capture_output=True, text=True,
                    timeout=timeout, cwd=worktree,
                )
                hit = proc.returncode == probe.expect_exit
            except subprocess.TimeoutExpired:
                hit = False
        results.append({"id": probe.id, "kind": probe.kind, "hit": hit,
                        "meaning": probe.meaning.strip()})
    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_arm(
    repo: Path,
    task: Task,
    arm: Arm,
    *,
    model: str = DEFAULT_MODEL,
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout: int = DEFAULT_TIMEOUT,
    full_auto: bool = False,
    keep: bool = False,
    runs_base: Path | None = None,
    order_index: int = 0,
) -> dict:
    if not task.source.ref:
        raise ArmError(f"task `{task.id}` has no source.ref to check out")
    base = runs_base or RUNS_BASE
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    worktree = base / "wt" / f"{task.id}--{arm.name}--{stamp}"

    prepare_worktree(repo, task.source.ref, worktree)
    record: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task": task.id,
        "overlap": task.overlap,
        "arm": arm.spec,
        "scope": arm.scope,
        "ref": task.source.ref,
        "model": model,
        "max_turns": max_turns,
        "full_auto": full_auto,
        "order_index": order_index,
        "worktree": str(worktree),
    }
    try:
        record["applied"] = apply_arm(worktree, arm)
        started = time.monotonic()
        agent = run_agent(
            worktree, task.prompt, scope=arm.scope, project=repo.name, model=model,
            max_turns=max_turns, timeout=timeout, full_auto=full_auto,
        )
        record["agent"] = {
            "session_id": agent.session_id,
            "cost_usd": round(agent.cost_usd, 4),
            "duration_ms": agent.duration_ms,
            "num_turns": agent.num_turns,
            "is_error": agent.is_error,
            "result_tail": agent.result[-300:],
        }
        # Censoring, stamped not inferred: a capped session never concluded, so
        # its iteration metrics are lower bounds (lab/011: the cap bound in 4/4
        # first-campaign runs).
        record["turn_capped"] = agent.num_turns > max_turns
        record["wall_seconds"] = round(time.monotonic() - started, 1)

        # `is_error` alone is NOT an auth signal — every turn-capped run in
        # runs.jsonl carries it too. The result string is the discriminator.
        auth_fault = classify_auth_fault(agent)
        if auth_fault == "auth_failed_void":
            # No candidate work happened; grading an untouched worktree would
            # manufacture a verdict out of nothing.
            record["infra_fault"] = auth_fault
            record["attributable"] = False
            record["void"] = True
            raise AuthFault(
                f"{task.id} · {arm.spec}: headless auth died before any work "
                "(1 turn, $0.00) — record stamped void, campaign stopped"
            )

        diff = _worktree_diff(worktree)
        record["diff_lines"] = len(diff.splitlines())
        transcript = transcript_text(worktree, agent.session_id)
        record["transcript_captured"] = bool(transcript)
        record["acceptance"] = evaluate_acceptance(task, worktree)
        record["accepted"] = bool(record["acceptance"]) and all(
            a["passed"] for a in record["acceptance"]
        )
        record["probes"] = evaluate_probes(task, transcript, diff, worktree)

        # Flag, never exclude (arXiv 2111.03382, 2605.05564): the verdict above
        # stays exactly as measured; `attributable` says whether it can be read
        # as a fact about the *candidate*. lab/013 lost a whole task-pair to a
        # `uv run pytest` failure that rendered identically to a real
        # regression, so this distinction has to live in the record itself.
        faults = sorted({
            a["infra_fault"] for a in record["acceptance"] if a["infra_fault"]
        })
        if auth_fault:
            # Oracles still ran and are trustworthy here (lab/012 verified the
            # worktree state against the raw transcript) — only the model's
            # closing summary was lost. The stamp records the caveat; the
            # campaign still stops, below.
            faults.append(auth_fault)
        record["infra_faults"] = faults
        record["attributable"] = not faults
        if auth_fault:
            raise AuthFault(
                f"{task.id} · {arm.spec}: headless auth died on the closing "
                f"turn after {agent.num_turns} turns — this record's oracles "
                "are trustworthy, but the campaign is stopped"
            )
    finally:
        record["kept"] = keep
        if not keep:
            remove_worktree(repo, worktree)
        base.mkdir(parents=True, exist_ok=True)
        with (base / "runs.jsonl").open("a") as fh:
            fh.write(json.dumps(record) + "\n")
    return record


def _worktree_diff(worktree: Path) -> str:
    """Tracked changes plus the names of anything untracked the session left."""
    diff = _git(worktree, "diff")
    status = _git(worktree, "status", "--porcelain")
    untracked = [line[3:] for line in status.splitlines() if line.startswith("??")]
    if untracked:
        diff += "\n" + "\n".join(f"untracked: {name}" for name in untracked)
    return diff


# Two things genuinely differ between arms of the same pair and must be
# normalized away before comparing failure shapes: the worktree path (it
# carries the arm name and a timestamp) and pytest's duration line. Nothing
# else — blanket digit-stripping would collapse `assert 0 == 3` and
# `assert 1 == 3` into the same shape, erasing the very signal that tells two
# candidates' failures apart.
_VOLATILE_PATH = re.compile(r"(?:/[\w.\-]+)+/?")
_VOLATILE_DURATION = re.compile(r"\d+\.\d+s\b")


def _normalize_tail(tail: str) -> str:
    """Collapse a failure tail to its shape, so two arms' failures can be compared."""
    shape = _VOLATILE_PATH.sub("PATH", tail)
    shape = _VOLATILE_DURATION.sub("Ns", shape)
    return re.sub(r"\s+", " ", shape).strip()


def render_campaign_faults(records: list[dict]) -> str:
    """Cross-arm fault signals — what a single record cannot see.

    Grounded in the Apache study's finding that *repeated error messages* are
    among the strongest features for identifying failures unrelated to the
    change under test (arXiv 2605.05564). The arm-pair gives a sharper version
    of that signal than CI has: two arms are two different candidate sessions
    writing different code against the same ref, so a failure that reproduces
    **identically in every arm** is very unlikely to be about the candidates.
    lab/013's reader pair was exactly this — the same
    `ModuleNotFoundError: No module named 'gremlin_python'` in both arms — and
    it was written up as a candidate defect for a day before being caught by
    hand.

    Suggestive, never conclusive, and reported as such: a task whose arms all
    fail the same genuine way (a fix nobody found) looks the same from here.
    """
    graded = [r for r in records if r.get("acceptance") and not r.get("void")]
    if len(graded) < 2:
        return ""
    lines = []
    for i, acc in enumerate(graded[0]["acceptance"]):
        failed_everywhere = all(
            len(r["acceptance"]) > i and not r["acceptance"][i]["passed"]
            for r in graded
        )
        if not failed_everywhere:
            continue
        shapes = {_normalize_tail(r["acceptance"][i]["tail"]) for r in graded}
        if len(shapes) == 1:
            lines.append(
                f"  `{acc['run']}` failed identically in all {len(graded)} arms "
                "— failures that reproduce across arms are usually the harness, "
                "not the candidates (arXiv 2605.05564). Check before reading "
                "this task's acceptance column as a result."
            )
    if not lines:
        return ""
    return "CROSS-ARM FAULT SIGNAL\n" + "\n".join(lines)


def render_run(record: dict) -> str:
    agent = record.get("agent", {})
    lines = [
        f"{record['task']} · {record['arm']} (scope {record['scope']}, "
        f"ref {record['ref']}, order {record['order_index']})",
        f"  session {agent.get('session_id', '?')} — {agent.get('num_turns', '?')} turns"
        + (" (CAPPED)" if record.get("turn_capped") else "")
        + f", ${agent.get('cost_usd', 0):.2f}, {record.get('wall_seconds', '?')}s wall, "
        f"{record.get('diff_lines', 0)} diff lines"
        + (", transcript MISSING" if not record.get("transcript_captured") else ""),
        f"  applied: mcp_removed={record.get('applied', {}).get('mcp_removed')}, "
        f"stripped={len(record.get('applied', {}).get('stripped_hooks', []))} hook(s)",
    ]
    for acc in record.get("acceptance", []):
        if acc["passed"]:
            mark = "PASS"
        elif acc.get("infra_fault"):
            mark = f"INFRA-FAULT[{acc['infra_fault']}]"
        else:
            mark = "FAIL"
        lines.append(f"  acceptance {mark} (exit {acc['exit']}): {acc['run']}")
    if record.get("void"):
        # No oracle ran, so "NOT ACCEPTED" would invent a verdict.
        lines.append(f"  => VOID ({record.get('infra_fault')}) — no candidate work, not graded")
        return "\n".join(lines)
    verdict = "ACCEPTED" if record.get("accepted") else "NOT ACCEPTED"
    if record.get("infra_faults"):
        # Loud on purpose: the failure mode this guards against is an infra
        # fault read as a candidate defect (lab/013).
        verdict += (
            f" — INFRA FAULT ({', '.join(record['infra_faults'])}), "
            "NOT attributable to the candidate"
        )
    lines.append(f"  => {verdict}")
    for probe in record.get("probes", []):
        mark = "hit " if probe["hit"] else "miss"
        lines.append(f"  probe {mark} [{probe['kind']}] {probe['id']} — {probe['meaning']}")
    return "\n".join(lines)
