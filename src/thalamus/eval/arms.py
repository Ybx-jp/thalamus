"""The arm runner — layer 2's execution half (docs/04).

One run = one task from the pre-registered battery (eval/tasks.py), one arm, one
disposable git worktree at the task's ref, one headless coding-agent session, then
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

The session binary comes from `harness/agents.py` like every other headless
invocation, but arms are the one surface that is **not** harness-agnostic: they
need staged credentials, turn limits, permission flags, an envelope reporting
turns and cost, and a transcript the escape detectors and fault classifier can
read. `agent_cli()` refuses a harness that lacks those, itemised, rather than
substituting a binary and emitting records that read as measurements.

Known residual, named not hidden: a memory-on arm can still write via the
`memorize` MCP tool, and reads hit the *live* graph — snapshot pinning (the
freshness arm's prerequisite) is not built, which is why `freshness-degraded`
and `volume-degraded` are refused rather than approximated.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from thalamus.eval.cost import project_slug
from thalamus.harness.agents import cli_for as _cli_for
from thalamus.eval.tasks import Task

DEFAULT_MODEL = _cli_for("claude").default_model
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


def agent_cli(harness: str):
    """The CLI for this harness, or a refusal naming what is still Claude-Code-only.

    Arms need far more from a harness than a binary that takes `-p`: staged
    credentials, turn limits, permission flags, a run envelope that reports turns
    and cost, and a transcript the escape detectors and fault classifier can read.
    Swapping the binary alone would produce arms that run and report success while
    measuring nothing — records that look like data and are not, which is the
    failure lab/016 and lab/022 are both about. So the gaps are enumerated on the
    registry entry (harness/agents.py) and refused here by name.
    """
    try:
        cli = _cli_for(harness)
    except ValueError as exc:
        raise ArmError(str(exc)) from None
    if not cli.runs_arms:
        blockers = "\n".join(f"  - {b}" for b in cli.arm_blockers)
        raise ArmError(
            f"eval arms cannot run under `{harness}` yet. Still Claude-Code-only:\n"
            f"{blockers}\n"
            "Extraction and ingestion are harness-agnostic; arms are not, and a "
            "partial port would emit records that read as measurements."
        )
    return cli


class SessionFault(ArmError):
    """The headless session died for a reason outside the experiment.

    Credentials expiring (lab/012), a usage/session limit landing mid-campaign
    (lab/016) — the cause differs, the consequence does not: this arm's result
    is not about the candidate, and every arm after it will hit the same wall.
    The campaign must halt rather than keep emitting records that read as data.

    lab/016 is why this is not called AuthFault any more. The first version
    matched exactly the one string lab/012 happened to observe
    ("Failed to authenticate"), so `You've hit your session limit` walked
    straight past it: 16 arms were recorded as $0.00 candidate *failures* and
    two more, killed at turns 11 and 18 of 40, were stamped
    `attributable: true, accepted: false` — a trustworthy-looking candidate
    defect that was nothing of the kind. Match the failure class, never one
    vendor's phrasing.
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

# Markers that mean the *session* died, not the candidate's attempt. Kept as a
# class of failures rather than a single string — see SessionFault.
SESSION_FAULT_MARKERS = (
    "failed to authenticate",
    "not logged in",
    "session limit",
    "usage limit",
    "rate limit",
    "quota",
)

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


def classify_session_fault(agent: AgentRun) -> str | None:
    """Name how a dead session died, or None if it died of nothing.

    Two shapes only:

    - `void` — nothing happened (1 turn, $0.00). Grading an untouched worktree
      would manufacture a verdict out of thin air.
    - `interrupted` — real work, then the session died. The worktree holds an
      attempt of *unknown completeness*, so any verdict against it is a
      statement about the interruption, not about the candidate.

    Both stop the campaign and neither is graded.

    There is deliberately no `at_close` shape, tempting as it is: lab/012 did
    establish that one arm's token died only after its fixtures were already
    passing, so its oracles were trustworthy — but that was established by
    *reading the raw transcript*, and it was 33 turns into a 40-turn budget.
    No cheap signal separates it from lab/016's fable arms, cut off at turns 11
    and 18 of the same budget. A runner that guessed would sometimes stamp a
    half-finished attempt as a trustworthy verdict, which is the exact failure
    this whole classifier exists to prevent. When an interrupted arm matters,
    read its transcript and say so by hand.
    """
    # `is_error` is NECESSARY but not sufficient, and the order matters. A run
    # that concluded normally is not a dead session no matter what its prose
    # says — and its prose is the model's own summary, which on a task *about*
    # session limits necessarily contains these very markers. lab/020 lost a
    # campaign to exactly that: a healthy 49-turn arm reported that it had
    # broadened the marker list to cover session/usage/rate/quota, the runner
    # read its own vocabulary back out of that sentence, stamped the arm void
    # and halted. The same error class as lab/016 — matching a string instead of
    # a failure — inverted: the right string, in the wrong place.
    #
    # Necessity is checked against the whole record: every genuine death in
    # runs.jsonl (18 void arms, 22 marker-bearing arms) carries `is_error`, and
    # the only `is_error: False` fault ever stamped was that false positive.
    # `is_error` still cannot stand alone — every turn-capped run carries it too
    # — so the marker remains the discriminator *among errored runs*.
    if not agent.is_error:
        return None
    # `void` is decided on *behavior*, before any marker is consulted. An
    # errored session that took no turn and spent nothing did nothing, whatever
    # string it printed on the way out, and the marker list cannot enumerate
    # every way a session fails to start. The first confined arm proved the
    # gap: it died with "Not logged in · Please run /login" — an auth failure
    # by any reading, but not the phrase `failed to authenticate` — so the
    # marker gate returned None and an untouched worktree was graded RUNG 1,
    # the exact verdict-from-thin-air this classifier exists to prevent
    # (lab/016: matching a string instead of a failure).
    #
    # This cannot resurrect lab/020's false positive. That arm ran 49 turns and
    # spent real money; the conjunction below is unreachable for any session
    # that did work, so the marker gate is still what guards the *interrupted*
    # shape, which is the only one a healthy arm's prose can be confused with.
    if agent.num_turns <= 1 and agent.cost_usd == 0.0:
        return "session_fault_void"
    text = (agent.result or "").lower()
    if not any(marker in text for marker in SESSION_FAULT_MARKERS):
        return None
    return "session_fault_interrupted"


