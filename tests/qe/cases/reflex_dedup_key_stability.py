"""The reflex must not re-query the graph for a failure it already fired on.

`reflex.fire` keys dedup on `(session, agent, normalised anchor)` — `seen` is built from
every prior row's `keys` filtered to the *same* `agent_id` — so a rerun of an unchanged
test failure inside one session must not re-query the graph a second time, and a
subagent sharing the session id must still be able to fire on its own first encounter.
This is the strongest of the three controls the module's docstring names: "per-anchor
dedup keyed on `(session, agent, normalised anchor)`, so the same failing test on a
rerun does not refire." `tests/test_reflex.py::test_a_rerun_of_the_same_failure_does_not_refire_but_
another_agent_does` covers this fixture once, in dev's own loop; this case drives the
same property from `qe`'s side, which is not gated on dev's suite staying wired or
green.

The fixture borrows `test_reflex.py`'s own `_fake_recall`, `_memory` and `_fire` helpers
rather than reimplementing a stubbed `recall`, following `cases/ingress_floor.py`'s
precedent of reusing dev's fixture verbatim so the two suites cannot silently drift onto
different setups. Importing `test_reflex` pulls in `pytest` at module scope, the same
`dev`-extra prerequisite `ingress_floor.py` and `dispatch_addressability.py` already
carry (`tests/qe/README.md`, "The `dev` extra is a prerequisite of the fast tier").

**Positive control.** A firing tagged with a different `agent_id` sharing the same
`session_id` must still be served — without this, "the rerun was deduped" cannot be told
apart from "nothing in this session fires a second time no matter who asks", which would
report a dead reflex as a working one.

**Shown capable of going red.** Comment out the `if len(fresh) < MIN_NEW_ANCHORS:` guard
(or empty the `seen` set unconditionally) in `src/thalamus/harness/reflex.py::fire` and
rerun: the second, identical firing re-queries the graph and returns a second digest;
this case then reports `INVARIANT_FALSIFIED` with that digest as the witness. `qe`
does not write `src/thalamus/harness/`, so the mutation is not carried in the case.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_TESTS = Path(__file__).resolve().parents[2]


def _load_fixture():
    """Borrow dev's reflex fixture rather than minting a second stubbed `recall`.

    Same reuse rationale as `ingress_floor.py::_load_fixture`: if the two ever
    diverge, a green result here says nothing about `test_reflex.py`'s own fixture.
    """
    if str(_TESTS) not in sys.path:
        sys.path.insert(0, str(_TESTS))
    import test_reflex as _tr  # noqa: PLC0415

    return _tr


def run() -> Finding | None:
    from thalamus.harness import reflex, retrieval  # noqa: PLC0415

    tr = _load_fixture()
    original_recall = retrieval.recall
    original_scopes = reflex.available_scopes
    try:
        retrieval.recall = tr._fake_recall([tr._memory()])
        reflex.available_scopes = lambda: ["main", "qe"]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tr._fire(tmp_path)
            second = tr._fire(tmp_path)
            # CONTROL: a different agent sharing this session's id must still fire.
            third = tr._fire(tmp_path, agent_id="qe-dedup-probe-agent",
                              agent_type="general-purpose")

            if not first:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: the first firing did not serve a "
                        "digest at all, so 'served then deduped' cannot be "
                        "observed on the calls that follow it"
                    ),
                    witness=f"first_call_result={first!r}",
                    site="tests/qe/cases/reflex_dedup_key_stability.py::run",
                )
            if not third:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: a different agent_id sharing the "
                        "same session did not refire on the identical failure text, "
                        "so a deduped second call cannot be told apart from a "
                        "session that never fires twice for any reason"
                    ),
                    witness=f"first={bool(first)!r} third={third!r}",
                    site="tests/qe/cases/reflex_dedup_key_stability.py::run",
                )

            if second == "":
                return None

            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "firing the same session with identical failure output a second "
                    "time re-served a digest instead of deduping on the "
                    "(session, agent, anchor) key — a rerun of an unchanged test "
                    "failure re-queries the graph on every retry"
                ),
                witness=f"second_call_result={second!r}",
                site="src/thalamus/harness/reflex.py::fire",
            )
    finally:
        retrieval.recall = original_recall
        reflex.available_scopes = original_scopes


CASE = Case(
    name="reflex-dedup-key-is-session-agent-stable",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a rerun of the same failure text must dedupe; a different agent must still fire",
    run=run,
)
