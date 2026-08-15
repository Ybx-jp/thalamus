"""A long-lived process must state the room it is in, never inherit it.

Found live, 2026-08-15: `/api/dispatch` called `dispatch.dispatch(...)` without
`caller_room`, and `dispatch()` had no such parameter to pass — the seam existed on
`authenticate` and was never plumbed through the public entry point. `authenticate`
falls back to `pin.resolve_room()`, which reads `THALAMUS_ROOM` from the *calling
process*. So a console started from a member's shell authenticates as that member for
its whole life and refuses every dispatch to every other room, naming in the refusal a
room the operator is not in and cannot see.

Latent in the shipped unit rather than reachable — a systemd `--user` unit inherits no
interactive environment, and the manager environment was measured clean. It arms the
moment anything runs `systemctl --user import-environment` from a room shell, and the
fix removes the dependence rather than resting on that.

`do_spawn` and `roster_sync` already pass `room=""` with docstrings giving exactly this
reasoning, and `/api/spawn` already had a `..._never_inherits_one` test. Dispatch got
neither the argument nor the test, which is why this is pinned as a property over
*every* call site instead of as one more assertion at one of them.

Both halves are asserted because they fail differently. A caller that omits the
argument inherits silently; a callee that does not accept it leaves every caller with
no way to be explicit, and that is the state this shipped in.
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

# Callers that outlive the session whose environment they would otherwise adopt.
LONG_LIVED = (("src/thalamus/console/server.py", "the console server"),)

_CALL = re.compile(r"dispatch\.dispatch\s*\(", re.S)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _call_args(source: str, start: int) -> str:
    """The argument text of one call, balanced across nested parentheses."""
    depth, i = 0, start
    while i < len(source):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                return source[start:i]
        i += 1
    return ""


def run() -> Finding | None:
    from thalamus.harness import dispatch, pin  # noqa: PLC0415

    faults: list[str] = []

    # Half one: the callee offers a way to be explicit at all.
    accepts = "caller_room" in inspect.signature(dispatch.dispatch).parameters
    if not accepts:
        faults.append(
            "dispatch() has no `caller_room` parameter, so no caller can state its "
            "room; authenticate() has the seam and it is not plumbed through")

    # Half two: every long-lived caller uses it.
    calls_seen = 0
    for relative, who in LONG_LIVED:
        source = (_repo_root() / relative).read_text()
        for match in _CALL.finditer(source):
            calls_seen += 1
            args = _call_args(source, match.end() - 1)
            if "caller_room" not in args:
                line = source[: match.start()].count("\n") + 1
                faults.append(
                    f"{relative}:{line} ({who}) calls dispatch.dispatch without "
                    f"caller_room, so it authenticates as whatever room its own "
                    f"process was started in")

    # CONTROL: the scan must find the call it is auditing. Zero call sites and a clean
    # surface produce the same verdict, and a renamed import or a moved endpoint would
    # silently empty this case rather than failing it.
    if calls_seen == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="no dispatch.dispatch call site was found in any long-lived "
                    "caller, so this case is asserting over nothing",
            witness=f"scanned {[r for r, _ in LONG_LIVED]}, matched 0 call sites",
            site="tests/qe/cases/longlived_caller_names_its_room.py",
        )

    # Half three, behavioural: `""` and `None` must actually differ. The two halves
    # above are structural and would both pass against a `caller_room` that was
    # accepted, forwarded, and then ignored.
    if accepts:
        previous = os.environ.get("THALAMUS_ROOM")
        os.environ["THALAMUS_ROOM"] = "qe-probe-elsewhere"
        try:
            # CONTROL: the poisoned environment must genuinely reach the refusal.
            # Without this, the roomless pass below could come from an environment
            # that was never dirty, which proves nothing at all.
            inherited_refused = False
            try:
                dispatch.authenticate("qe-probe-target", "console")
            except dispatch.DispatchRefused:
                inherited_refused = True

            if not inherited_refused:
                faults.append(
                    "authenticate() did not refuse while THALAMUS_ROOM named a "
                    "different room, so this case cannot show that passing '' is "
                    "what avoids the refusal")
            else:
                try:
                    dispatch.authenticate("qe-probe-target", "console", caller_room="")
                except dispatch.DispatchRefused as refused:
                    faults.append(
                        f"caller_room='' was refused anyway, so a roomless caller "
                        f"cannot declare itself: {refused}")
            if pin.resolve_room() != "qe-probe-elsewhere":
                faults.append(
                    "pin.resolve_room() does not read THALAMUS_ROOM, so the premise "
                    "of this case no longer holds and it should be re-derived")
        finally:
            if previous is None:
                os.environ.pop("THALAMUS_ROOM", None)
            else:
                os.environ["THALAMUS_ROOM"] = previous

    if not faults:
        return None

    return Finding(
        failure_class=FailureClass.BOUNDARY_LEAK,
        summary=(
            "a long-lived process takes the room it authenticates as from its own "
            "environment, so a console started inside a room adopts that room for "
            "life and refuses every other one"
        ),
        witness="; ".join(faults),
        site="src/thalamus/console/server.py::/api/dispatch",
    )


CASE = Case(
    name="a-long-lived-caller-states-its-room",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.BOUNDARY_LEAK, FailureClass.COLLAPSED_SENTINEL),
    summary="the console must declare itself roomless rather than inherit the room its "
            "own process was launched in",
    run=run,
)
