"""A firing must never inject past the session's char budget, and must say why not.

`reflex.fire` (`harness/reflex.py:369-372`) checks the cheap half of the budget before
ever asking the graph: a session whose recorded spend already meets
`SESSION_CHAR_BUDGET` is refused with the arithmetic and nothing is queried. That is the
control the design's own grounding leans on — an unsolicited injection past the ceiling
"costs more than it returns" (module docstring, `reflex.py:19-23`) — and it is a
UNIVERSAL over what got the session there: this case drives it directly by preloading
one ledger row at exactly the ceiling, the boundary the check has to get exactly right
rather than approximately.

**Positive control.** `ReflexBudget(spent=SESSION_CHAR_BUDGET - 1, cost=1).fits` must be
`True` — the row one character under the ceiling has to fit, or the boundary itself
cannot be trusted to separate "at or over" from "under", and a refusal at the ceiling
would say nothing about precision, only about the check firing on everything.

**Shown capable of going red.** Comment out the `if spent >= SESSION_CHAR_BUDGET:` guard
at `reflex.py:369-372` and rerun: `fire()` proceeds to call `recall` and, given any
matching content, returns a non-empty envelope past the ceiling; this case then reports
`INVARIANT_FALSIFIED` with that envelope's length as the witness. `qe` does not write
`src/thalamus/harness/`, so the mutation is not carried in the case.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

# A failure text extract_anchors turns into several distinct anchors — the case does
# not depend on which ones, only that there are at least the two `fire()` requires
# before it does anything else (`MIN_NEW_ANCHORS`).
_OBSERVED = (
    "FAILED tests/qe/cases/reflex_budget_ceiling_probe.py::test_ceiling\n"
    "E       AssertionError: reflex_budget_ceiling_probe_marker broke\n"
)


def run() -> Finding | None:
    from thalamus.harness.reflex import (  # noqa: PLC0415
        SESSION_CHAR_BUDGET,
        Firing,
        ReflexBudget,
        fire,
        load_firings,
    )

    # CONTROL: one character under the ceiling must fit, or the exact boundary this
    # case preloads means nothing — a refusal at the ceiling would be indistinguishable
    # from a check that refuses everything regardless of spend.
    if not ReflexBudget(spent=SESSION_CHAR_BUDGET - 1, cost=1).fits:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "positive control failed: a budget one character under the ceiling "
                "does not fit, so the ceiling preloaded below cannot be shown to be "
                "an exact boundary rather than a check that always refuses"
            ),
            witness=f"ReflexBudget(spent={SESSION_CHAR_BUDGET - 1}, cost=1).fits=False",
            site="tests/qe/cases/reflex_budget_ceiling.py::run",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ledger = tmp_path / "reflex" / "sessions" / "s1.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            Firing(
                ts="2026-09-13T11:00:00Z", session_id="s1", agent_id="", outcome="served",
                keys=["qe-budget-ceiling-probe-unrelated"], injected_chars=SESSION_CHAR_BUDGET,
            ).to_json() + "\n"
        )

        envelope = fire(
            object(), session_id="s1", observed=_OBSERVED, scope="main", agent_id="",
            agent_type="", cwd="/qe-budget-ceiling-probe", now=_NOW,
            reflex_base=tmp_path / "reflex", traces_base=tmp_path / "traces",
        )
        rows = load_firings("s1", tmp_path / "reflex")
        last = rows[-1] if rows else None

        if envelope == "" and last is not None and last.outcome == "refused":
            has_arithmetic = (
                f"{SESSION_CHAR_BUDGET:,}-char budget" in last.detail and "over by" in last.detail
            )
            if has_arithmetic:
                return None
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "a firing refused at the char budget ceiling does not report the "
                    "arithmetic in its ledger row, so a refused session cannot see "
                    "why the reflex stopped injecting"
                ),
                witness=f"refusal detail={last.detail!r}",
                site="src/thalamus/harness/reflex.py::ReflexBudget.refusal",
            )

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "a firing whose session had already spent its full char budget was "
                "not refused before the graph was asked: fire() returned an "
                f"envelope or a ledger outcome other than 'refused' "
                f"(outcome={last.outcome if last else '<no row written>'!r})"
            ),
            witness=f"envelope_len={len(envelope)} outcome={last.outcome if last else None!r}",
            site="src/thalamus/harness/reflex.py::fire",
        )


CASE = Case(
    name="reflex-budget-refuses-at-the-ceiling",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a firing must never inject past SESSION_CHAR_BUDGET and must report the arithmetic",
    run=run,
)
