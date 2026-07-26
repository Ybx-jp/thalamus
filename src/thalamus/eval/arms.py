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
        results.append({
            "run": acc.run.strip().splitlines()[0][:80],
            "exit": exit_code,
            "passed": exit_code == acc.expect_exit,
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

        diff = _worktree_diff(worktree)
        record["diff_lines"] = len(diff.splitlines())
        transcript = transcript_text(worktree, agent.session_id)
        record["transcript_captured"] = bool(transcript)
        record["acceptance"] = evaluate_acceptance(task, worktree)
        record["accepted"] = bool(record["acceptance"]) and all(
            a["passed"] for a in record["acceptance"]
        )
        record["probes"] = evaluate_probes(task, transcript, diff, worktree)
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
        mark = "PASS" if acc["passed"] else "FAIL"
        lines.append(f"  acceptance {mark} (exit {acc['exit']}): {acc['run']}")
    verdict = "ACCEPTED" if record.get("accepted") else "NOT ACCEPTED"
    lines.append(f"  => {verdict}")
    for probe in record.get("probes", []):
        mark = "hit " if probe["hit"] else "miss"
        lines.append(f"  probe {mark} [{probe['kind']}] {probe['id']} — {probe['meaning']}")
    return "\n".join(lines)
