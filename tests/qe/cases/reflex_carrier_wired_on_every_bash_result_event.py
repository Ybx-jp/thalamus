"""The reflex carrier sits in exactly one unmatchered group on `PostToolUse` and one
on `PostToolUseFailure`, and on no other event.

Supersedes `reflex-carrier-is-exactly-one-posttooluse-group` (this case's earlier
shape): that case asserted `PostToolUse` only, citing docs/14-memory-reflex.md §4's
"Wired on `PostToolUse` only" — the sentence ledger A0181 grounded and A0189 has since
superseded. `reflex-pointer-tap.sh` now runs on both events a tool call can end on
(`install.py`'s `HOOK_WIRING` gained `("PostToolUseFailure", None,
"reflex-pointer-tap.sh")` beside the existing `PostToolUse` row), so a digest waiting
for the agent no longer holds if the agent's next call happens to fail — a failed
`pytest` run followed by a fix-and-rerun no longer sits on a delivery an unrelated
event tripped it into. The invariant this case now guards is the current one: exactly
one row per event, on exactly those two events, both unmatchered.

A duplicate entry on either event would double-run the carrier on every tool call of
that kind for no declared reason; a matcher narrowed off `None` on either would
silently stop it seeing whole classes of tool calls it is supposed to run on every one
of (docs/cli.md: "`PostToolUse` and `PostToolUseFailure`, all tools"); a row wired on
some third event would run a carrier expecting a Bash-result-shaped payload
(`tool_use_id`, `tool_input`) against an event that may not carry one; and a row
missing outright on either event is exactly the shape of the gap this case's own prior
version carried between thalamus PR #280 (carrier on `PostToolUse` only) and the
follow-up that wired it on `PostToolUseFailure` too.

**Positive controls, against a synthetic baseline rather than the live table.** The
checking logic (`_check`) is exercised against a *constructed* wiring — every other
script's rows from the live table, plus exactly the two correct carrier rows — rather
than the live table itself, specifically so a control does not depend on the live
table already being correct. Against that baseline: `_check` must flag a duplicated
row on `PostToolUse`, a duplicated row on `PostToolUseFailure`, a matcher narrowed off
`None` on either event, and a `PostToolUseFailure` row removed outright — the last one
reproducing, on a controlled fixture, the exact gap the live table carried before
`main`'s follow-up landed, so this case is shown capable of having caught it. Only once
every control passes does `_check` run against the real `install.HOOK_WIRING`.

Hermetic: reads `install.HOOK_WIRING`, no environment or process.
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_carrier_wired_on_every_bash_result_event.py::run"
_SCRIPT = "reflex-pointer-tap.sh"
_EVENTS = ("PostToolUse", "PostToolUseFailure")


def _rows_for(wiring, event):
    return [(e, matcher, name) for e, matcher, name in wiring
            if name == _SCRIPT and e == event]


def _check(wiring) -> Finding | None:
    """The invariant: exactly one unmatchered carrier row per event in `_EVENTS`."""
    for event in _EVENTS:
        rows = _rows_for(wiring, event)
        if len(rows) != 1:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    f"the reflex carrier is not wired as exactly one entry on "
                    f"{event} in HOOK_WIRING — either duplicated (it would run more "
                    "than once per tool call) or absent (a digest waiting for the "
                    f"agent would not be delivered on a {event} call)"
                ),
                witness=f"event={event} rows={rows!r}",
                site="src/thalamus/harness/install.py::HOOK_WIRING",
            )
        _event, matcher, _name = rows[0]
        if matcher is not None:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    f"the reflex carrier's {event} row carries a matcher, narrowing "
                    "it off some tool calls — docs/cli.md states it runs on "
                    "PostToolUse and PostToolUseFailure, all tools"
                ),
                witness=f"event={event} matcher={matcher!r}",
                site="src/thalamus/harness/install.py::HOOK_WIRING",
            )
    other_events = [(event, matcher, name) for event, matcher, name in wiring
                     if name == _SCRIPT and event not in _EVENTS]
    if other_events:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the reflex carrier is wired on an event other than PostToolUse or "
                "PostToolUseFailure — the only two events a Bash tool call ends on, "
                "and the only shape its payload is documented to carry"
            ),
            witness=f"other_events={other_events!r}",
            site="src/thalamus/harness/install.py::HOOK_WIRING",
        )
    return None


def run() -> Finding | None:
    from thalamus.harness import install  # noqa: PLC0415

    live = list(install.HOOK_WIRING)
    # A known-good synthetic baseline: every OTHER script's live rows, untouched, plus
    # exactly the two correct carrier rows — built this way so the controls below do
    # not depend on the live table already being correct.
    others = [row for row in live if row[2] != _SCRIPT]
    baseline = [*others, *((event, None, _SCRIPT) for event in _EVENTS)]

    if _check(baseline) is not None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: the constructed known-good baseline "
                "(every other script's live rows plus exactly the two correct "
                "carrier rows) was itself flagged, so nothing below distinguishes a "
                "real defect from a broken checker"
            ),
            witness=f"_check(baseline)={_check(baseline)!r}",
            site=_SITE,
        )

    for event in _EVENTS:
        duplicated = [*baseline, (event, None, _SCRIPT)]
        if _check(duplicated) is None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    f"positive control failed: a duplicated carrier row on {event} "
                    "was not flagged, so a clean result on the real table would not "
                    "show anything"
                ),
                witness=f"event={event} rows={_rows_for(duplicated, event)!r}",
                site=_SITE,
            )
        narrowed = [(e, "Bash", name) if name == _SCRIPT and e == event
                    else (e, matcher, name) for e, matcher, name in baseline]
        if _check(narrowed) is None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    f"positive control failed: narrowing the carrier's {event} "
                    "matcher away from None was not flagged"
                ),
                witness=f"event={event} rows={_rows_for(narrowed, event)!r}",
                site=_SITE,
            )

    # The regression this case's prior version missed: the carrier wired on
    # PostToolUse only, with no PostToolUseFailure row at all.
    missing_failure = [row for row in baseline
                        if row != ("PostToolUseFailure", None, _SCRIPT)]
    if _check(missing_failure) is None:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: removing the carrier's PostToolUseFailure "
                "row entirely was not flagged — the exact shape of the gap between "
                "thalamus PR #280 and the follow-up that wired the carrier on "
                "PostToolUseFailure too"
            ),
            witness=f"rows={_rows_for(missing_failure, 'PostToolUseFailure')!r}",
            site=_SITE,
        )

    return _check(live)


CASE = Case(
    name="reflex-carrier-is-exactly-one-group-on-each-bash-result-event",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "reflex-pointer-tap.sh is wired as exactly one unmatchered entry on each of "
        "PostToolUse and PostToolUseFailure, and on no other event"
    ),
    run=run,
)
