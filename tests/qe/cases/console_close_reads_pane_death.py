"""A graceful close must be recognised as one, not waited out and then force-killed.

Issue #151, fixed. Both teardown workers poll for the window's disappearance through
`_window_gone` (`console/server.py:249`), which answers from `list-windows` — has this
window id left the session's enumeration — and that is a *different* question from
whether the pane inside has already exited. `recycle_window` (:1005) asks both:

    if _window_gone(cfg, wid):
        return  # window vanished entirely; roster sync recreates it
    r = tmux("display", "-p", "-t", target, "#{pane_dead}")
    if r.stdout.strip() == "1":
        dead = True
        break

`close_window` (:1064) asks both too:

    if _window_gone(cfg, wid):
        return  # window already gone: claude exited and tmux closed it
    r = tmux("display", "-p", "-t", target, "#{pane_dead}")
    if r.stdout.strip() == "1":
        return  # the agent exited; remain-on-exit is keeping the corpse

The check matters because `remain-on-exit` being on is the ordinary case rather than an
exotic one: `docs/console.md:867` instructs setting it globally
(`tmux -L thalamus set -wg remain-on-exit on`) to diagnose a spawn that never execed, and
never instructs unsetting it. With it on, a pane that exits cleanly leaves a corpse —
the window stays in `list-windows`, so `_window_gone` never fires — and without the
`#{pane_dead}` poll the loop would run the whole `RECYCLE_GRACE_S = 240` budget before
doing the two things reserved for a hang: `_record_forced_kill(who, "close")` and
`kill-window`, to a session that ran `/exit`, fired SessionEnd, and distilled normally.

Measured against real tmux 3.4 on a private socket, 2026-08-31:

    $ tmux -L $S new-session -d -s t 'sh -c "read x"'
    $ tmux -L $S set -w -t t:0 remain-on-exit on
    $ tmux -L $S send-keys -t t:0 Enter        # exits gracefully
    $ tmux -L $S display -p -t t:0 '#{pane_dead}'
    1                                          # rc=0, on every poll
    $ tmux -L $S list-windows -t t
    0: sh[dead]* (1 panes) [80x24] @0 (active)

The window is still in `list-windows` — `_window_gone` will not fire — while `display`
already reports the pane dead. That is what makes the two questions genuinely
different: a check on `_window_gone` alone cannot answer it, and getting it wrong writes
a forced-kill record — whose whole meaning is "SessionEnd never ran, nothing will ever
distil this session" — about a session that distilled fine, with the band the operator
reads on the phone (`app.js:1079`) false for every one of them.

**Nothing here executes tmux.** The stub answers `display` and `list-windows` from
fixtures and records argv. `_record_forced_kill` is stubbed too, and that is not only
for speed: the real one appends to the operator's live `distill-killed.jsonl`, so a
case that let it through would forge exactly the false record it exists to report.
`RECYCLE_GRACE_S` is shortened to keep the case under a few seconds; the property under
test is the check itself, not the size of the budget it would otherwise burn.

**Three controls, all running.**

1. *Discrimination against the fixed sibling.* The same probe runs against
   `recycle_window`, on a fixture where the window stays enumerated (so `_window_gone`
   does not fire) but the pane reports dead. `recycle_window`'s extra `display` poll
   must catch that and force nothing. If both functions looked clean the probe would
   be blind, and this is the strongest available green control because it is real
   product code with the correct shape rather than a mutation written here.
2. *The forcing control.* On a window that stays enumerated for the whole grace budget
   and a pane that never reports dead, `close_window` must force — record the kill and
   call `kill-window`. Without this, "close_window forced" and "the probe cannot see
   forcing at all" are the same observation, and the case would pass forever once its
   stub drifted.
3. *The vanished-window control.* With `list-windows` no longer naming the window's id,
   the existing early return must fire: no force, no kill. This pins the one exit path
   the function had before the `#{pane_dead}` check existed, so a regression that
   removed it while touching the new check would be caught.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

# One window, in the eleven tab-separated fields `list-windows -F` prints. `%0` is the
# id `_window_id` captures and `_window_gone` then looks for in this same listing.
_WID = "%0"
_WINDOWS = f"0\tmain\t1\tclaude\t80\t24\t0\t/tmp\tclaude\t{_WID}\t991"

# Long enough that a correct implementation's early exit is unambiguous, short enough
# that the defect's full burn costs the suite a couple of seconds instead of four
# minutes. The loop sleeps 1s per turn, so this is ~2 polls.
_GRACE_S = 1.2


class _StubTmux:
    """Answers `display` and `list-windows` from fixtures, and records argv.

    `display` is asked for two different formats — `#{window_id}` (once, by
    `_window_id`, before either loop starts) and `#{pane_dead}` (by `recycle_window`,
    inside its loop) — and the two must not share one answer: `_window_id` has to
    resolve so the loops have a real id to poll for, independent of whatever the pane's
    fixture says. Executes nothing, ever.
    """

    def __init__(self, pane_dead: str = "0", window_present: bool = True) -> None:
        self._pane_dead = pane_dead
        self._window_present = window_present
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        if args and args[0] == "display":
            if args[-1] == "#{window_id}":
                return subprocess.CompletedProcess(args=list(args), returncode=0,
                                                   stdout=_WID, stderr="")
            if args[-1] == "#{pane_dead}":
                return subprocess.CompletedProcess(args=list(args), returncode=0,
                                                   stdout=self._pane_dead, stderr="")
        if args and args[0] == "list-windows":
            out = _WINDOWS if self._window_present else ""
            return subprocess.CompletedProcess(args=list(args), returncode=0,
                                               stdout=out, stderr="")
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout="", stderr="")

    def ran(self, verb: str) -> bool:
        return any(c and c[0] == verb for c in self.calls)


@contextlib.contextmanager
def _harnessed(console, pane_dead: str = "0", window_present: bool = True):
    """The teardown functions with tmux, the ledger and the grace budget replaced.

    `_record_forced_kill` is replaced rather than allowed to no-op on a missing
    watcher: this case must observe the call, and it must not be able to append to the
    operator's real killed-window ledger on a box where a watcher does exist.
    """
    stub = _StubTmux(pane_dead, window_present)
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


def _teardown(console, fn, cfg, pane_dead: str = "0", window_present: bool = True):
    """(stub, forced) after running one teardown worker to completion."""
    with _harnessed(console, pane_dead, window_present) as (stub, forced):
        fn(cfg, 0)
        return stub, list(forced)


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        (root / ".git").mkdir(parents=True)
        cfg = console.Config(session="qe-close-probe", project_root=root)

        # CONTROL 2, first: on a window that stays enumerated and a pane that never
        # reports dead, close_window must force. If it does not, this probe cannot see
        # forcing at all and its verdict on the graceful-exit fixture is not evidence.
        stub, forced = _teardown(console, console.close_window, cfg,
                                  pane_dead="0", window_present=True)
        if not forced or not stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="close_window did not force on a window that stayed enumerated "
                        "past the grace budget, so this probe cannot observe forcing at "
                        "all and its result on a graceful exit is not evidence",
                witness=f"window_present=True, pane_dead=0 for {_GRACE_S}s: "
                        f"_record_forced_kill calls={len(forced)}, "
                        f"kill-window ran={stub.ran('kill-window')}",
                site="tests/qe/cases/console_close_reads_pane_death.py",
            )

        # CONTROL 3: the one early exit close_window does have must still fire.
        stub, forced = _teardown(console, console.close_window, cfg,
                                  window_present=False)
        if forced or stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="close_window forced on a window list-windows no longer names, "
                        "so its vanished-window early return is not working and the "
                        "graceful-exit result cannot be attributed to the missing check",
                witness=f"window_present=False: _record_forced_kill "
                        f"calls={len(forced)}, kill-window ran={stub.ran('kill-window')}",
                site="src/thalamus/console/server.py::_window_gone",
            )

        # CONTROL 1: the fixed sibling, on the same fixture the property is asserted
        # over — window still enumerated, pane reports dead. recycle_window's extra
        # `display` poll must catch that and stop early.
        stub, forced = _teardown(console, console.recycle_window, cfg,
                                  pane_dead="1", window_present=True)
        if forced:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="recycle_window also forced on a gracefully-dead pane, so this "
                        "fixture does not distinguish a loop that reads pane_dead from "
                        "one that ignores it and the probe is blind",
                witness=f"recycle_window on window_present=True, pane_dead=1: "
                        f"_record_forced_kill calls={len(forced)}, ops="
                        f"{[op for _, op in forced]}",
                site="tests/qe/cases/console_close_reads_pane_death.py",
            )

        # THE PROPERTY. Same fixture, the other function.
        stub, forced = _teardown(console, console.close_window, cfg,
                                  pane_dead="1", window_present=True)
        if forced or stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.UNENFORCED_SIGNAL,
                summary="close_window has no path that reads `#{pane_dead}`, so a "
                        "session that exited gracefully under remain-on-exit — window "
                        "still enumerated, pane already dead — is waited out for the "
                        "whole grace budget and then force-killed and recorded as never "
                        "having distilled",
                witness=f"window stayed enumerated with pane_dead=1 for {_GRACE_S}s; "
                        f"close_window recorded {len(forced)} forced kill(s) "
                        f"{[op for _, op in forced]} and "
                        f"kill-window ran={stub.ran('kill-window')} — "
                        f"recycle_window on the identical fixture recorded none",
                site="src/thalamus/console/server.py:1064",
            )
    return None


CASE = Case(
    name="a-graceful-close-is-not-recorded-as-a-forced-kill",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.UNENFORCED_SIGNAL, FailureClass.COLLAPSED_SENTINEL),
    summary="close_window must read the `#{pane_dead}` `recycle_window` also polls for, "
            "so a pane that exited gracefully is not waited out and then force-killed",
    run=run,
    issue=151,
    fixed=True,
)