@dataclass
class Arm:
    """A parsed arm spec: `memory-on`, `memory-off`, `scoping-degraded:<scope>`, `ceiling`."""

    spec: str
    name: str
    scope: str
    mcp: bool
    strip_hooks: set[str] = field(default_factory=set)
    # `ceiling` only: the task's withheld fact is handed to the candidate directly,
    # so the arm measures what a *perfect* retrieval would be worth.
    inject_fact: bool = False


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
    if spec == "ceiling":
        # The skyline. Same stripped harness as memory-off — no MCP, no memory
        # surface — but the task's withheld fact is injected into the prompt, so
        # retrieval is not merely good, it is perfect and free.
        #
        # It answers the question that gates every other arm: if a candidate handed
        # exactly the right memory, with no retrieval to get wrong, does not beat one
        # with no memory at all, then no retrieval improvement can move this battery
        # and the layer-2 program is measuring the battery rather than the memory.
        #
        # Labelled "not found in the 2026 scan" rather than standard practice: two
        # literature scans found no held claims on oracle-context or skyline arms
        # (`scope:eval-methodology:thread:ceiling-arm-and-survival-analysis-ungrounded`).
        return Arm(
            spec, "ceiling", "main", mcp=False,
            strip_hooks=set(WRITE_BACK_HOOKS) | set(MEMORY_SURFACE_HOOKS),
            inject_fact=True,
        )
    if spec.split(":", 1)[0] in UNBUILT_ARMS:
        raise ArmError(
            f"arm `{spec}` is designed but not built — it needs graph-snapshot "
            "pinning (docs/04 open questions); refusing beats approximating"
        )
    raise ArmError(
        f"unknown arm `{spec}` (memory-on, memory-off, ceiling, scoping-degraded:<scope>)"
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
    """Build the arm's checkout as a repository whose history *stops* at `ref`.

    This was `git worktree add` until the leak was measured. A worktree shares
    refs and the object store with the operator's repo, so an arm could read its
    own answer without ever naming a path outside its own directory: 9 of 88
    recorded arms ran history commands reaching past their pinned ref, including
    `git show <fix_ref>` on the task's own fix and one
    `git grep -l "<task-id>" $(git rev-list --all)` — a deliberate sweep of every
    commit for the task's name. Filesystem confinement cannot close that, because
    the object store is exactly what git needs to function.

    So the arm gets a private repo containing one commit and nothing else. The
    fetch names the **full** 40-char SHA (an abbreviation is not a fetchable ref)
    and enables `allowAnySHA1InWant` on the *remote* side of the transport, so an
    unadvertised commit can be fetched without creating a temp branch or leaving
    any config behind in the operator's repo.

    `--depth=1` is what removes the history; `pin_pre_existing_suite` still works
    because it resolves `source.ref`, which is the very commit fetched.

    The initial environment state is part of the instrument's definition rather
    than scaffolding around it — τ-bench grades against an annotated end state
    and pass^k presupposes an identical start state across trials, neither of
    which a shared object store delivers (literature consultation
    `scope:main:exchange:3f47831f43f2447b`).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    full = _git(repo, "rev-parse", ref).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", full):
        raise ArmError(f"could not resolve `{ref}` to a full object name (got {full!r})")
    _git(dest, "init", "-q")
    _git(
        dest, "fetch", "-q", "--depth=1",
        "--upload-pack", "git -c uploadpack.allowAnySHA1InWant=true upload-pack",
        f"file://{repo}", full,
    )
    _git(dest, "checkout", "-q", "--detach", full)
    sync_runner_hooks(repo, dest)
    sync_worktree_env(dest)


def refuse_self_leaking_task(repo: Path, ref: str, task_id: str) -> None:
    """Refuse a task whose own battery file exists at its `source.ref`.

    Ref-limiting removes *future* leakage; it cannot remove *contemporaneous*
    leakage. A task authored before the commit it replays ships its own answer
    key — prompt, every relation with its literals, and the withheld fact in
    prose — inside the checkout the candidate is handed.

    Deleting the battery from the checkout was tried first and is wrong: the
    pinned suite carries `test_the_shipped_battery_validates`, which asserts the
    battery holds at least two tasks, so stripping it fails L1 for *every*
    candidate. That is lab/019's ungradeable-design defect in a new place — the
    no-regression gate is not a place to hide a harness edit.

    So the check is structural and refuses rather than patches, on the same
    ground as the unbuilt arms: a task that leaks to itself is unsound by
    construction, and no runtime fixup makes the measurement mean what it
    claims. All three shipped tasks pass (their battery files postdate their
    refs); this keeps the next one honest.

    Not covered, and named rather than fixed: *sibling* task files present at a
    ref (both original tasks are readable at `1fc6aef`). Those do not give away
    the arm's own answer, but they do reveal how arms are graded in general.
    Low severity while probes stay unscored, and it becomes real the moment any
    rung depends on a battery-visible literal.
    """
    path = f"config/tasks/{task_id}.yaml"
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    if probe.returncode == 0:
        raise ArmError(
            f"task `{task_id}` ships its own answer key: `{path}` already exists "
            f"at `{ref}`, so the candidate's checkout contains the "
            "pre-registration. Re-author the task against an earlier ref — "
            "refusing beats grading a candidate that can read the oracle."
        )


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
    """Drop the arm's checkout.

    A plain rmtree since `prepare_worktree` stopped registering worktrees in the
    operator's repo. The `git worktree remove` + `prune` fallback is kept for
    checkouts left behind by campaigns that ran before that change — they are
    still registered, and pruning them is how the operator's repo forgets them.
    """
    shutil.rmtree(dest, ignore_errors=True)
    try:
        _git(repo, "worktree", "prune")
    except ArmError:
        pass


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


ARM_IMAGE = "thalamus-arm:latest"
ARM_DOCKER_CONTEXT = "default"
DOCKERFILE_REL = Path("docker") / "arm-runner.Dockerfile"


def arm_home_for(worktree: Path) -> Path:
    """The private HOME a confined arm runs under.

    Derived from the worktree rather than passed around, because two callers must
    agree on it from different places: `run_agent` mounts it as the container's
    HOME, and `transcript_text` reads the session transcript back out of it. When
    they disagreed the read returned "" rather than raising, so a sandboxed arm
    recorded `transcript_captured: false`, `recall_calls` {0, 0}, every probe a
    miss and no escapes — an arm that recalled memory perfectly, filed as one that
    never reached for it.

    Confinement exists for *gated* campaigns, where recall behaviour is the
    primary outcome (lab/020's C2), so the drift would have zeroed exactly the
    measurement the campaign was bought to make, in the arm where it matters most,
    while every other field in the record looked normal. Same class as the
    `basename $cwd` scoping bug (lab/012) and the `turn_capped` comparison
    (lab/015): a default that returns a plausible value instead of failing.
    """
    return worktree.parent / f"{worktree.name}--home"


def docker_available(image: str = ARM_IMAGE) -> bool:
    """Whether the confinement image is built on the daemon the arms will use."""
    probe = subprocess.run(
        ["docker", "--context", ARM_DOCKER_CONTEXT, "image", "inspect", image],
        capture_output=True, text=True,
    )
    return probe.returncode == 0


# Commands the *retained* hooks need. Every Thalamus hook parses its stdin
# payload with `jq` under `set -euo pipefail`, so an image without it runs a
# session whose whole hook layer is dead.
HOOK_DEPENDENCIES = ("jq",)

_hook_dep_cache: dict[str, tuple[str, ...]] = {}


def image_missing_hook_deps(image: str = ARM_IMAGE) -> tuple[str, ...]:
    """Hook dependencies absent from the confinement image.

    The failure this exists to prevent is silent by construction. A
    SessionStart hook that aborts does not stop the session — it just does not
    inject. The first confined arm ran with no `jq`, so `session-start.sh` died
    on its first line, the memory-priming context was never delivered, and the
    arm recorded `recall_calls: 0`. That record is indistinguishable from a
    candidate that was told to recall and declined, which is the reading it
    would have got: a memory-on arm filed as evidence about memory when the
    memory surface had never been announced to it.

    It also breaks an invariant the campaign design depends on — docs/index
    2026-07-19 keeps the neutral discipline on in *every* arm precisely so it
    cannot confound the contrast, and hooks that do not run are not on.
    """
    if image in _hook_dep_cache:
        return _hook_dep_cache[image]
    probe = subprocess.run(
        ["docker", "--context", ARM_DOCKER_CONTEXT, "run", "--rm", image,
         "sh", "-c", " ".join(f"command -v {dep} >/dev/null || echo {dep};"
                              for dep in HOOK_DEPENDENCIES)],
        capture_output=True, text=True,
    )
    missing = tuple(line.strip() for line in probe.stdout.splitlines() if line.strip())
    _hook_dep_cache[image] = missing
    return missing


def sandbox_argv(
    worktree: Path,
    home: Path,
    *,
    image: str = ARM_IMAGE,
    network: str = "host",
    claude_bin: Path | None = None,
    uv_bin: Path | None = None,
) -> list[str]:
    """The `docker run` prefix that confines one arm.

    What the confinement is *for*: the arm's checkout is mounted and the
    operator's repo is not, so `/home/<user>/code/thalamus` does not exist inside
    the container and the absolute-path reads measured in lab/020 resolve to
    nothing. Combined with `prepare_worktree`'s one-commit repo, both measured
    leak channels are closed — filesystem and git object store.

    `network` is the one-flag difference between arms and carries a second
    result. `host` lets a memory-on arm reach the graph at
    `ws://localhost:8182/gremlin`, which is the treatment. `bridge` gives
    memory-off the **store isolation** docs/04 has carried as an open question
    since the first campaign, where a memory-off session was measured querying
    the graph over ad-hoc gremlin: removing the surface never removed the store,
    and this does.

    `bridge` rather than `none`, and the distinction is not cosmetic. `none`
    isolates the store *and* the model API, so the arm dies on its first turn
    (`Unable to connect to API (ENOTIMP)`) and halts the campaign — measured,
    on the first attempt to run this design. From `bridge` the graph is
    unreachable on `localhost:8182`, which is the container's own loopback, and
    also on the gateway `172.17.0.1:8182`, because the graph server binds
    loopback-only; `api.anthropic.com` answers. Probed at the TCP layer, since
    HTTP status codes say nothing useful about a websocket port.

    The toolchain is mounted read-only from the host rather than baked, so the
    arm runs the operator's own `claude` and `uv` builds and the image cannot
    drift from them.
    """
    claude = claude_bin or Path.home() / ".local" / "bin" / "claude"
    uv = uv_bin or Path(shutil.which("uv") or "/usr/bin/uv")
    argv = [
        # The native daemon, explicitly. Docker Desktop is the default context on
        # this box and is the wrong runtime here: it runs containers inside a VM,
        # so bind mounts are restricted to configured shares and `--network host`
        # is the VM's host, not the operator's — a memory-on arm could not reach
        # `ws://localhost:8182/gremlin` at all. Measured both ways before pinning.
        "docker", "--context", ARM_DOCKER_CONTEXT, "run", "--rm", "-i",
        "--network", network,
        f"--user={os.getuid()}:{os.getgid()}",
        # The arm's own checkout, read-write: this is the thing under test.
        "-v", f"{worktree}:{worktree}",
        # A private HOME. Transcripts land in <home>/.claude/projects/... where
        # `transcript_text` reads them, so probes and recall counts survive
        # confinement.
        "-v", f"{home}:{home}",
        # Toolchain, read-only.
        "-v", f"{claude.parent.parent}:{claude.parent.parent}:ro",
        "-v", f"{uv}:{uv}:ro",
        "-e", f"HOME={home}",
        # The mounted toolchain is outside the image's PATH by construction.
        "-e", f"PATH={claude.parent}:{uv.parent}:/usr/local/bin:/usr/bin:/bin",
        "-w", str(worktree),
        image,
    ]
    return argv


def run_agent(
    worktree: Path,
    prompt: str,
    *,
    scope: str,
    project: str,
    model: str | None = None,
    harness: str = "claude",
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout: int = DEFAULT_TIMEOUT,
    full_auto: bool = False,
    sandbox: bool = False,
    network: str = "host",
    home: Path | None = None,
) -> AgentRun:
    cli = agent_cli(harness)
    model = model or cli.default_model
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

    cli = agent_cli(harness)
    cmd = [cli.binary, "-p", "--model", model, "--output-format", "json",
           "--max-turns", str(max_turns)]
    cmd += (
        ["--dangerously-skip-permissions"] if full_auto
        else ["--permission-mode", "acceptEdits"]
    )
    if sandbox:
        # Confinement is refused rather than approximated when the image is
        # absent: silently running unconfined would produce records that look
        # like every other record and are not (the lab/016 lesson about guards
        # that are correct about the case in front of them).
        if not docker_available():
            raise ArmError(
                f"sandboxed arm requested but image `{ARM_IMAGE}` is not built on "
                f"the `{ARM_DOCKER_CONTEXT}` docker context. Build it with:\n"
                f"  docker --context {ARM_DOCKER_CONTEXT} build "
                f"-f {DOCKERFILE_REL} -t {ARM_IMAGE} "
                "--build-arg UID=$(id -u) --build-arg GID=$(id -g) .\n"
                "The `--context` is not optional: Docker Desktop is the default "
                "context on this box, and a build there is invisible to the "
                "daemon the arms use."
            )
        missing = image_missing_hook_deps()
        if missing:
            raise ArmError(
                f"image `{ARM_IMAGE}` is missing {', '.join(missing)}, which the "
                "retained hooks need. They would fail silently and the arm would "
                "record a dead hook layer as candidate behaviour (no memory "
                f"priming, `recall_calls: 0`). Rebuild:\n"
                f"  docker --context {ARM_DOCKER_CONTEXT} build "
                f"-f {DOCKERFILE_REL} -t {ARM_IMAGE} "
                "--build-arg UID=$(id -u) --build-arg GID=$(id -g) ."
            )
        arm_home = home or arm_home_for(worktree)
        (arm_home / ".claude").mkdir(parents=True, exist_ok=True)
        # The two files the CLI needs, and nothing else from the operator's
        # HOME. They are not interchangeable and the split is the whole reason
        # the first confined arm died: `.claude.json` is config and state (it
        # carries `oauthAccount` *metadata*), while the OAuth token itself
        # lives in `.claude/.credentials.json`. Copying only the former yields
        # a session that starts, reports "Not logged in · Please run /login",
        # and exits in ~70ms.
        host_config = Path.home() / ".claude.json"
        if host_config.is_file():
            shutil.copy2(host_config, arm_home / ".claude.json")
        # Refused before launch rather than discovered inside the container: a
        # missing token costs a prepared worktree and produces an `attributable`
        # record that says nothing about the candidate. The runner knows the
        # answer here before it spends anything, so it says so.
        host_creds = Path.home() / ".claude" / ".credentials.json"
        if not host_creds.is_file():
            raise ArmError(
                f"sandboxed arm requested but no credentials at {host_creds}. "
                "The container gets its own HOME, so it cannot reach the "
                "operator's login — run `claude` and `/login` on the host "
                "first, then re-run the campaign."
            )
        # copy2 preserves the source's 0600; the arm HOME is the operator's own
        # directory, but the token should not widen on the way in.
        arm_creds = arm_home / ".claude" / ".credentials.json"
        shutil.copy2(host_creds, arm_creds)
        arm_creds.chmod(0o600)
        # HOME is deliberately NOT reassigned here. This process is the *docker
        # client*, which resolves its context and daemon config out of the
        # operator's own HOME — repointing it makes the CLI look up a context
        # that does not exist and fail with a misleading "image not found,
        # pull access denied". The container's HOME is set inside the container,
        # by `-e HOME=` in `sandbox_argv`.
        cmd = sandbox_argv(worktree, arm_home, network=network) + cmd
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            timeout=timeout, cwd=worktree, env=env,
        )
    except FileNotFoundError as exc:
        raise ArmError(f"`{cli.binary}` CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ArmError(f"arm session timed out after {timeout}s") from exc
    if proc.returncode != 0 and not proc.stdout.strip():
        raise ArmError(
            f"{cli.binary} -p exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ArmError(
            f"unparseable {cli.binary} -p output: {proc.stdout[:200]}"
        ) from exc
    return AgentRun(
        session_id=str(envelope.get("session_id", "")),
        result=str(envelope.get("result", "")),
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        duration_ms=int(envelope.get("duration_ms") or 0),
        num_turns=int(envelope.get("num_turns") or 0),
        is_error=bool(envelope.get("is_error")),
    )


def count_recall_calls(transcript: str) -> dict:
    """Count the arm's memory-surface tool calls, from its own transcript.

    `thalamus` is every `mcp__thalamus__*` call — the thing memory-on is
    supposed to make possible. `tool_search` is the deferred-schema load that
    must precede it in this harness (lab/013-014); recording it separately is
    what distinguishes "never tried" from "tried and could not".
    """
    counts = {"thalamus": 0, "tool_search": 0}
    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            if name.startswith("mcp__thalamus__"):
                counts["thalamus"] += 1
            elif name == "ToolSearch":
                counts["tool_search"] += 1
    return counts


# The battery files ARE the answer key: each states its withheld fact in prose
# (`under_specification.fact`) and carries every relation with its exact literals.
ANSWER_KEY_DIRS = ("config/tasks",)


def fix_touched_paths(repo: Path, source_ref: str, fix_ref: str) -> frozenset[str]:
    """The files the historical fix changed — the answer key in code form.

    Found by validating the escape detector against lab/020's own arms: the two
    the write-up caught had read the task *file*, but a third had run the live
    `src/thalamus/eval/arms.py`, which at HEAD already carries the very fix the
    task asks the candidate to write. A directory list would have filed that as
    the weaker `operator_repo` class. Which files give the answer away is a
    property of the task, so it is derived from the task rather than declared.

    An `authored` task has no `fix_ref` and no such set.
    """
    if not fix_ref or not source_ref:
        return frozenset()
    try:
        out = _git(repo, "diff", "--name-only", f"{source_ref}..{fix_ref}")
    except ArmError:
        return frozenset()
    return frozenset(p.strip() for p in out.splitlines() if p.strip())


def detect_worktree_escape(
    transcript: str,
    worktree: Path,
    repo: Path,
    fix_paths: frozenset[str] | set[str] = frozenset(),
) -> list[dict]:
    """Find reads of the operator's live checkout from inside an arm session.

    A campaign arm runs `--full-auto` (`--dangerously-skip-permissions`) and
    nothing confines it to its worktree. lab/020 measured the consequence: two
    memory-off arms ran `ls config/tasks/` and then read the task file by
    absolute path, outside the worktree entirely. That file states the withheld
    constraint in prose and lists every relation with its marker strings and
    turn counts — both arms then scored at or above the memory-off ceiling the
    gate had pre-registered for them, and one of the two carried `memo-surfaced`
    on a session UUID it had read out of the file rather than recalled.

    That was caught by reading transcripts. A validity threat found by hand is
    one that gets missed on the run nobody reads, so it is mechanised here on
    the discipline the infra classifier already follows (arXiv 2111.03382,
    2605.05564): **flag, never exclude**. The rung stands exactly as measured.

    Two classes, because they are not equally disqualifying:

    - `answer_key` — a battery file, or a file the task's own `fix_ref` changed
      (`fix_paths`). The candidate could have read the answer, in prose or in
      code, so the run says nothing about an *unaided* one.
    - `operator_repo` — any other escape into the live checkout. Not the answer,
      but not the experiment either: that tree carries the fix commit and every
      lab entry describing it, both reachable from `source.ref`'s own history.

    Deliberately separate from `attributable`. An infra fault means the verdict
    is not about the candidate at all; contamination means it is about the
    candidate but not about an unaided one. Collapsing them would lose the
    distinction that makes either useful.
    """
    repo_s, worktree_s = str(repo.resolve()), str(worktree.resolve())
    # A worktree normally lives outside the repo (under RUNS_BASE), so any
    # mention of the repo path is already an escape — but the check is explicit
    # so that relocating worktrees inside the repo cannot silently flip it.
    pattern = re.compile(re.escape(repo_s) + r"[\w./\-]*")
    escapes: list[dict] = []
    seen: set[tuple] = set()
    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            blob = json.dumps(block.get("input") or {})
            for hit in pattern.findall(blob):
                if hit.startswith(worktree_s):
                    continue
                rel = hit[len(repo_s):].lstrip("/")
                gives_answer = rel.startswith(ANSWER_KEY_DIRS) or rel in fix_paths
                kind = "answer_key" if gives_answer else "operator_repo"
                key = (name, rel, kind)
                if key in seen:
                    continue
                seen.add(key)
                escapes.append({"tool": name, "path": rel, "kind": kind})
    return escapes


# Git invocations that reach outside the commit the arm was pinned to. Ordered
# most-specific first; the first match names the reach.
_GIT_REACH = (
    (re.compile(r"\bgit\b[^|;&\n]*\brev-list\b[^|;&\n]*--all"), "rev-list --all"),
    (re.compile(r"\bgit\b[^|;&\n]*\blog\b[^|;&\n]*\ball\b"), "log --all"),
    (re.compile(r"\bgit\b[^|;&\n]*\b(?:show|diff|checkout|grep)\s+([0-9a-f]{7,40})\b"),
     "show/diff <sha>"),
    (re.compile(r"\bgit\b[^|;&\n]*\b(?:origin/\w+|master|main)\b"), "named branch"),
    (re.compile(r"\bgit\b[^|;&\n]*\bHEAD~\d+"), "HEAD~n"),
    (re.compile(r"\bgit\b[^|;&\n]*--all\b"), "--all"),
)


def detect_history_reach(
    transcript: str, source_ref: str = "", fix_ref: str = ""
) -> list[dict]:
    """Find git commands that reached past the arm's pinned commit.

    The leak nobody was watching. A `git worktree` shares refs and the object
    store with the operator's repo, so an arm could read the fix, every lab entry
    describing it, and the task YAML itself **without naming a path outside its
    own directory** — invisible to `detect_worktree_escape`, and un-closable by
    filesystem confinement, since the object store is what git needs to run.

    Measured across the recorded campaigns: 9 arms, including
    `git grep -l "<task-id>" $(git rev-list --all)` — a sweep of every commit for
    the task's own name — and a `git show <fix_ref> -- tests/test_reader.py`
    against the reader task's own fix.

    `prepare_worktree` now closes the channel, which is exactly why this detector
    has to exist: an arm reaching for `git log --all` behaves differently from one
    that does not, and that difference is data about the candidate. Denying the
    read silently would convert a measured behavior into an absence. Execution
    provenance treats environmental interaction as a first-class step type
    (literature consultation `scope:main:exchange:3f47831f43f2447b`), so the
    design is **deny at the environment, measure at the transcript**: the attempt
    stays in the record and keeps the rate observable after the fix.
    """
    fix = (fix_ref or "").strip()
    reaches: list[dict] = []
    seen: set[tuple] = set()
    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            command = str((block.get("input") or {}).get("command") or "")
            if "git" not in command:
                continue
            for pattern, how in _GIT_REACH:
                match = pattern.search(command)
                if not match:
                    continue
                sha = match.group(1) if match.groups() else ""
                # A command naming the task's own fix is the answer, not a reach.
                names_fix = bool(sha and fix and (sha.startswith(fix[:7])
                                                  or fix.startswith(sha[:7])))
                if sha and source_ref and (sha.startswith(source_ref[:7])
                                           or source_ref.startswith(sha[:7])):
                    break  # naming its own pinned ref is not a reach
                kind = "answer_key" if names_fix else "history_reach"
                key = (how, sha, kind)
                if key not in seen:
                    seen.add(key)
                    reaches.append({"tool": "Bash", "path": f"git {how}".strip(),
                                    "kind": kind, "command": command[:160]})
                break
    return reaches


def transcript_text(worktree: Path, session_id: str, projects_base: Path | None = None) -> str:
    """The harness transcript of the arm session — the probe/judging capture."""
    base = projects_base or (Path.home() / ".claude" / "projects")
    path = base / project_slug(worktree) / f"{session_id}.jsonl"
    return path.read_text() if path.is_file() else ""


# ---------------------------------------------------------------------------
# Oracles
# ---------------------------------------------------------------------------


def pin_pre_existing_suite(repo: Path, worktree: Path, source_ref: str) -> None:
    """Restore `tests/` to the task's starting ref before grading.

    L1 is "the *pre-existing* suite stays green", and pre-existing means the suite
    at `source.ref` — the one a candidate arm actually inherits. Anchors and
    mutants start from `fix_ref` instead, whose tree carries the tests the fix
    shipped with itself, and grading against those measures something no arm was
    ever measured against. Two concrete distortions, both observed on this task:

    - Every degradation collapses to rung 0. The fix's own unit test fails on any
      mutant that weakens case-insensitivity, so L1 falls and the ladder never
      gets to say *how* degraded the candidate was — the discrimination the
      mutant set exists to measure is destroyed before rung 2.
    - Worse, it rewards imitation. `test_keyword_matching_is_case_insensitive_and_regex_safe`
      imports `_keyword_predicate` by name, so a *correct* fix that structures the
      predicate differently fails L1 on an ImportError. docs/04 requires the
      opposite: relations are behavioral precisely so they "cannot reward
      imitating the historical fix's names", and a gate that does is not a gate
      on quality.


    Called from BOTH paths, and that is the point. It landed with the oracle gate
    (lab/017) and for a while only the gate pinned, so `eval oracle` graded
    anchors against the inherited suite while a real arm was graded against
    whatever tests the candidate happened to leave behind. Two ways that goes
    wrong, one of them observed on the very first gated arm (lab/020): a
    candidate that writes an ambitious test its own fix does not satisfy fails L1
    for a defect the gate would never see, and a candidate that weakens or
    deletes a test passes L1 for the same reason. Neither is a no-regression
    measurement, and neither is what the gate validated.

    Only `tests/` is pinned. Source stays at the candidate's ref — that is the
    thing under grading. A ref carrying no `tests/` at all is a no-op rather than
    an error: there is no inherited suite to restore, so there is nothing the
    candidate could have altered.

    Restoring tracked files is not sufficient on its own. `git checkout` leaves
    *untracked* additions in place, so a candidate that drops a brand-new file
    into `tests/` would still have it graded — which is the same defect in a
    thinner disguise. The clean step is what makes "the suite it inherited"
    literally true.
    """
    probe = subprocess.run(
        ["git", "-C", str(worktree), "cat-file", "-e", f"{source_ref}:tests"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        return
    _git(worktree, "checkout", source_ref, "--", "tests")
    _git(worktree, "clean", "-fdq", "tests")


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
            "level": acc.level,
            "name": acc.name,
            "exit": exit_code,
            "passed": passed,
            # Only a *failure* can be an infra fault. A passing command that
            # happens to print one of these strings is still a pass.
            "infra_fault": None if passed else classify_infra_fault(tail, exit_code),
            "tail": tail,
        })
    return results


def ladder_score(acceptance: list[dict]) -> int:
    """The run's rung: highest level whose checks, and all lower ones, pass.

    Ordinal and lexicographic (docs/04, eval-methodology exchange
    `scope:main:exchange:06723ce1b78345a9`). Two properties earn the shape:
    adding a cheap check to a rung cannot raise the score, so there is no
    cardinality bias to correct (arXiv 2601.03525); and there are no weights,
    so nothing about the scale can be tuned after seeing results.

    A rung with no checks declared is not "satisfied by default" — it is absent,
    and the ladder stops below it. Scoring an undeclared rung as passed would
    hand a task a high score for having written nothing.
    """
    by_level: dict[int, list[dict]] = {}
    for entry in acceptance:
        by_level.setdefault(entry.get("level", 1), []).append(entry)
    score = 0
    for level in sorted(by_level):
        if level != score + 1:
            break  # a gap: the rung above it is unreachable
        if not all(entry["passed"] for entry in by_level[level]):
            break
        score = level
    return score


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


def memo_echo(task, transcript: str) -> dict:
    """How much of the injected fact shows up in what the candidate did.

    Excludes the prompt itself: the fact is *in* the first user turn by
    construction, so counting the whole transcript would score every ceiling arm
    as a perfect echo and measure nothing. Only assistant prose and tool-call
    inputs count, which is the same window layer-1 attribution judges against.
    """
    from thalamus.eval.attribution import attribute_prepared, node_terms, output_window, prepare

    fact = (task.under_specification.fact or "") if task.under_specification else ""
    if not fact.strip():
        return {"terms": 0, "matched": 0, "used": False}

    window = output_window(transcript.encode(), datetime.min.replace(tzinfo=timezone.utc))
    lower, tokens = prepare(window.text())
    terms = node_terms(fact)
    # The key doubles as a node id, and layer 1's strongest path is a substring
    # test on that id — so a key of "memo" scores every arm that says the word
    # "memo" as a citation. Named so it cannot occur in prose.
    key = "__injected_memo__"
    verdict = attribute_prepared({key: fact}, lower, tokens, {key: terms})[0]
    matched = sum(1 for term in terms if term in tokens)
    return {
        "terms": len(terms),
        "matched": matched,
        "ratio": round(matched / len(terms), 3) if terms else 0.0,
        "used": verdict.used,
        "evidence": verdict.evidence,
    }


def ceiling_prompt(task) -> str:
    """The task prompt with its withheld fact handed over as recalled memory.

    Framed as memory rather than as instruction on purpose. The comparison is
    against arms that *retrieve* — so the ceiling must differ from them in
    retrieval quality alone, not in whether the candidate was told what to do. A
    fact presented as "here is what a past session established" is the same speech
    act a perfect recall would have performed; "you must do X" is a different
    experiment.

    Refuses a task with no withheld fact: on an ungated task the ceiling arm is
    identical to memory-off, and running it would spend money to produce a
    duplicate labelled as a treatment.
    """
    fact = (task.under_specification.fact or "").strip() if task.under_specification else ""
    if not fact:
        raise ArmError(
            f"task `{task.id}` has no under_specification.fact, so it has no ceiling: "
            "with nothing withheld, a ceiling arm is memory-off wearing another name"
        )
    return (
        f"{task.prompt}\n\n"
        "---\n\n"
        "Recalled from memory of a past session on this codebase:\n\n"
        f"> {fact}\n"
    )


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
    sandbox: bool = False,
    isolate_store: bool = False,
) -> dict:
    if not task.source.ref:
        raise ArmError(f"task `{task.id}` has no source.ref to check out")
    base = runs_base or RUNS_BASE
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    worktree = base / "wt" / f"{task.id}--{arm.name}--{stamp}"

    refuse_self_leaking_task(repo, task.source.ref, task.id)
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
        # An arm you can't see confined is an arm you can't trust, same rule as
        # the stripped hooks above. `isolate_store` only bites arms that have no
        # memory surface: cutting the network on memory-on would remove the
        # treatment itself.
        #
        # `bridge`, not `none`. `none` does isolate the store, and it also
        # isolates the model API — the arm dies on turn 1 with "Unable to
        # connect to API (ENOTIMP)" and the campaign halts, which is what the
        # first attempt at this campaign did. The original check verified that
        # the *graph* was unreachable and never asked whether the arm could
        # still run. Measured at the TCP layer instead of by HTTP semantics,
        # which lie about a websocket port: from `bridge` the graph is
        # unreachable both on `localhost:8182` (the container's own loopback)
        # and on the gateway `172.17.0.1:8182`, because the server binds
        # loopback-only — while `api.anthropic.com` answers. That is the whole
        # requirement: no route to the store, a working session.
        network = "bridge" if (sandbox and isolate_store and not arm.mcp) else "host"
        record["applied"]["sandboxed"] = sandbox
        record["applied"]["network"] = network if sandbox else "host (unconfined)"
        started = time.monotonic()
        prompt = task.prompt
        if arm.inject_fact:
            prompt = ceiling_prompt(task)
            record["applied"]["injected_fact_chars"] = len(prompt) - len(task.prompt)
        agent = run_agent(
            worktree, prompt, scope=arm.scope, project=repo.name, model=model,
            max_turns=max_turns, timeout=timeout, full_auto=full_auto,
            sandbox=sandbox, network=network,
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
        #
        # `num_turns > max_turns` is NOT the test. lab/015 measured opus runs
        # reporting 46-53 turns against `--max-turns 40` while terminating
        # *normally* — `is_error=False`, a real closing summary in `result` —
        # so the reported turn count and the cap are not on the same scale and
        # the naive comparison marks completed runs as censored. The genuine
        # termination signature is the one every truly capped run carries:
        # errored, with an empty result because the model never got to conclude.
        record["turn_capped"] = (
            agent.num_turns >= max_turns
            and agent.is_error
            and not agent.result.strip()
        )
        record["wall_seconds"] = round(time.monotonic() - started, 1)

        # `is_error` alone is NOT a session-death signal — every turn-capped run
        # in runs.jsonl carries it too. The result string is the discriminator.
        session_fault = classify_session_fault(agent)
        if session_fault:
            # Nothing to grade, or an attempt of unknown completeness. Either
            # way a verdict here would describe the interruption and be read as
            # a statement about the candidate (lab/016).
            record["infra_fault"] = session_fault
            record["attributable"] = False
            record["void"] = True
            how = ("no work done" if session_fault.endswith("void")
                   else f"cut off after {agent.num_turns} turns of {max_turns}")
            raise SessionFault(
                f"{task.id} · {arm.spec}: session died ({how}) "
                "— record stamped void and ungraded, campaign stopped"
            )

        diff = _worktree_diff(worktree)
        record["diff_lines"] = len(diff.splitlines())
        # A confined session writes its transcript into the container's HOME,
        # not the operator's, so the reader must look where the arm wrote.
        transcript = transcript_text(
            worktree, agent.session_id,
            (arm_home_for(worktree) / ".claude" / "projects") if sandbox else None,
        )
        record["transcript_captured"] = bool(transcript)
        # Whether the arm actually reached for memory is the primary outcome of
        # the memory-on/off contrast, and it lived only in the transcript until
        # lab/015 had to re-derive it by hand for twelve arms across three
        # models. Recording it makes a campaign self-describing.
        record["recall_calls"] = count_recall_calls(transcript)
        # A ceiling arm's whole treatment is the injected fact, so whether the
        # candidate visibly acted on it is not optional colour — "perfect memory,
        # ignored" and "perfect memory, useless" are different findings and a rung
        # cannot separate them (experiments/004 pre-registration). Recorded at run
        # time because the arm's transcript does not outlive its worktree.
        #
        # Judged with layer 1's own instrument, thresholds and all, so its known
        # weakness is inherited openly rather than a second judge being invented
        # here: this counts term overlap in what the candidate *did*, and term
        # overlap is roughly 57 points floor and a little signal (experiments/001).
        if arm.inject_fact and transcript:
            record["memo_echoed"] = memo_echo(task, transcript)
        # Whether the candidate stayed inside its own experiment. lab/020 found
        # two arms reading the task file out of the operator's checkout by
        # absolute path; `contaminated` is the pre-registered exclusion key for
        # a per-protocol read, and the intention-to-treat comparison keeps every
        # arm regardless.
        record["escapes"] = detect_worktree_escape(
            transcript, worktree, repo,
            fix_touched_paths(repo, task.source.ref, task.source.fix_ref),
        ) + detect_history_reach(
            transcript, task.source.ref, task.source.fix_ref
        )
        record["contaminated"] = any(
            e["kind"] == "answer_key" for e in record["escapes"]
        )
        # L1 is "the *pre-existing* suite stays green", so the suite the
        # candidate inherited is the one that grades it — not the one it left
        # behind. Pinned after the diff is captured, so the record still shows
        # the candidate's real work including any tests it wrote.
        pin_pre_existing_suite(repo, worktree, task.source.ref)
        record["acceptance"] = evaluate_acceptance(task, worktree)
        record["accepted"] = bool(record["acceptance"]) and all(
            a["passed"] for a in record["acceptance"]
        )
        # The graded endpoint. `accepted` stays as the binary it always was so
        # lab/011-016 records remain comparable, but it is the saturated
        # measure (18/18) the ladder exists to replace.
        record["rung"] = ladder_score(record["acceptance"])
        # Probes are the *manipulation check* — did the intervention reach the
        # arm — never part of the score. memo-surfaced fires iff the arm called
        # a thalamus tool (lab/016, 0 mismatches at n=18), which makes it an
        # excellent delivery detector and a disqualifying one as an outcome: a
        # memory-off arm cannot emit a UUID it never saw, so scoring it would
        # make memory-on > memory-off true by construction.
        record["probes"] = evaluate_probes(task, transcript, diff, worktree)

        # Flag, never exclude (arXiv 2111.03382, 2605.05564): the verdict above
        # stays exactly as measured; `attributable` says whether it can be read
        # as a fact about the *candidate*. lab/013 lost a whole task-pair to a
        # `uv run pytest` failure that rendered identically to a real
        # regression, so this distinction has to live in the record itself.
        faults = sorted({
            a["infra_fault"] for a in record["acceptance"] if a["infra_fault"]
        })
        record["infra_faults"] = faults
        record["attributable"] = not faults
    finally:
        record["kept"] = keep
        if not keep:
            remove_worktree(repo, worktree)
            # The confined arm's private HOME holds its credentials copy and
            # its transcript; both have been read by now.
            shutil.rmtree(arm_home_for(worktree), ignore_errors=True)
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
        + (", transcript MISSING" if not record.get("transcript_captured") else "")
        + (f", recall {record['recall_calls']['thalamus']} call(s)"
           f" / {record['recall_calls']['tool_search']} ToolSearch"
           if record.get("recall_calls") else ""),
        f"  applied: mcp_removed={record.get('applied', {}).get('mcp_removed')}, "
        f"stripped={len(record.get('applied', {}).get('stripped_hooks', []))} hook(s)",
    ]
    for acc in sorted(record.get("acceptance", []), key=lambda a: a.get("level", 1)):
        if acc["passed"]:
            mark = "PASS"
        elif acc.get("infra_fault"):
            mark = f"INFRA-FAULT[{acc['infra_fault']}]"
        else:
            mark = "FAIL"
        label = f" {acc['name']}" if acc.get("name") else ""
        lines.append(
            f"  L{acc.get('level', 1)}{label} {mark} (exit {acc['exit']}): {acc['run']}"
        )
    if "rung" in record:
        lines.append(f"  => RUNG {record['rung']}")
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
