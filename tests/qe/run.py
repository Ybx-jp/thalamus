"""The runner. `python tests/qe/run.py --tier fast`

Not a pytest plugin and not a `thalamus` subcommand. Both absences are deliberate:
pytest is a dev-only extra, and the suite lives outside `src/` because it must not ship
in the wheel — a released package carrying known-red entries would hand every installer
a working oracle for the defects in the release they just installed.

Exit codes are separated rather than collapsed into one red X, because if every failure
renders identically the cheap ones get rerun until green, and rerunning until green is
the (1-p)^k laundering channel wearing process clothes:

    0  every case passed, or failed exactly as triaged
    1  a NEW failure, or a known-red that DRIFTED into a different defect
    2  a case PASSED that an expectation says should fail — delete the expectation
    3  a case is MALFORMED — the check itself is broken, which is not evidence
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qe import expectations as exp_mod  # noqa: E402
from qe import ledger as ledger_mod  # noqa: E402
from qe.model import Case, CaseResult, Finding, Outcome, Tier, missing_substrate  # noqa: E402

REPO_ROOT = _HERE.parents[1]

# Resolved by NAME, never by holding a callable in a data file. This is what lets the
# committed expectations file name a case without importing it, and it is why an
# unresolvable name is MALFORMED rather than a silent skip — a suite that quietly drops
# a case it cannot find reports green over a shrinking denominator.
CASE_MODULES = (
    "qe.cases.ingress_floor",
    "qe.cases.hook_arming",
    "qe.cases.guard_failopen",
    "qe.cases.ingest_gate",
    "qe.cases.floor_coverage",
    "qe.cases.ingest_redirect",
    "qe.cases.home_isolation",
    "qe.cases.tmux_socket",
    "qe.cases.ranker_dials",
    "qe.cases.served_tier_rule",
    "qe.cases.doc_mcp_snippet",
    "qe.cases.secret_scan_heard",
    "qe.cases.prompt_template_roundtrip",
    "qe.cases.probe_vocabulary",
    "qe.cases.shadowed_tests",
)


def load_cases() -> tuple[list[Case], list[str]]:
    cases, broken = [], []
    for name in CASE_MODULES:
        try:
            module = importlib.import_module(name)
            case = module.CASE
        except Exception as exc:  # noqa: BLE001
            broken.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if not isinstance(case, Case):
            broken.append(f"{name}: CASE is {type(case).__name__}, not Case")
            continue
        cases.append(case)
    return cases, broken


def execute(case: Case) -> CaseResult:
    missing = missing_substrate(case)
    if missing:
        return CaseResult(case.name, Outcome.SKIPPED, case.tier, missing=missing)

    started = time.monotonic()
    try:
        finding = case.run()
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            case.name, Outcome.MALFORMED, case.tier,
            detail=f"{type(exc).__name__}: {exc}",
            duration_s=time.monotonic() - started,
        )
    elapsed = time.monotonic() - started

    if finding is None:
        return CaseResult(case.name, Outcome.PASSED, case.tier, duration_s=elapsed)

    if not isinstance(finding, Finding):
        return CaseResult(
            case.name, Outcome.MALFORMED, case.tier,
            detail=f"run() returned {type(finding).__name__}, expected Finding or None",
            duration_s=elapsed,
        )

    # A case emitting a class outside its own declaration is MALFORMED, not failed: an
    # expectation triaged against this case could not have anticipated the class, so
    # reconciliation would be meaningless.
    if finding.failure_class not in case.classes:
        return CaseResult(
            case.name, Outcome.MALFORMED, case.tier,
            detail=(f"emitted {finding.failure_class.value}, which is not in this case's "
                    f"declared classes {[c.value for c in case.classes]}"),
            duration_s=elapsed,
        )

    return CaseResult(case.name, Outcome.FAILED, case.tier, finding=finding, duration_s=elapsed)


_MARK = {
    exp_mod.OK: "✓", exp_mod.KNOWN_RED: "○", exp_mod.NEW_FAILURE: "✗",
    exp_mod.DRIFTED: "✗", exp_mod.FIXED: "△", exp_mod.SKIPPED: "–",
    exp_mod.MALFORMED: "!",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thalamus adversarial suite (scope qe)")
    parser.add_argument("--tier", choices=[t.value for t in Tier], default=Tier.FAST.value)
    parser.add_argument("--all-tiers", action="store_true", help="run every tier")
    parser.add_argument("--no-ledger", action="store_true", help="do not append a run row")
    args = parser.parse_args(argv)

    cases, broken = load_cases()
    if args.all_tiers:
        selected = cases
    else:
        selected = [c for c in cases if c.tier.value == args.tier]

    expectations, exp_sha = exp_mod.load()
    header = ledger_mod.new_header(
        tier="all" if args.all_tiers else args.tier,
        rev=ledger_mod.repo_rev(REPO_ROOT),
        tree_dirty=ledger_mod.dirty(REPO_ROOT),
        expectations_sha=exp_sha,
    )

    print(f"qe suite — tier={header.tier} rev={header.rev}"
          f"{' (dirty)' if header.dirty else ''} expectations={exp_sha}\n")

    rows: list[tuple[CaseResult, str]] = []
    for case in selected:
        result = execute(case)
        verdict, why = exp_mod.reconcile(result, expectations)
        rows.append((result, verdict))
        detail = result.finding.summary if result.finding else (result.detail or why)
        print(f"  {_MARK.get(verdict, '?')} {case.name} [{verdict}]")
        if detail:
            print(f"      {detail}")
        if result.finding and result.finding.witness:
            print(f"      witness: {result.finding.witness}")
        if verdict in (exp_mod.NEW_FAILURE, exp_mod.DRIFTED, exp_mod.FIXED) and why:
            print(f"      {why}")

    for entry in broken:
        print(f"  ! <unloadable> [{exp_mod.MALFORMED}]\n      {entry}")

    # An expectation naming a case that does not exist is dead config, and left
    # unreported it is this repo's signature defect committed by its own detector:
    # "case absent" and "case passed" both produce no verdict, so a stale entry for a
    # renamed or deleted case survives indefinitely while appearing to hold. Found by
    # deliberately falsifying the reconciliation mechanism rather than by reading it.
    known = {c.name for c in cases}
    orphans = sorted(set(expectations) - known)
    for name in orphans:
        print(f"  ! {name} [{exp_mod.MALFORMED}]\n      expectation names a case that does "
              f"not exist — rename or delete it; it is currently acknowledging nothing")

    counts = ledger_mod.summarize(rows)
    print("\n" + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if broken:
        print(f"unloadable={len(broken)}")
    if orphans:
        print(f"orphan-expectations={len(orphans)}")

    if not args.no_ledger and rows:
        path = ledger_mod.append(header, rows)
        print(f"ledger: {path}")

    verdicts = {v for _, v in rows}
    if broken or orphans or exp_mod.MALFORMED in verdicts:
        print("\nA case is broken. That is not evidence about the code under test.",
              file=sys.stderr)
        return 3
    if exp_mod.NEW_FAILURE in verdicts or exp_mod.DRIFTED in verdicts:
        print("\nA new or changed failure. Triage it before acknowledging it.",
              file=sys.stderr)
        return 1
    if exp_mod.FIXED in verdicts:
        print("\nA triaged defect now passes. Delete its expectation in the same change "
              "that fixed it.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
