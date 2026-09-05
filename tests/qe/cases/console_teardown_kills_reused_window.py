"""A stalled teardown must not force-kill whatever now occupies its window's index.

Issue #153, open — but narrower against current code than filed. The issue's own
quotes (`target = f"{cfg.session}:{idx}"` at the old `server.py:1043`/`:998`, with no
id capture at all) describe a version of `close_window`/`recycle_window` that no
longer exists: both functions now open with

    who = _pinned_session(cfg, idx)
    wid = _window_id(cfg, idx)
    target = wid or f"{cfg.session}:{idx}"

and use `target` — not `idx` — for every tmux call for the rest of the function,
including the poll (`_window_gone(cfg, wid)`) and the eventual force. `_window_id`'s own
docstring states the property that defeats the issue's primary scenario: a window id
(`@N`) "is minted once and never reassigned", unlike an index. Measured here (see
`_teardown`'s exploration, reproduced by this case's own GREEN_CONTROL run): once `wid`
capture succeeds, `_window_gone(cfg, wid)` correctly notices A's id has left
`list-windows` the instant a same-indexed replacement appears, and returns before
either function ever reaches its force path. **The primary interleaving the issue
describes does not reproduce on current code.**

A narrower version of the same hazard does. `target = wid or f"{cfg.session}:{idx}"`
falls back to idx-addressing whenever `_window_id`'s own capture — one `display -t
<session>:<idx> #{window_id}` call, at the very top of the function, before either loop
starts — fails (non-zero rc). And `_window_gone` has a guard for exactly that case:

    if not wid:
        return False

An empty `wid` makes `_window_gone` return `False` unconditionally, without even
calling `list-windows` — so the one check that would have caught A's disappearance is
disabled for the rest of the function, *and* the eventual force still fires at
`f"{cfg.session}:{idx}"`, an index-shaped target a real tmux resolves against whoever
currently sits there. Both properties the fix relies on — the early exit, and
identity-stable addressing — are lost together, for the same reason, in the same
branch. If a same-indexed replacement (session B) has landed by the time the grace
budget expires, the force-kill (`close_window`) or forced respawn (`recycle_window
-k`) destroys B, while `_record_forced_kill(who, ...)` — `who` captured from A before
the race, per the issue's own "Already decided" — still writes the row under A's
identity. The row is now false in both directions: A, whatever became of it, is not
what got destroyed, and B — a session that never hung — is gone without SessionEnd and
absent from its own kill row entirely.

**Nothing here executes tmux.** `_StubTmux` answers `display` and `list-windows` from a
declared timeline and records argv; it never calls `list-windows` with the real 11-field
projection `list_windows()` expects, because `_pinned_session` is stubbed directly (as
in `console_close_reads_pane_death.py`) rather than allowed to run — the same reason:
this case must observe the forced-kill call without being able to forge the record it
reports on, or risk the operator's live roster if the stub ever slipped through to a
real tmux.

**Three runs, all executed.**

1. *Discrimination + detector control.* The vulnerable path (`wid` capture fails), on a
   timeline where the index is **not** reused — N still legitimately names A when the
   budget expires. `close_window` must still force, and must name A: this is what
   proves a kill can be observed at all, and that "the wrong window was killed" is
   distinguishable from "nothing was killed" or "the probe cannot see forcing".
2. *Green control.* The current code's own default path (`wid` capture succeeds), on
   the **same reused-index timeline** the property is asserted over. `_window_gone`
   must catch A's vanished id and return before either function reaches a force. This
   is what shows the primary defect is gone in the common case — real product code,
   not a mutation written here.
3. *The property.* The vulnerable path, on the reused-index timeline. Both
   `close_window` and `recycle_window` are checked: each must not resolve its force to
   session B, and must not write a kill row that claims A while destroying B.

A real tmux server is not running, so "destroys B" is not observed directly; the
resolution a real server would perform is reproduced in `_really_destroyed`, grounded
in the two measured claims already in `server.py`'s own docstrings — a window id is
never reassigned, an index is not identifying once its window closes.

**Shown capable of going red**: run 3 fails now, against the defect as it ships in the
fallback branch. To watch it clear, either remove the fallback (require a captured
`wid` and refuse to proceed on an empty one, since `_window_gone` cannot do its job
without it) or give the index-addressed branch its own re-resolution immediately before
the force, checking that the window it is about to destroy is still the one `who` was
read from.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SESSION = "qe-close-probe"
_IDX = 0
_IDX_TARGET = f"{_SESSION}:{_IDX}"
# A's window id. Minted once, never reassigned — the property `_window_id`'s
# docstring states and this case leans on to tell a same-indexed replacement (B) apart
# from A once `wid` capture has actually succeeded.
_WID_A = "@1"
# B's window id, standing for "whatever now occupies index N". Never handed to
# close_window/recycle_window directly (they only ever hold A's identity); it exists
# so `list-windows` can report a world where A's id is gone and something else has
# taken the index.
_WID_B = "@2"

# Long enough that a correct early exit is unambiguous, short enough that the
# defect's full burn costs the suite a couple of seconds. Both loops sleep 1s/turn.
_GRACE_S = 1.2


class _StubTmux:
    """Answers `display` and `list-windows` from a declared timeline; records argv.

    The very first call either function makes is `_window_id`'s own capture, while
    index N still names A — modeled here as call #1. Every call after it sees the
    post-interleaving world: A's id gone from `list-windows`, and — when `reused` — B
    now sitting at N. Executes nothing, ever.
    """

    def __init__(self, *, wid_capture_fails: bool, reused: bool) -> None:
        self._wid_capture_fails = wid_capture_fails
        self._reused = reused
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess:
        self.calls.append(args)
        settled = len(self.calls) > 1
        if args and args[0] == "display":
            if args[-1] == "#{window_id}":
                if self._wid_capture_fails:
                    return subprocess.CompletedProcess(args=list(args), returncode=1,
                                                       stdout="", stderr="no such window")
                return subprocess.CompletedProcess(args=list(args), returncode=0,
                                                   stdout=_WID_A, stderr="")
            if args[-1] == "#{pane_dead}":
                # Never reports dead: isolates this case from #151 (the missing
                # pane_dead check) by making the grace budget's full burn the only
                # way either function reaches its force path here.
                return subprocess.CompletedProcess(args=list(args), returncode=0,
                                                   stdout="0", stderr="")
        if args and args[0] == "list-windows":
            present = _WID_B if (settled and self._reused) else _WID_A
            return subprocess.CompletedProcess(args=list(args), returncode=0,
                                               stdout=present, stderr="")
        return subprocess.CompletedProcess(args=list(args), returncode=0,
                                           stdout="", stderr="")

    def ran(self, verb: str) -> bool:
        return any(c and c[0] == verb for c in self.calls)

    def target_of(self, verb: str) -> str | None:
        """The `-t` argument of the first call to `verb`, or None if it never ran."""
        for c in self.calls:
            if c and c[0] == verb and "-t" in c:
                return c[c.index("-t") + 1]
        return None


def _really_destroyed(target: str | None, *, reused: bool) -> str | None:
    """What a real tmux server would tear down for this argv, on this timeline.

    Neither function re-resolves its target before destroying it, so this is the only
    place that answers the question. Grounded in `server.py`'s own measured claims
    (`_window_id`, `_window_gone`): a window id is minted once and never reassigned, so
    a wid-shaped target still names A specifically; an index is not identifying once
    its window closes, so an idx-shaped target resolves to whoever tmux currently
    seats there — B if the index was reused, A otherwise.
    """
    if target is None:
        return None
    if target == _WID_A:
        return "A"
    if target == _IDX_TARGET:
        return "B" if reused else "A"
    return None


@contextlib.contextmanager
def _harnessed(console, *, wid_capture_fails: bool, reused: bool):
    """The teardown functions with tmux, the ledger and the grace budget replaced.

    `_record_forced_kill` is replaced rather than allowed to no-op on a missing
    watcher: this case must observe the call, and must not be able to append to the
    operator's real killed-window ledger on a box where a watcher does exist.
    `_pinned_session` is replaced so `who` deterministically names session A — the
    identity the real function would have read from index N before this race began.
    """
    stub = _StubTmux(wid_capture_fails=wid_capture_fails, reused=reused)
    forced: list[tuple[dict, str]] = []
    saved = (console.tmux, console._record_forced_kill, console._pinned_session,
             console.RECYCLE_GRACE_S)
    console.tmux = stub
    console._record_forced_kill = lambda who, op: forced.append((who, op))
    console._pinned_session = lambda cfg, idx: {"session": "session-A", "scope": "qe",
                                                "cwd": "/tmp", "project": "thalamus",
                                                "repo_root": "/tmp"}
    console.RECYCLE_GRACE_S = _GRACE_S
    try:
        yield stub, forced
    finally:
        (console.tmux, console._record_forced_kill, console._pinned_session,
         console.RECYCLE_GRACE_S) = saved


def _teardown(console, fn, cfg, *, wid_capture_fails: bool, reused: bool):
    """(stub, forced) after running one teardown worker to completion."""
    with _harnessed(console, wid_capture_fails=wid_capture_fails,
                    reused=reused) as (stub, forced):
        fn(cfg, _IDX)
        return stub, list(forced)


def run() -> Finding | None:
    from thalamus.console import server as console  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "checkout"
        (root / ".git").mkdir(parents=True)
        cfg = console.Config(session=_SESSION, project_root=root)

        # CONTROL 1: discrimination + detector. Vulnerable path, index NOT reused —
        # N still legitimately names A at the deadline. close_window must still
        # force and must name A: without this, "the wrong window was killed" cannot
        # be told from "nothing was killed" or "the probe stopped observing forcing".
        stub, forced = _teardown(console, console.close_window, cfg,
                                  wid_capture_fails=True, reused=False)
        killed = stub.target_of("kill-window")
        destroyed = _really_destroyed(killed, reused=False)
        if not forced or killed is None or destroyed != "A":
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="close_window did not force-kill the right session on an "
                        "index that was never reused, so this probe cannot tell a "
                        "misattributed kill apart from a detector that stopped "
                        "observing forcing at all",
                witness=f"wid_capture_fails=True, reused=False: forced={bool(forced)}, "
                        f"kill-window target={killed!r}, resolves to={destroyed!r}",
                site="tests/qe/cases/console_teardown_kills_reused_window.py",
            )

        # CONTROL 2: green control. The current code's own default path (wid capture
        # succeeds) against the identical reused-index timeline. `_window_gone` must
        # catch A's vanished id and return before either function reaches a force.
        stub, forced = _teardown(console, console.close_window, cfg,
                                  wid_capture_fails=False, reused=True)
        if forced or stub.ran("kill-window"):
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="close_window force-killed even on the path where window-id "
                        "capture succeeded, so id-addressed teardown no longer "
                        "defends against index reuse either — the issue's primary "
                        "scenario reproduces broadly, not only through the wid-"
                        "capture-failure fallback",
                witness=f"wid_capture_fails=False, reused=True: forced={bool(forced)}, "
                        f"kill-window ran={stub.ran('kill-window')}",
                site="src/thalamus/console/server.py::close_window",
            )

        # THE PROPERTY. Vulnerable path, index reused: close_window must not
        # resolve its force to B, and must not write a kill row naming A for a
        # destruction that (if it happened at all) hit B instead.
        stub, forced = _teardown(console, console.close_window, cfg,
                                  wid_capture_fails=True, reused=True)
        killed = stub.target_of("kill-window")
        destroyed = _really_destroyed(killed, reused=True)
        close_hit = forced and destroyed == "B"

        # Same property, `recycle_window` — its force is `respawn-window -k`.
        stub_r, forced_r = _teardown(console, console.recycle_window, cfg,
                                      wid_capture_fails=True, reused=True)
        killed_r = stub_r.target_of("respawn-window")
        destroyed_r = _really_destroyed(killed_r, reused=True)
        recycle_hit = forced_r and destroyed_r == "B" and "-k" in stub_r.calls[
            [c[0] for c in stub_r.calls].index("respawn-window")]

        if close_hit or recycle_hit:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="when window-id capture fails at teardown start, "
                        "close_window/recycle_window fall back to addressing the "
                        "window by index for the whole grace budget; a same-indexed "
                        "replacement landing before the budget expires is force-"
                        "killed (or force-respawned) in the original session's "
                        "place, while the kill row still names the original session",
                witness=(
                    f"close_window: forced={bool(forced)} naming "
                    f"{forced[0][0]['session'] if forced else None!r}, "
                    f"kill-window target={killed!r} resolves to={destroyed!r}; "
                    f"recycle_window: forced={bool(forced_r)} naming "
                    f"{forced_r[0][0]['session'] if forced_r else None!r}, "
                    f"respawn-window target={killed_r!r} resolves to={destroyed_r!r}"
                ),
                site="src/thalamus/console/server.py::close_window",
            )
    return None


CASE = Case(
    name="a-stalled-teardown-does-not-force-kill-a-reused-index",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="close_window/recycle_window must not force-kill whatever now occupies "
            "a window's index, nor record that destruction under the identity of "
            "the session the teardown actually started against",
    run=run,
    issue=153,
)
