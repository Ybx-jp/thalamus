"""Every member of the capability checker's vocabulary must have a producer.

Corpus record: `probes-docstring-promises-unbuilt-field` (`bf24b5a`). The general form —
a docstring promising a capability the module lacks — is prose and not mechanically
detectable. The narrow mechanical instance is: an enum member nothing emits is dead, and
a consumer that branches on it is unreachable code guarding a state that cannot occur.

`contract/probes.py` is the module that exists because *nothing ever asked the CLI
again* (lab/054). Its `Condition` enum records the mode an observation was taken under,
and the module's own reasoning turns on that distinction: a `<timestamp>` seen in print
mode is one inference away from unwiring the clock tier for interactive sessions nobody
looked at. `Condition.PARSE` is produced. `PRINT` and `INTERACTIVE` are declared and
emitted by nothing, so no probe result can ever carry them and no reader can act on the
distinction they describe.

The control is the module's own sibling. `Outcome` — the five-member vocabulary of what
a re-probe found — is scanned by the same pass, and every member of it is produced. So a
run reporting dead members in one enum and none in the other is reporting on the code
rather than on a scanner that stopped matching, and a run reporting nothing dead
anywhere would mean the scan broke.

Declared-ahead-of-use is a real and legitimate pattern in this repo —
`contract/ontology.py` declares edges it does not yet write and says so in a comment
next to them. That is why this case is scoped to the probe vocabulary rather than run
over every enum in `src/`: a repo-wide version would need to distinguish "not built yet"
from "cannot be built", which is the judgement the corpus record already marked as not
mechanically detectable.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SRC = Path(__file__).resolve().parents[3] / "src" / "thalamus"
_DEFINING_FILE = "contract/probes.py"
# The vocabulary under test, and the sibling that acts as its control.
_SUBJECT, _CONTROL = "Condition", "Outcome"


def _members(tree: ast.Module, enum_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == enum_name:
            return [
                target.id
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for target in stmt.targets
                if isinstance(target, ast.Name)
            ]
    return []


def _produced(enum_name: str, members: list[str]) -> dict[str, int]:
    """How many times each member is named outside its own definition.

    Counted over attribute access (`Condition.PARSE`) across the whole package, which
    over-counts rather than under-counts: a member named anywhere at all — even only in
    a comparison — is not dead in the sense this case claims. The finding is therefore
    conservative, which is the right direction for a case that accuses code of carrying
    a state nothing can reach.
    """
    counts = dict.fromkeys(members, 0)
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == enum_name
                and node.attr in counts
            ):
                counts[node.attr] += 1
    return counts


def run() -> Finding | None:
    defining = _SRC / _DEFINING_FILE
    if not defining.is_file():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the probe module was not found, so 'no dead member' means 'nothing "
                    "was read'",
            witness=str(defining),
            site=f"src/thalamus/{_DEFINING_FILE}",
        )

    tree = ast.parse(defining.read_text(encoding="utf-8"))
    subject = _members(tree, _SUBJECT)
    control = _members(tree, _CONTROL)
    if not subject or not control:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=f"{_SUBJECT} or {_CONTROL} could not be read out of the probe module, "
                    "so this case would report a clean vocabulary either way",
            witness=f"{_SUBJECT}={subject}, {_CONTROL}={control}",
            site=f"src/thalamus/{_DEFINING_FILE}",
        )

    control_counts = _produced(_CONTROL, control)
    control_dead = sorted(name for name, hits in control_counts.items() if hits == 0)
    # CONTROL: every member of the sibling vocabulary is produced. If one reads as dead,
    # the scan is under-reaching (a member emitted through a path this pass cannot see)
    # and its verdict on the subject cannot be trusted either.
    if control_dead:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=f"the scan reports members of {_CONTROL} as unproduced, which is the "
                    "signature of a scan that cannot see producers rather than of dead "
                    "vocabulary",
            witness=f"{_CONTROL} counts={control_counts}",
            site="tests/qe/cases/probe_vocabulary.py::_produced",
        )

    counts = _produced(_SUBJECT, subject)
    dead = sorted(name for name, hits in counts.items() if hits == 0)
    if not dead:
        return None

    return Finding(
        failure_class=FailureClass.DOC_CODE_DRIFT,
        summary=(
            f"{_SUBJECT} declares states no code path can produce, so a probe result can "
            "never carry them and the distinction the module reasons from — an "
            "observation's mode — is not recorded by anything that observes"
        ),
        witness=f"{_SUBJECT} unproduced: {dead}; produced: "
                f"{ {k: v for k, v in counts.items() if v} }; "
                f"{_CONTROL} all produced: {control_counts}",
        site=f"src/thalamus/{_DEFINING_FILE}::{_SUBJECT}",
    )


CASE = Case(
    name="probe-vocabulary-has-no-dead-members",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.DOC_CODE_DRIFT, FailureClass.COLLAPSED_SENTINEL),
    summary="every Condition/Outcome member the probe checker declares must be emitted",
    run=run,
)
