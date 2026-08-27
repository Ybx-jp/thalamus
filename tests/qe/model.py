"""The typed vocabulary of the adversarial suite.

Shape follows `contract/probes.py`: frozen dataclasses, an enum per axis, and checks
resolved by *name* through a registry rather than by holding a callable in the data.
The registry indirection is what lets a version-controlled expectations file name a
check without importing it, and what makes an unresolvable name a MALFORMED result
rather than a silent skip.

This tree is deliberately NOT shipped in the wheel and deliberately NOT collected by
pytest. Both are the same decision: the suite carries known-red entries naming defects
that are real and unfixed, so shipping it would hand every installer a bug oracle
against the release they just installed. `pyproject.toml` sets `testpaths = ["tests"]`,
so containment here rests on filenames — nothing in this tree may match `test_*.py` or
`*_test.py`, or dev's in-loop suite inherits an intentionally red corpus.

Three vocabularies, deliberately separate:

- `Substrate` is what a case NEEDS. Absent substrate yields SKIPPED, never a failure —
  a suite that fails on a box without docker is reporting on the box, not the code.
- `Outcome` is what HAPPENED.
- `FailureClass` is WHY it failed, drawn from a closed set the case declares up front.
  That is the part which stops a known-red entry from absorbing a different defect at
  the same site: an acknowledged failure carries its class, and a failure arriving with
  a class the entry did not record is drift, which is a failure and not an ack.
"""

from __future__ import annotations

import shutil
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Substrate(str, Enum):
    """What a case needs in order to mean anything.

    HERMETIC is the absence of a requirement, stated positively so a case must declare
    its needs rather than defaulting into them by omission.
    """

    HERMETIC = "hermetic"
    NEEDS_GRAPH = "needs-graph"
    NEEDS_TMUX = "needs-tmux"
    NEEDS_DOCKER = "needs-docker"
    NEEDS_MODEL = "needs-model"
    NEEDS_NODE = "needs-node"
    NEEDS_JQ = "needs-jq"


class Tier(str, Enum):
    """FAST gates every push; DEEP runs where real substrate exists.

    A case's tier is a claim about cost and blast radius, not about importance. The
    unliftability property is FAST because it is a pure function over generated
    strings, and it is also the most serious finding in the suite.
    """

    FAST = "fast"
    DEEP = "deep"


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    # The check itself is broken — an unresolvable name, or an exception that is not a
    # returned Finding. Never a pass, and never absorbed by an expectation.
    MALFORMED = "malformed"


class FailureClass(str, Enum):
    """The closed set of reasons a case in this suite may fail.

    Closed on purpose, and the closure is the whole mechanism. `thalamus ceremony ack`
    (bc3946d) draws its discrimination from ten categories computed by the auditor;
    these are *emitted by the failing case itself*, which is weaker — a case can emit
    the wrong class where an auditor cannot. The mitigation is that there is no OTHER
    member: a case with nowhere to put its failure must grow this enum in a reviewed
    change rather than widening it at runtime.
    """

    FAILED_OPEN = "failed-open"
    GATE_ORDERING = "gate-ordering"
    UNENFORCED_SIGNAL = "unenforced-signal"
    INVARIANT_FALSIFIED = "invariant-falsified"
    COLLAPSED_SENTINEL = "collapsed-sentinel"
    DOC_CODE_DRIFT = "doc-code-drift"
    BOUNDARY_LEAK = "boundary-leak"


@dataclass(frozen=True)
class Finding:
    """What a failing case returns. `witness` is the point of the whole suite.

    A failure that cannot show the input which produced it is a claim, not evidence.
    `witness` carries the concrete thing — the string that lifted the floor, the exit
    code the guard returned — so a ledger row is reproducible without a rerun.
    """

    failure_class: FailureClass
    summary: str
    witness: str = ""
    # Where the defect lives, not where the assertion is written.
    site: str = ""


@dataclass(frozen=True)
class Case:
    """One adversarial case.

    `run` returns None to pass, or a Finding to fail. It must not raise for an ordinary
    failure: a raised exception is MALFORMED, meaning the check is broken, which is a
    different and louder thing than the code under test being broken.
    """

    name: str
    tier: Tier
    substrate: tuple[Substrate, ...]
    # The closed set THIS case may emit. A case returning a class outside its own
    # declaration is MALFORMED, because an expectation recorded against it could not
    # have anticipated that class.
    classes: tuple[FailureClass, ...]
    summary: str
    run: Callable[[], Finding | None] = field(repr=False)
    # The GitHub issue whose defect this case reproduces, or 0 for a case guarding a
    # property no filed defect covers. Same field, same meaning and the same pair of
    # rules as `install/spec.py::Check` — a red naming an issue has reproduced
    # something already filed, and a red naming nothing has found something new.
    issue: int = 0
    #: The issue is closed and this case is now the regression guard for it, so it is
    #: expected to PASS. `run.py` refuses to reconcile a fixed case against an entry in
    #: `expectations.json`: an issue number absolves a red result, and an untouched tag
    #: goes on absolving long after the defect is gone. Flip this in the change that
    #: closes the issue, and delete the expectation in the same one.
    fixed: bool = False


@dataclass(frozen=True)
class CaseResult:
    name: str
    outcome: Outcome
    tier: Tier
    detail: str = ""
    finding: Finding | None = None
    # Populated only when substrate was missing, and it names WHICH. "Skipped" with no
    # reason is exactly the collapsed sentinel this suite exists to hunt.
    missing: tuple[Substrate, ...] = ()
    duration_s: float = 0.0


def _graph_reachable(host: str = "localhost", port: int = 8182) -> bool:
    """A TCP connect, not a Gremlin handshake.

    Deliberately shallow: this answers "is something listening" so the runner can skip,
    and nothing more. A deeper probe would need the driver, and a substrate check that
    imports the thing it is checking for cannot report that thing's absence.
    """
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def available(substrate: Substrate) -> bool:
    """Is this substrate present on THIS box, right now?

    Every answer is a live probe rather than a cached capability, because a stale yes
    is how a skip becomes a spurious failure.
    """
    if substrate is Substrate.HERMETIC:
        return True
    if substrate is Substrate.NEEDS_GRAPH:
        return _graph_reachable()
    if substrate is Substrate.NEEDS_TMUX:
        return shutil.which("tmux") is not None
    if substrate is Substrate.NEEDS_DOCKER:
        return shutil.which("docker") is not None
    if substrate is Substrate.NEEDS_NODE:
        return shutil.which("node") is not None
    if substrate is Substrate.NEEDS_JQ:
        return shutil.which("jq") is not None
    if substrate is Substrate.NEEDS_MODEL:
        # Presence of the binary, not of credentials or quota. A case needing a real
        # model call that finds an unauthenticated CLI should FAIL rather than skip:
        # the binary is the declarable precondition, auth state is a runtime fact the
        # case itself has to report on.
        return shutil.which("claude") is not None
    return False


def missing_substrate(case: Case) -> tuple[Substrate, ...]:
    return tuple(s for s in case.substrate if not available(s))
