"""A graceful close must be recognised as one, not waited out and then force-killed.

Issue #151, open. `close_window` (`console/server.py:1052`) polls `#{pane_dead}` once a
second and throws the answer away:

    while time.time() < deadline:
        r = tmux("display", "-p", "-t", target, "#{pane_dead}")
        if r.returncode != 0:
            return  # window already gone
        time.sleep(1)

Its only early exit is the tmux command *failing*. `recycle_window` (:1011) runs the
identical poll and does read the value — `if r.stdout.strip() == "1": dead = True; break`.
The two functions were written to the same shape and one of them lost its predicate.

The consequence needs `remain-on-exit` to be on, which is the ordinary case rather than
an exotic one. `docs/console.md:850` instructs setting it globally
(`tmux -L thalamus set -wg remain-on-exit on`) to diagnose a spawn that never execed, and
never instructs unsetting it; `recycle_window` sets it at :1003 and unsets it at :1024,
the last statement of a `try` whose `finally` (:1026) pops `RECYCLING` and nothing else,
so any raise in between leaves it on for good. With it on, a pane that exits cleanly
leaves a corpse: `display` answers rc 0 and `pane_dead 1`, forever. The loop therefore
runs the whole `RECYCLE_GRACE_S = 240` budget and then does the two things reserved for a
hang — `_record_forced_kill(who, "close")` and `kill-window` — to a session that ran
`/exit`, fired SessionEnd, and distilled normally.

Measured against real tmux 3.4 on a private socket, 2026-08-31:

    $ tmux -L $S new-session -d -s t 'sh -c "read x"'
    $ tmux -L $S set -w -t t:0 remain-on-exit on
    $ tmux -L $S send-keys -t t:0 Enter        # exits gracefully
    $ tmux -L $S display -p -t t:0 '#{pane_dead}'
    1                                          # rc=0, on every poll
    $ tmux -L $S list-windows -t t
    0: sh[dead]* (1 panes) [80x24] @0 (active)

So the forced-kill record — whose whole meaning is "SessionEnd never ran, nothing will
ever distil this session" — is written about sessions that distilled fine, and the band
the operator reads on the phone (`app.js:1079`) is false for every one of them.

**Nothing here executes tmux.** The stub answers `display` from a fixture and records
argv. `_record_forced_kill` is stubbed too, and that is not only for speed: the real one
appends to the operator's live `distill-killed.jsonl`, so a case that let it through
would forge exactly the false record it exists to report. `RECYCLE_GRACE_S` is shortened
to keep the case under a few seconds; the defect is the missing predicate, and the size
of the budget it burns is not the property.

**Three controls, all running.**

1. *Discrimination against the fixed sibling.* The same probe runs against
   `recycle_window`, which is the same loop with the predicate present. On the identical
   dead-pane fixture it must stop early and force nothing. If both functions looked clean
   the probe would be blind, and this is the strongest available green control because it
   is real product code with the correct shape rather than a mutation written here.
2. *The forcing control.* On a pane that is genuinely alive (`pane_dead 0` throughout),
   `close_window` must force — record the kill and call `kill-window`. Without this,
   "close_window forced" and "the probe cannot see forcing at all" are the same
   observation, and the case would pass forever once its stub drifted.
3. *The vanished-window control.* With `display` answering rc 1, the existing early
   return must fire: no force, no kill. This pins the one exit path the function does
   have, so a repair that removed it in the course of adding the predicate is caught.

**Shown capable of going red** — it is red now, against the defect as it ships. To watch
it go green, give `close_window` the predicate its sibling has:

    r = tmux("display", "-p", "-t", target, "#{pane_dead}")
    if r.returncode != 0:
        return
    if r.stdout.strip() == "1":
        return

and re-run: control 1 keeps passing, control 2 keeps passing, and the finding clears.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

# One window, in the eleven tab-separated fields `list-windows -F` prints.
_WINDOWS = "0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t%0\t991"

# Long enough that a correct implementation's early exit is unambiguous, short enough
# that the defect's full burn costs the suite a couple of seconds instead of four
# minutes. The loop sleeps 1s per turn, so this is ~2 polls.
_GRACE_S = 1.2


class _StubTmux:
    """Answers `display` from a fixture and records argv. Executes nothing, ever."""

    def __init__(self, pane_dead: str, returncode: int = 0) -> None:
        self._pane_dead = pane_dead
        self._returncode = returncode
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        if args and args[0] == "display":
            return subprocess.CompletedProcess(args=list(args),
                                               returncode=self._returncode,
                                               stdout=self._pane_dead, stderr="")
        out = _WINDOWS if args and args[0] == "list-windows" else ""
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout=out, stderr="")

    def ran(self, verb: str) -> bool:
        return any(c and c[0] == verb for c in self.calls)


@contextlib.contextmanager
def _harnessed(console, pane_dead: str, returncode: int = 0):
    """The teardown functions with tmux, the ledger and the grace budget replaced.

    `_record_forced_kill` is replaced rather than allowed to no-op on a missing
    watcher: this case must observe the call, and it must not be able to append to the
    operator's real killed-window ledger on a box where a watcher does exist.
    """
    stub = _StubTmux(pane_dead, returncode)
    forced: list[tuple[dict, str]] = []
    saved = (console.tmux, console._record_forced_kill, console._pinned_session,
             console.RECYCLE_GRACE_S)
    console.tmux = stub
    console._record_forced_kill = lambda who, op: forced.append((who, op))
    console._pinned_session = lambda cfg, idx: {"session": "qe000000", "scope": "qe",
                                                "cwd": "/tmp", "project": "thalamus",
                                                "repo_root": "/tmp"}
    console.RECYCLE_GRACE_S = _GRACE_S
    try:
        yield stub, forced
    finally:
        (console.tmux, console._record_forced_kill, console._pinned_session,
         console.RECYCLE_GRACE_S) = saved


def _teardown(console, fn, cfg, pane_dead: str, returncode: int = 0):
    """(stub, forced) after running one teardown worker to completion."""
    with _harnessed(console, pane_dead, returncode) as (stub, forced):
        fn(cfg, 0)
        return stub, list(forced)


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        (root / ".git").mkdir(parents=True)
        cfg = console.Config(session="qe-close-probe", project_root=root)

        # CONTROL 2, first: on a pane that never dies, close_window must force. If it
        # does not, this probe cannot see forcing and its verdict on the dead pane
        # would mean nothing.
        stub, forced = _teardown(console, console.close_window, cfg, "0")
        if not forced or not stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="close_window did not force on a pane that stayed alive past "
                        "the grace budget, so this probe cannot observe forcing at all "
                        "and its result on a dead pane is not evidence",
                witness=f"pane_dead=0 for {_GRACE_S}s: "
                        f"_record_forced_kill calls={len(forced)}, "
                        f"kill-window ran={stub.ran('kill-window')}",
                site="tests/qe/cases/console_close_reads_pane_death.py",
            )

        # CONTROL 3: the one early exit close_window does have must still fire.
        stub, forced = _teardown(console, console.close_window, cfg, "", returncode=1)
        if forced or stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="close_window forced on a window tmux says is already gone, so "
                        "its vanished-window early return is not working and the "
                        "dead-pane result cannot be attributed to the missing predicate",
                witness=f"display rc=1: _record_forced_kill calls={len(forced)}, "
                        f"kill-window ran={stub.ran('kill-window')}",
                site="src/thalamus/console/server.py:1054",
            )

        # CONTROL 1: the fixed sibling, on the same fixture the property is asserted
        # over. recycle_window reads `pane_dead` and must stop early.
        stub, forced = _teardown(console, console.recycle_window, cfg, "1")
        if forced:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="recycle_window also forced on a gracefully-dead pane, so this "
                        "fixture does not distinguish a loop that reads pane_dead from "
                        "one that ignores it and the probe is blind",
                witness=f"recycle_window on pane_dead=1: "
                        f"_record_forced_kill calls={len(forced)}, ops="
                        f"{[op for _, op in forced]}",
                site="tests/qe/cases/console_close_reads_pane_death.py",
            )

        # THE PROPERTY. Same fixture, the other function.
        stub, forced = _teardown(console, console.close_window, cfg, "1")
        if forced or stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.UNENFORCED_SIGNAL,
                summary="close_window ignores the `#{pane_dead}` it polls for, so a "
                        "session that exited gracefully is waited out for the whole "
                        "grace budget and then force-killed and recorded as never "
                        "having distilled",
                witness=f"tmux answered rc=0 `1` on every poll for {_GRACE_S}s; "
                        f"close_window recorded {len(forced)} forced kill(s) "
                        f"{[op for _, op in forced]} and "
                        f"kill-window ran={stub.ran('kill-window')} — "
                        f"recycle_window on the identical fixture recorded none",
                site="src/thalamus/console/server.py:1052",
            )
    return None


CASE = Case(
    name="a-graceful-close-is-not-recorded-as-a-forced-kill",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="close_window must read the `#{pane_dead}` it polls for, so a pane that "
            "exited gracefully is not waited out and then force-killed",
    run=run,
    issue=151,
)
