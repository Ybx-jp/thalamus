"""Guards on the spec itself, runnable with no VM and no graph.

The matrix is expensive to run and slow to fail, so the properties that can be
checked by reading the spec are checked by reading the spec. This is the part of
the harness that gates a change to the harness.

    python ops/qe-install-matrix/lint.py

Exit 0 clean, 1 with findings. Deliberately not named `test_*` — see the
containment rule in tests/qe/README.md.
"""

from __future__ import annotations

import sys

import checks
import spec


def _absence_shaped(check: spec.Check) -> bool:
    """Does this check assert that something is NOT the case?

    Kept lexical and slightly over-eager on purpose. A false positive costs one
    sentence of `control`; a false negative is a check that passes forever.
    """
    haystack = f"{check.name} {check.summary}".lower()
    return any(marker in haystack for marker in (
        "must not", "no ", "never", "leaves no", "does not", "is not", "without",
        "absent", "nothing",
    ))


def findings() -> list[str]:
    out: list[str] = []

    for check in spec.CHECKS:
        if _absence_shaped(check) and not check.control:
            out.append(
                f"{check.name}: asserts an absence with no positive control. "
                "'Nothing was observed' and 'the step never ran' are the same "
                "output otherwise (tests/qe/README.md)."
            )

    names = [c.name for c in spec.CHECKS]
    for dupe in {n for n in names if names.count(n) > 1}:
        out.append(f"{dupe}: duplicate check name; results are keyed by name.")

    config_names = [c.name for c in spec.CONFIGS]
    for dupe in {n for n in config_names if config_names.count(n) > 1}:
        out.append(f"{dupe}: duplicate config name.")

    # Every phase a check names must be reachable: either a step produces it or it
    # is one of the phases the runner synthesizes. A check pinned to a phase the
    # sequence never enters is a check that never runs, which reads as a pass.
    synthesized = {spec.Phase.PREFLIGHT, spec.Phase.GRAPH_READY, spec.Phase.MOVED,
                   spec.Phase.CONSOLE}
    reachable = {s.phase for s in spec.STEPS} | synthesized
    for check in spec.CHECKS:
        if check.phase not in reachable:
            out.append(
                f"{check.name}: pinned to phase {check.phase.value}, which no step "
                "produces and the runner does not synthesize — it would never run."
            )

    # `fixed` only means anything relative to an issue: it is the flag that withdraws
    # a tag's absolution, and there is nothing to withdraw where no tag was given.
    for check in spec.CHECKS:
        if check.fixed and not check.issue:
            out.append(
                f"{check.name}: marked fixed but names no issue. `fixed` withdraws "
                "the absolution an issue number grants a red result; on an untagged "
                "check it reads as a claim with no referent."
            )
    for config in spec.CONFIGS:
        if config.fixed and not config.issue:
            out.append(f"{config.name}: marked fixed but names no issue.")

    # A config and the checks that observe its defect must agree about whether that
    # defect is still there. Split state is how one half goes on absolving after the
    # other half was repaired.
    for config in spec.CONFIGS:
        if not config.issue:
            continue
        peers = [c for c in spec.CHECKS if c.issue == config.issue]
        if peers and any(c.fixed for c in peers) != all(c.fixed for c in peers) \
                or (peers and peers[0].fixed != config.fixed):
            out.append(
                f"#{config.issue}: config {config.name!r} and its check(s) disagree "
                "about `fixed`, so the same defect is both expected to reproduce and "
                "expected to pass depending on which one a run consults."
            )

    # A config naming an issue should have at least one check that can observe it,
    # otherwise the variant costs a full boot and asserts nothing specific.
    check_issues = {c.issue for c in spec.CHECKS if c.issue}
    for config in spec.CONFIGS:
        if config.issue and config.issue not in check_issues:
            out.append(
                f"{config.name}: reproduces issue #{config.issue} but no check "
                "names that issue, so the variant boots a VM and observes nothing "
                "specific to it."
            )

    # Every check must be either implemented or explicitly deferred with a reason.
    # The failure this closes is a check that has no evaluator and no entry: it lands in
    # `not_evaluated` with no cause, which reads exactly like a check whose evidence was
    # missing that day. Accounting for the gap is what keeps "we did not build it" from
    # being reported as "we could not see it".
    spec_names = {c.name for c in spec.CHECKS}
    implemented = set(checks.EVALUATORS)
    deferred = set(checks.DEFERRED)

    for name in sorted(implemented & deferred):
        out.append(
            f"{name}: is both implemented and deferred in checks.py; one of the two "
            "is stale and the deferral reason would be reported over a real result."
        )
    for name in sorted(spec_names - implemented - deferred):
        out.append(
            f"{name}: has no evaluator in checks.py and no DEFERRED reason, so it "
            "would report as not_evaluated with no cause — indistinguishable from a "
            "check whose evidence was missing."
        )
    for name in sorted((implemented | deferred) - spec_names):
        out.append(
            f"{name}: checks.py carries it but spec.CHECKS does not, so it is "
            "evaluated and never reported."
        )
    for name in sorted(deferred):
        if not checks.DEFERRED.get(name, "").strip():
            out.append(f"{name}: deferred with an empty reason.")

    if not spec.known_defect_issues():
        out.append(
            "known_defect_issues() is empty: the harness has no positive control "
            "on itself and a fully green run would be indistinguishable from a "
            "run that observed nothing."
        )

    return out


def main() -> int:
    found = findings()
    print(f"vm spec lint — {len(spec.CHECKS)} checks "
          f"({len(checks.EVALUATORS)} implemented, {len(checks.DEFERRED)} deferred), "
          f"{len(spec.CONFIGS)} configs, {len(spec.STEPS)} steps")
    for line in found:
        print(f"  FAIL {line}")
    if not found:
        print("  clean")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
