"""The falsifier docs/13 lists as owed for the ledger rule.

docs/13's design rests on one sentence: **`main` never acts on `qe`'s classification
because `qe` asserted it — it re-derives the verdict from the ledger and acts only
where the two agree.** `verify_report` (`src/thalamus/harness/ci_triage.py`) is that
re-derivation, and it did not exist to test until this session: `main` built it as an
importable function that takes a report's claims and the ledger's rows and returns
every `Disagreement` between them.

A disagreement *rate* cannot tell "the report was always right" apart from "the
verifier is blind" — both look identical when nothing has ever disagreed. What can
tell them apart is a planted lie: construct a report claiming a case is `known-red`
(triaged, safe to leave red) while the ledger's own verdict for that exact case is
`new-failure` (untriaged, unactioned), and require `verify_report` to refuse it rather
than let it through. This is structurally identical to
`expectation_additions.py`'s own `_control()` (`tests/qe/cases/expectation_additions.py:268-280`)
— a planted mismatch the mechanism must not let through — aimed at `main`'s
verification step instead of the expectations differ, per this scope's round-2 design
answer (consultation `107f3a026be148ba`).

## The positive control

A verifier that refuses every report, unconditionally, would pass the planted-lie
assertion above while being useless — a rubber stamp inverted into a permanent veto is
still not verification. So this case also requires an honest report — every claim
matches the ledger exactly — to verify **clean** (`[]`, not merely "no disagreement
about the planted case"). Both halves run before the realistic scenario below, on
abstract single-letter case names, so a failure in either is legible on its own terms
before the more elaborate fixture is read.
"""

from __future__ import annotations

from ..model import Case, FailureClass, Finding, Substrate, Tier

_CASE_NAME = "triage-verifier-refuses-a-report-the-ledger-contradicts"

_CONTROL_LEDGER = [
    {"case": "planted-honest", "verdict": "known-red"},
    {"case": "planted-mismatch", "verdict": "new-failure"},
    {"case": "planted-absent-from-report", "verdict": "fixed"},
]


class Undecidable(Exception):
    """The control failed, so a clean report below would be unfalsifiable.

    Raised rather than returned: `run.py` renders an exception as MALFORMED, which is
    the one verdict `reconcile()` refuses to let an expectation absorb.
    """


def _control(verify_report) -> None:
    """Isolate exactly the planted mismatch, and pass an honest report clean.

    Two impostors this rules out, from opposite directions: a verifier that always
    returns `[]` (rubber-stamps everything) fails the negative half below, since it
    would not isolate `planted-mismatch` either. A verifier that always returns every
    claimed case as a disagreement (refuses everything, unconditionally) fails the
    positive half, since the honest report would come back non-empty. Only a verifier
    that actually compares claim to ledger passes both.
    """
    honest = {"planted-honest": "known-red", "planted-mismatch": "new-failure"}
    clean = verify_report(honest, _CONTROL_LEDGER)
    if clean:
        raise Undecidable(
            f"an honest report — every claim matches the ledger — was not verified "
            f"clean, so this case's refusal of a planted lie below would prove "
            f"nothing about discrimination: got {clean!r}"
        )

    planted = {"planted-honest": "known-red", "planted-mismatch": "known-red"}
    caught = verify_report(planted, _CONTROL_LEDGER)
    names = {d.case for d in caught}
    if names != {"planted-mismatch"}:
        raise Undecidable(
            f"the verifier did not isolate exactly the planted mismatch: expected "
            f"only 'planted-mismatch' flagged against the honest 'planted-honest', "
            f"got {sorted(names)}"
        )


def run() -> Finding | None:
    from thalamus.harness.ci_triage import verify_report  # noqa: PLC0415

    _control(verify_report)

    # A realistic-shaped ledger — the fields `ledger.py`'s `_row` actually emits, of
    # which `verify_report` reads only `case` and `verdict`. The planted lie: a report
    # claims `console-write-origin` is `known-red` (triaged, leave it) while the
    # ledger's own verdict for that exact case is `new-failure` (untriaged red) — the
    # exact shape docs/13 names as the hazard this hop exists to close.
    ledger_rows = [
        {
            "run_id": "abc123def456", "case": "console-write-origin",
            "verdict": "new-failure", "failure_class": "boundary-leak",
            "witness": "origin header absent on 3/20 probes",
        },
        {
            "run_id": "abc123def456", "case": "unarmed-hook-must-gate",
            "verdict": "known-red", "failure_class": "unenforced-signal",
            "witness": "advisory only",
        },
    ]
    report = {
        "console-write-origin": "known-red",  # FALSE: ledger says new-failure
        "unarmed-hook-must-gate": "known-red",  # true: matches the ledger
    }

    disagreements = verify_report(report, ledger_rows)
    flagged = {d.case for d in disagreements}

    if "console-write-origin" not in flagged:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "verify_report let a report through that claims a NEW_FAILURE case is "
                "known-red and safe to leave alone. docs/13's whole hop rests on "
                "'main never acts on qe's classification because qe asserted it' — a "
                "report shaped exactly like this one reaching main unrefused means "
                "the independent-verification step is decorative, not a gate"
            ),
            witness=f"report={report!r} ledger={ledger_rows!r} -> "
                    f"disagreements={disagreements!r}",
            site="src/thalamus/harness/ci_triage.py:verify_report",
        )
    if "unarmed-hook-must-gate" in flagged:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "verify_report flagged a claim that matched the ledger exactly. A "
                "verifier that cannot tell a true claim from a false one is not "
                "independent verification — it is noise shaped like a gate, and the "
                "positive control above should have caught this before the realistic "
                "fixture ever ran"
            ),
            witness=f"report={report!r} ledger={ledger_rows!r} -> "
                    f"disagreements={disagreements!r}",
            site="src/thalamus/harness/ci_triage.py:verify_report",
        )
    return None


CASE = Case(
    name=_CASE_NAME,
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED,),
    summary="verify_report must refuse a report claiming a NEW_FAILURE case is "
            "known-red, and must not refuse an honest one",
    run=run,
)
