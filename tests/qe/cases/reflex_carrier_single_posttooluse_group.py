"""The reflex carrier sits in exactly one `PostToolUse` group in `HOOK_WIRING`.

docs/14-memory-reflex.md §4 ("The carrier") and §7's qe companion list both state this
as a fact the design depends on: `reflex-pointer-tap.sh` is wired
`("PostToolUse", None, "reflex-pointer-tap.sh")` and nowhere else, "so no `HOOK_WIRING`
row or parity count changed" when it was added, and the `PostToolUseFailure` row the
doc names as not yet built is exactly what thalamus PR #280's follow-up (bumping
`tests/qe/install/checks.py::EXPECTED_HOOK_ENTRIES`, landed beside this case) exists to
let `main` add safely — a second, distinguishable row, not a silent duplicate of the
first. A duplicate `PostToolUse` entry for the same script would double-run the carrier
on every tool call for no declared reason, and a matcher accidentally narrowed off
`None` would silently stop the carrier seeing whole classes of tool calls it is
supposed to run on every one of (docs/14 §4: "Matched on every tool, because a file is
read through `Read`, `Grep` and `Bash` alike").

**Positive control.** The detector must be shown capable of firing: a `HOOK_WIRING`
copy with the carrier's row duplicated must be flagged, and a copy with the row
narrowed to a matcher must be flagged too — otherwise a clean result on the real table
could mean the counting is broken rather than that the table is correct.

Hermetic: reads `install.HOOK_WIRING`, no environment or process.
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_carrier_single_posttooluse_group.py::run"
_SCRIPT = "reflex-pointer-tap.sh"


def _posttooluse_rows(wiring, script):
    return [(event, matcher, name) for event, matcher, name in wiring
            if name == script and event == "PostToolUse"]


def run() -> Finding | None:
    from thalamus.harness import install  # noqa: PLC0415

    wiring = list(install.HOOK_WIRING)

    # CONTROLS: the detector must be able to go red on the two ways this could break.
    duplicated = [*wiring, ("PostToolUse", None, _SCRIPT)]
    if len(_posttooluse_rows(duplicated, _SCRIPT)) <= 1:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: a duplicated carrier row was not detected "
                "as more than one PostToolUse entry, so a clean result on the real "
                "table would not show anything"
            ),
            witness=f"rows={_posttooluse_rows(duplicated, _SCRIPT)!r}",
            site=_SITE,
        )
    narrowed = [(event, "Bash", name) if name == _SCRIPT and event == "PostToolUse"
                else (event, matcher, name) for event, matcher, name in wiring]
    if any(matcher is None for _e, matcher, name in _posttooluse_rows(narrowed, _SCRIPT)):
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: narrowing the carrier's matcher away from "
                "None was not visible to the same read this case uses on the real "
                "table"
            ),
            witness=f"rows={_posttooluse_rows(narrowed, _SCRIPT)!r}",
            site=_SITE,
        )

    rows = _posttooluse_rows(wiring, _SCRIPT)
    if len(rows) != 1:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the reflex carrier is not wired as exactly one PostToolUse entry in "
                "HOOK_WIRING — either duplicated (it would run more than once per "
                "tool call) or absent (the digest and the pointer-open tap would "
                "never run at all)"
            ),
            witness=f"rows={rows!r}",
            site="src/thalamus/harness/install.py::HOOK_WIRING",
        )
    _event, matcher, _name = rows[0]
    if matcher is not None:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the reflex carrier's PostToolUse row carries a matcher, narrowing "
                "it off some tool calls — docs/14 §4 states it must match every "
                "tool, since a pointer file is read through Read, Grep and Bash alike"
            ),
            witness=f"matcher={matcher!r}",
            site="src/thalamus/harness/install.py::HOOK_WIRING",
        )

    other_events = [(event, matcher, name) for event, matcher, name in wiring
                     if name == _SCRIPT and event != "PostToolUse"]
    if other_events:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the reflex carrier is wired on an event other than PostToolUse in "
                "addition to it — docs/14 §4 states it is wired on PostToolUse only, "
                "pending the qe-owned EXPECTED_HOOK_ENTRIES bump that lets main add "
                "a distinct PostToolUseFailure row"
            ),
            witness=f"other_events={other_events!r}",
            site="src/thalamus/harness/install.py::HOOK_WIRING",
        )
    return None


CASE = Case(
    name="reflex-carrier-is-exactly-one-posttooluse-group",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="reflex-pointer-tap.sh is wired as exactly one unmatchered PostToolUse entry",
    run=run,
)
