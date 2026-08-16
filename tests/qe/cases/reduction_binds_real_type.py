"""A reduction onto the wire must read only what the real type carries.

Found live, 2026-08-15, against the d4v2 console branch: `attach_blocked` read
`session.status_updated_at` from a descriptor that did not carry it, raising
`AttributeError` on every poll that could read a descriptor at all — the common case
in production. The whole suite was green throughout, because the liveness tests hand
the reduction a hand-written session object and **a fake grows whatever attribute the
code asks it for**. The one shape that cannot fail was the only shape under test. It
was caught by a human reading a diff at landing time, which is not a control.

The general form, and the reason this is a case rather than a unit test: *a test that
constructs its own copy of the thing under test cannot see that thing drift.*

Derived from the reduction's own source rather than from a list of field names. A
hand-kept list is a second owner of what the code reads — the day a fourth attribute
is read the fake grows it, the list never hears about it, and the binding is
decorative again. That is the original defect with one more name in front of it. The
first repair after the AttributeError *was* such a list, covering three `session.*`
names, and it left `dispatch.BUSY_STATUS` — read by the same function, pinned nowhere
but inside the fake — free to be renamed without a single test going red.

Syntactic on purpose. Calling the reduction and observing what it touches is what the
fake already does, and it cannot see an attribute on a branch the one constructed
input never reaches.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
import textwrap

from ..model import Case, FailureClass, Finding, Substrate, Tier

# Reductions that cross into a wire payload or a console surface, each with the
# receiver whose attributes must exist on the real type. Grown when a new reduction
# reaches the wire, not when one breaks.
REDUCTIONS = (
    ("thalamus.console.server", "attach_blocked"),
)


def _reads(fn, receiver: str) -> set[str]:
    """Every `<receiver>.<name>` in a function's own source."""
    source = textwrap.dedent(inspect.getsource(fn))
    return set(re.findall(rf"\b{re.escape(receiver)}\.([A-Za-z_][A-Za-z0-9_]*)", source))


def run() -> Finding | None:
    import importlib  # noqa: PLC0415

    from thalamus.harness import dispatch  # noqa: PLC0415
    from thalamus.harness.quick import LiveSession  # noqa: PLC0415

    carried = {f.name for f in dataclasses.fields(LiveSession)}
    drifted: list[str] = []
    total_reads = 0

    for module_name, fn_name in REDUCTIONS:
        module = importlib.import_module(module_name)
        fn = getattr(module, fn_name, None)
        if fn is None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=f"{module_name}.{fn_name} does not exist, so this case is "
                        f"asserting over nothing",
                witness=f"{module_name} has no attribute {fn_name}",
                site="tests/qe/cases/reduction_binds_real_type.py",
            )

        session_reads = _reads(fn, "session")
        module_reads = _reads(fn, "dispatch")
        total_reads += len(session_reads) + len(module_reads)

        for name in sorted(session_reads):
            if name not in carried:
                drifted.append(
                    f"{fn_name} reads session.{name}; LiveSession carries "
                    f"{sorted(carried)}")
        for name in sorted(module_reads):
            if not hasattr(dispatch, name):
                drifted.append(
                    f"{fn_name} reads dispatch.{name}, which harness.dispatch does "
                    f"not define")

    # CONTROL: the scan must actually see reads. A regex that matches nothing turns
    # every assertion above into a statement about an empty set, which passes forever
    # and is indistinguishable from a clean reduction. This is the failure mode the
    # case exists to catch, so it is checked on the case itself.
    if total_reads == 0:
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the source scan found no attribute reads at all, so this case "
                    "cannot tell a bound reduction from an unbound one",
            witness=f"scanned {len(REDUCTIONS)} reduction(s), matched 0 reads",
            site="tests/qe/cases/reduction_binds_real_type.py::_reads",
        )

    if not drifted:
        return None

    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "a reduction onto the wire reads an attribute its real input does not "
            "carry — the tests cannot see it because they hand the reduction a fake, "
            "and a fake grows whatever attribute the code asks it for"
        ),
        witness="; ".join(drifted),
        site="src/thalamus/console/server.py::attach_blocked",
    )


CASE = Case(
    name="wire-reductions-bind-to-the-real-type",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="every attribute a wire reduction reads must exist on the type production "
            "actually passes it, not merely on the fake its tests construct",
    run=run,
)
