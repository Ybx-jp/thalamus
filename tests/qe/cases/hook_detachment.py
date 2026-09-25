"""Work a session-end hook does must not sit on the exiting process's critical path —
and, since thalamus PR #280, the same question for the reflex's enqueuing hook and its
carrier, checked by a different mechanism because their detachment is not text a bash
scan can see.

Corpus record: `delta-staging-cancelled-by-the-envelope` (lab/050). A headless
`claude -p` exits the moment it prints its envelope, and a SessionEnd hook still running
when that happens is cancelled. Fork delta staging ran synchronously in the foreground,
so it was killed mid-flight — observed twice, once as `Hook cancelled` and once as a
fork whose staging never happened and whose log stops after its first line. A few
seconds of `uv run` is enough to lose the race.

The failure mode is what makes this worth a permanent case rather than a one-line fix:
the loser of the race is the memory write, and it loses *silently*. Nothing reports a
cancelled hook to the session that just ended, so the symptom is an episode that is
simply absent from the graph later — indistinguishable from a session that had nothing
worth distilling.

The invariant is the general form the record names: an expensive invocation in a
session-end hook must be inside a detached block, never on the path the exiting process
waits for. Asserted over every harness's `session-end.sh`, not just Claude Code's —
`cursor/session-end.sh` deliberately does no extraction today, and the moment it grows
one this case decides whether it grew it detached. Two hooks implementing one rule, with
only one of them exercised, is this repo's `mirror-divergence` class (corpus entries 86,
129, 151).

Read as text rather than by running the hook: proving the race behaviourally means
racing a real headless session against a real exit, which is a deep-tier experiment that
answers "did it lose this time" rather than "can it lose at all".

**Extension (thalamus PR #280): the reflex's enqueuing hook and its carrier.** Both are
still `session-end.sh`'s question — must the harness's exiting or continuing process
wait on expensive work — but the text scan above cannot answer it for either, and
applying it naively would be wrong twice over:

- `hooks/claude-code/reflex.sh`'s enqueuing path runs `uv run ... thalamus reflex ...`
  in the foreground, matching `_HEAVY` — and that is *correct*: the call appends to
  `pending.jsonl` and returns, cheap by design (docs/14 §4). The actual expensive
  work — the local model's loop, tens of seconds — is spawned from *inside* that
  foreground call by `reflex_queue.spawn_worker()`, a Python `subprocess.Popen(...,
  start_new_session=True, close_fds=True)`, not a bash `nohup ... &`. A text scan
  extended naively to `reflex.sh` would flag its correct foreground call; it has
  nothing that could see whether the Python-level spawn inside it actually detaches.
  So "detached" is checked behaviourally instead, against the real function:
  `spawn_worker()` must return long before its child does (the hook must not become a
  process that waits on the worker), and the child must land in its own session
  (`start_new_session=True`'s actual guarantee — immune to a signal delivered to the
  hook's process group or session, the same property `nohup`/`setsid` give a bash
  hook, and the one lab/050's race turned on: an interactive `/exit` does not stop a
  running hook's children, but a session-level signal could reach a non-detached one).
- `hooks/claude-code/reflex-pointer-tap.sh` (the carrier) also runs a foreground
  `uv run ... thalamus reflex --deliver ...`, and that too is correct: `--deliver`
  reads ready results and returns their digest, no model call
  (`cli.py::_cmd_reflex`). The carrier never calls `spawn_worker()` — only `fire()`'s
  agentic branch does — so there is no child spawn to check on the carrier's side.
  What the carrier could get wrong instead is a wiring drift: `--deliver` silently
  routed to `reflex_worker.work()` (the worker's own blocking loop) rather than
  `reflex_worker.deliver()`. That is checked directly against `cli._cmd_reflex`.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOKS = Path(__file__).resolve().parents[3] / "src" / "thalamus" / "harness" / "hooks"
_SITE = "tests/qe/cases/hook_detachment.py::run"

_SLOW_STUB_WORKER = """#!/bin/sh
echo $$ > "{pidfile}"
sleep 5
echo done > "{donefile}"
"""

# Costly enough to lose the race: a `uv run` (which resolves an environment before it
# does anything) or a `thalamus <verb>` invocation. The space matters — the hooks source
# helper shell functions named `thalamus_*`, which are cheap and must not match.
_HEAVY = re.compile(r"uv run\b|\bthalamus\s+[a-z]")
_DETACH_START = re.compile(r"^\s*(nohup|setsid)\b")
# A trailing `&` backgrounds the command. `2>&1` ends in `1`, so it cannot match here.
_BACKGROUNDED = re.compile(r"&\s*$")

_POISONED = """#!/bin/sh
uv run --project /repo thalamus quick delta --transcript "$t" --parent "$p"
nohup sh -c "
  uv run --project /repo thalamus extract --write
