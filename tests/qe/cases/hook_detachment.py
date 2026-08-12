"""Work a session-end hook does must not sit on the exiting process's critical path.

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
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_HOOKS = Path(__file__).resolve().parents[3] / "src" / "thalamus" / "harness" / "hooks"

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


def run() -> Finding | None:
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


CASE = Case(
    name="session-end-hooks-detach-their-work",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="expensive session-end work must be detached, or the exiting session kills it",
    run=run,
)
