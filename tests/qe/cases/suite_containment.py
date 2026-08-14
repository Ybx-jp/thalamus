"""The in-loop suite must not collect this tree, and the check for that must not be prose.

This suite carries entries that are *supposed* to be red. `pyproject.toml` sets
`testpaths = ["tests"]`, and `tests/qe/` is inside it — so nothing but the **filenames**
keeps `uv run pytest` from collecting a deliberately red corpus into the suite developers
run to decide whether their change is good. One file added here as `test_ingress.py`, or
one `*_test.py`, and dev's suite inherits known-red cases it has no expectations file to
absorb.

The failure that follows is the one docs/13 is written about. A permanently red in-loop
suite is not a loud failure; it is a quiet one, because a gate that is always red stops
being read — developers "may lose trust in their test suites and stop considering
failures even if some of them are caused by real faults" (arXiv 2111.03382, the same
finding that motivated the expectations file). The repair reached for under that pressure
is to mute the case, and muting is what this whole tree is built to resist.

The suite README states the invariant and hands the reader a command:
`uv run pytest --collect-only -q | grep -c tests/qe`, *the answer must be 0*. That is a
procedure someone runs, which means it is a procedure someone skips — and the moment it
matters most is the moment it is least likely to be run, because the file that breaks it
is added by someone who did not know the rule existed. So it is asserted here instead.

**Asserted as an outcome, not as a naming convention.** Checking that no file matches
`test_*.py` would restate the mechanism and miss every other way collection could reach
this tree: a `conftest.py` adding a path, a changed `testpaths`, a `python_files` override
in `pyproject.toml`, a plugin. The subject is collection itself, so the case runs the
collector and reads what it collected.

**The control is that the collector collected.** "Zero cases collected from `tests/qe`" is
also what a pytest that failed to start, errored during collection, or was pointed at an
empty directory reports — and that reading is not hypothetical here, since this suite
deliberately does not depend on pytest working. So the run must also show dev's own suite
being collected in the same invocation; a collection that finds nothing anywhere is
reported as a broken check rather than as a clean tree.

**Shown capable of going red.** Drop a file named `test_canary.py` into `tests/qe/cases/`
containing a single `def test_x(): assert False`, re-run: the case reports
`invariant-falsified` naming that node id. Delete it and the case returns to green. It is
left out of the tree rather than created by the case, because a case that writes a
`test_*.py` file into this directory — even briefly, even cleaning up after itself — is
the defect, and a crash between the write and the cleanup would leave it behind.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_REPO = Path(__file__).resolve().parents[3]
_FORBIDDEN = "tests/qe"


def run() -> Finding | None:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(_REPO), capture_output=True, text=True, timeout=600, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the collector could not be run, so 'this tree is not collected' and "
                    "'nothing was collected' are the same result",
            witness=f"{type(exc).__name__}: {exc}",
            site="tests/qe/cases/suite_containment.py",
        )

    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if "::" in ln]

    # CONTROL: the collector must have collected dev's suite. Without this, a pytest that
    # died on an import error reports the same empty intersection as perfect containment —
    # and pytest is a dev-only extra this suite is designed to run without, so "it did not
    # work" is a live possibility rather than a defensive hypothetical.
    elsewhere = [ln for ln in lines if not ln.startswith(_FORBIDDEN)]
    if len(elsewhere) < 100:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the collector reported almost no tests anywhere, so its silence "
                    "about this tree is evidence about the collector rather than about "
                    "containment",
            witness=f"rc={proc.returncode}, {len(elsewhere)} node(s) collected outside "
                    f"{_FORBIDDEN}; stderr={(proc.stderr or '').strip()[:300]}",
            site="tests/qe/cases/suite_containment.py",
        )

    collected = [ln for ln in lines if ln.startswith(_FORBIDDEN)]
    if not collected:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "the in-loop pytest suite now collects the adversarial tree, so entries that "
            "are deliberately red are being run as if they were regressions — the "
            "developer-facing suite goes permanently red and the pressure lands on muting "
            "the cases"
        ),
        witness=(f"{len(collected)} node(s) collected from {_FORBIDDEN}: "
                 + "; ".join(collected[:6])
                 + (f" (+{len(collected) - 6} more)" if len(collected) > 6 else "")),
        site="tests/qe/ (filename containment) vs pyproject.toml testpaths",
    )


CASE = Case(
    name="in-loop-suite-collects-nothing-from-this-tree",
    tier=Tier.FAST,
    # pytest is already substrate for this tier — three cases borrow probe helpers out of
    # dev's suite — but it is declared here because this case *is* about the collector.
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="`pytest` must collect no node from tests/qe, or the in-loop suite inherits "
            "an intentionally red corpus",
    run=run,
)