" >>"$log" 2>&1 </dev/null &
exit 0
"""


def _foreground_work(source: str) -> list[tuple[int, str]]:
    """Heavy invocations that are not inside (or themselves) a detached block."""
    lines = source.splitlines()
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if start is None and _DETACH_START.search(line):
            start = index
        elif start is not None and _BACKGROUNDED.search(line):
            regions.append((start, index))
            start = None

    found: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not _HEAVY.search(line) or line.lstrip().startswith("#"):
            continue
        detached = any(a <= index <= b for a, b in regions) or _BACKGROUNDED.search(line)
        if not detached:
            found.append((index + 1, line.strip()[:70]))
    return found


def _session_end_hooks_detach_their_work() -> Finding | None:
    # CONTROL: the detector must flag the shape the defect shipped with — one heavy call
    # hoisted above an otherwise correct detached block. Run first, because every hook
    # passing and the matcher having broken produce the same clean output.
    if not _foreground_work(_POISONED):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector no longer flags foreground staging above a detached "
                    "block, so a clean scan of the hooks would mean nothing",
            witness="poisoned fixture produced no finding",
            site="tests/qe/cases/hook_detachment.py::_POISONED",
        )
    # And it must not flag the detached block in that same fixture, or every hook would
    # read as broken and the case would be a stuck alarm rather than an oracle.
    if any("extract" in text for _, text in _foreground_work(_POISONED)):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the detector flags work inside a detached block, so it cannot tell "
                    "a correct hook from a broken one",
            witness=f"fixture findings: {_foreground_work(_POISONED)}",
            site="tests/qe/cases/hook_detachment.py::_foreground_work",
        )

    hooks = sorted(_HOOKS.rglob("session-end.sh"))
    if not hooks:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no session-end hook was found, so 'nothing runs in the foreground' "
                    "means 'nothing was read'",
            witness=str(_HOOKS),
            site="src/thalamus/harness/hooks/**",
        )

    violations: list[str] = []
    scanned_heavy = 0
    for path in hooks:
        source = path.read_text(encoding="utf-8", errors="ignore")
        scanned_heavy += sum(
            1
            for line in source.splitlines()
            if _HEAVY.search(line) and not line.lstrip().startswith("#")
        )
        violations += [
            f"{path.relative_to(_HOOKS.parents[3])}:{lineno} {text}"
            for lineno, text in _foreground_work(source)
        ]

    # CONTROL: at least one hook must do heavy work at all. Zero would mean the pattern
    # stopped matching the invocation shape, and a hook that runs nothing trivially
    # satisfies an invariant about what it runs.
    if scanned_heavy == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no session-end hook was seen invoking anything expensive, so a clean "
                    "result reports on the matcher rather than on the hooks",
            witness=f"scanned {len(hooks)} hook(s), matched 0 heavy invocations",
            site="tests/qe/cases/hook_detachment.py::_HEAVY",
        )

    if not violations:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a session-end hook does expensive work on the exiting process's critical "
            "path: a headless session exits when it prints its envelope, cancelling the "
            "hook mid-flight, and the work that loses is the memory write — silently"
        ),
        witness=f"{len(violations)} foreground invocation(s) of {scanned_heavy} scanned: "
                + "; ".join(violations[:5]),
        site="src/thalamus/harness/hooks/**/session-end.sh",
    )


def _spawn_worker_is_detached() -> Finding | None:
    """The enqueuing path's actual detachment: `reflex_queue.spawn_worker`, behaviourally.

    `spawn_worker()` resolves its own binary as `Path(sys.executable).parent /
    "thalamus"`, falling back to plain `"thalamus"` off PATH. `sys.executable` is
    pointed at a directory with no `thalamus` sibling so the fallback is exercised,
    and PATH is pointed at a stub script that reports its own pid and then sleeps —
    standing in for the local model's tens-of-seconds loop.
    """
    from thalamus.harness import reflex_queue  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_python_dir = tmp_path / "fakebin"
        fake_python_dir.mkdir()
        path_bin = tmp_path / "pathbin"
        path_bin.mkdir()
        pidfile = tmp_path / "worker.pid"
        donefile = tmp_path / "worker.done"
        script = path_bin / "thalamus"
        script.write_text(_SLOW_STUB_WORKER.format(pidfile=pidfile, donefile=donefile))
        script.chmod(0o755)

        root = tmp_path / "reflex"
        log = tmp_path / "worker.log"

        original_executable = sys.executable
        original_path = os.environ.get("PATH", "")
        sys.executable = str(fake_python_dir / "python3")
        os.environ["PATH"] = f"{path_bin}{os.pathsep}{original_path}"
        try:
            started = time.monotonic()
            spawned = reflex_queue.spawn_worker(root, log=log)
            elapsed = time.monotonic() - started
        finally:
            sys.executable = original_executable
            os.environ["PATH"] = original_path

        if not spawned:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "spawn_worker() reported it started nothing (worker.lock held by "
                    "a leftover process?), so nothing below is evidence about "
                    "detachment"
                ),
                witness=f"spawned={spawned}",
                site=_SITE,
            )

        # THE INVARIANT: the call must return long before the 5s stub does its work —
        # the enqueuing hook's own process (which waits on this call, not on the
        # worker) must not become a process that waits on the model loop.
        if elapsed > 2.0:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "spawn_worker() took several seconds to return against a child "
                    "that sleeps 5s — the enqueuing hook's `thalamus reflex` process "
                    "would be waiting on the worker instead of returning immediately"
                ),
                witness=f"elapsed={elapsed:.2f}s",
                site="src/thalamus/harness/reflex_queue.py::spawn_worker",
            )

        deadline = time.monotonic() + 5.0
        child_pid: int | None = None
        while time.monotonic() < deadline:
            if pidfile.is_file() and pidfile.read_text().strip():
                child_pid = int(pidfile.read_text().strip())
                break
            time.sleep(0.05)
        try:
            if child_pid is None:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "the stub worker never reported its own pid, so its session "
                        "cannot be checked for detachment"
                    ),
                    witness="worker.pid was never written",
                    site=_SITE,
                )

            try:
                child_sid = os.getsid(child_pid)
            except ProcessLookupError:
                child_sid = None
            own_sid = os.getsid(0)
            if child_sid == own_sid:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "the worker spawn_worker() started shares this process's "
                        "session id — start_new_session did not detach it, so a "
                        "signal reaching this process's session (the terminal "
                        "hangup an interactive exit can send, docs/14 §4 'The "
                        "channel, measured') could reach the worker too"
                    ),
                    witness=f"child_sid={child_sid} own_sid={own_sid}",
                    site="src/thalamus/harness/reflex_queue.py::spawn_worker",
                )
        finally:
            try:
                os.kill(child_pid, 15) if child_pid else None
            except ProcessLookupError:
                pass
    return None


def _carrier_deliver_never_runs_the_worker_loop() -> Finding | None:
    """The carrier's `--deliver` must dispatch to `deliver()`, never to `work()`.

    The carrier (`reflex-pointer-tap.sh`) never spawns anything itself — only
    `fire()`'s agentic branch calls `spawn_worker()` — so there is no child to check
    on its side. What it depends on instead is `cli.py::_cmd_reflex` routing
    `--deliver` to the cheap, synchronous `reflex_worker.deliver()` and never to
    `reflex_worker.work()`, the worker's own blocking model loop: if that ever
    drifted, the carrier's foreground `uv run ... --deliver` call — correct today
    because `--deliver` is cheap — would start waiting on the model loop instead.
    """
    from thalamus import cli  # noqa: PLC0415
    from thalamus.harness import reflex_worker  # noqa: PLC0415

    # `_cmd_reflex` does `from thalamus.harness import reflex_worker` at call time,
    # which binds the same module object already in `sys.modules` — patching its
    # attributes here reaches that local import too.
    calls: list[str] = []

    def fake_deliver(*_a, **_k):
        calls.append("deliver")
        return ""

    def fake_work(*_a, **_k):
        calls.append("work")
        return 0

    original_deliver = reflex_worker.deliver
    original_work = reflex_worker.work
    reflex_worker.deliver = fake_deliver
    reflex_worker.work = fake_work
    try:
        args = SimpleNamespace(
            work=False, sweep=False, deliver=True, session_id="s1", agent_id="",
            event="PostToolUse", reflex_dir=None, url="",
        )
        cli._cmd_reflex(args)
    finally:
        reflex_worker.deliver = original_deliver
        reflex_worker.work = original_work

    if "work" in calls:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "`thalamus reflex --deliver` — what the carrier hook runs on every "
                "tool call — invoked the worker's own blocking model loop "
                "(reflex_worker.work) rather than the cheap reflex_worker.deliver, "
                "so the carrier would be waiting on a model loop instead of "
                "returning a ready digest"
            ),
            witness=f"calls={calls!r}",
            site="src/thalamus/cli.py::_cmd_reflex",
        )
    if calls != ["deliver"]:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "`--deliver` did not reach reflex_worker.deliver() at all, so this "
                "case did not actually exercise the carrier's dispatch path"
            ),
            witness=f"calls={calls!r}",
            site=_SITE,
        )
    return None


def run() -> Finding | None:
    for check in (
        _session_end_hooks_detach_their_work,
        _spawn_worker_is_detached,
        _carrier_deliver_never_runs_the_worker_loop,
    ):
        finding = check()
        if finding is not None:
            return finding
    return None


CASE = Case(
    name="session-end-hooks-detach-their-work",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "expensive session-end work must be detached; the reflex worker spawn must "
        "not block its caller; the carrier's --deliver must never run the model loop"
    ),
    run=run,
)
