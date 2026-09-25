"""The agentic plan's digest must never exceed its cap, and a refused delivery must
never leak a partial result.

docs/14-memory-reflex.md §7 (the qe companion list for thalamus PR #280) names this as
one control: "a digest never exceeds the cap, and a result crossing the session budget
is dropped whole — control: an oversized set." `tests/test_reflex_worker.py` already
covers both halves, but with a single kept node each time
(`test_a_served_job_leaves_a_ready_digest_under_the_cap_naming_its_trigger`,
`test_a_ready_result_that_would_cross_the_budget_is_dropped_whole`) — a fixture that
size can pass `pack_digest` without ever exercising the branch that actually drops a
line, and it never asks what happens to the *pointer file* a refused delivery leaves
behind. This case drives the same two code paths — `reflex_worker.run_job` and
`reflex_worker.deliver` — under a fixture built to overrun both, and adds the pointer
file's fate as its own assertion.

**The digest half.** The plan is stubbed to keep 60 synthetic nodes — twelve times
word match's own `MAX_CANDIDATES` cap (#251) and far more than `agentic.MAX_KEEP` (5)
would ever let a real loop choose, which is the point: `run_job` packs whatever
`AgenticResult.kept` holds, so this is the direct way to hand it more than any digest
could carry. Positive control: the pointer file `run_job` writes for all 60 records
must itself exceed `DIGEST_CHAR_CAP` — otherwise a capped digest below would not show
anything was dropped, only that the fixture happened to fit. The invariant: the ready
digest's own `chars` field, and `len(digest)`, must stay at or under `DIGEST_CHAR_CAP`
regardless, with at least one full synthetic record surviving in it and a "N more in
the file" line naming what did not.

**The budget half.** The same oversized job is run twice, under two session ids. The
first (`s1`) delivers against an empty budget — the positive control that this fixture
*can* be delivered at all, so a refusal on the second cannot be read as "oversized jobs
never deliver". The second (`s2`) preloads its session's firing ledger to
`SESSION_CHAR_BUDGET - 10`, ten characters short of the ceiling and far short of the
oversized digest's size, then delivers: `deliver()` must return no digest, record a
`budget` outcome, and — the assertion dev's suite does not make — unlink the ready
result's pointer file, since nothing was delivered to point at it. `s1`'s pointer file,
by contrast, must survive its successful delivery: the two runs together are what show
"dropped whole" means the delivery, not the on-disk record a successful one keeps.

Hermetic, borrowing `test_reflex_worker.py`'s `_memory`, `_plan`, `_job_line`, `_claim`
and `_run` helpers rather than reimplementing a claimed job or a stubbed plan, per
`ingress_floor.py`'s precedent (`tests/qe/README.md`, "The `dev` extra is a
prerequisite of the fast tier") — `test_reflex_worker.py` imports `pytest` at module
scope, so this case dies on import and reports MALFORMED without the `dev` extra.

**Shown capable of going red.** Loosen `pack_digest`'s `room` budget in
`src/thalamus/harness/reflex.py` (e.g. drop the `- len(frame)` term) and rerun: the
ready digest's `chars` exceeds `DIGEST_CHAR_CAP` and this case reports
`INVARIANT_FALSIFIED` with that length as the witness. Comment out the
`Path(...).unlink(missing_ok=True)` call in `reflex_worker.deliver`'s budget branch and
rerun: `s2`'s pointer file survives its refusal and this case reports
`INVARIANT_FALSIFIED` naming it. `qe` does not write `src/thalamus/harness/`, so
neither mutation is carried in the case.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_TESTS = Path(__file__).resolve().parents[2]
_SITE = "tests/qe/cases/reflex_worker_digest_and_budget_drop_whole.py::run"
_NODE_COUNT = 60
_SUMMARY = ("An oversized synthetic candidate record padding the digest well past "
            "its own character cap.")


def _load_fixture():
    """Borrow dev's worker fixture rather than minting a second stubbed graph read.

    Same reuse rationale as `reflex_dedup_key_stability.py::_load_fixture`: if the two
    ever diverge, a green result here says nothing about `test_reflex_worker.py`'s own
    fixture.
    """
    if str(_TESTS) not in sys.path:
        sys.path.insert(0, str(_TESTS))
    import test_reflex_worker as _trw  # noqa: PLC0415

    return _trw


def run() -> Finding | None:
    from thalamus.harness import agentic, reflex_worker  # noqa: PLC0415
    from thalamus.harness.reflex import DIGEST_CHAR_CAP, SESSION_CHAR_BUDGET, Firing  # noqa: PLC0415
    from thalamus.substrate.vocabulary import Row  # noqa: PLC0415

    trw = _load_fixture()
    kept_nodes = [f"scope:main:claim:qe-oversized-{i:03d}" for i in range(_NODE_COUNT)]

    original_scopes = reflex_worker.available_scopes
    original_resolve = reflex_worker.vocabulary.resolve
    original_rows_for = reflex_worker.vocabulary.rows_for
    original_run = agentic.run
    reflex_worker.available_scopes = lambda: ["main"]
    reflex_worker.vocabulary.resolve = lambda g, node, scope, knowledge: trw._memory(node)
    reflex_worker.vocabulary.rows_for = lambda g, vids, scope, knowledge: [
        Row(vid=v, kind="decision", tier=1, date="2026-09-12", summary=_SUMMARY)
        for v in vids
    ]
    agentic.run = trw._plan(kept=kept_nodes)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # --- the digest half: run once, under s1 ------------------------------
            claimed = trw._claim(tmp_path, session="s1")
            outcome = trw._run(tmp_path, claimed)
            if outcome != "ready":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "the oversized fixture did not reach 'ready', so nothing "
                        "below demonstrates the digest cap holding under stress"
                    ),
                    witness=f"run_job outcome={outcome!r}",
                    site=_SITE,
                )
            ready_path = next(tmp_path.glob("queue/s1/session/ready/*.json"))
            ready_s1 = json.loads(ready_path.read_text())

            if len(ready_s1["handles"]) != _NODE_COUNT:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "run_job did not keep all 60 synthetic candidates, so the "
                        "candidate-set is not actually oversized and a capped digest "
                        "below would prove nothing"
                    ),
                    witness=f"handles={len(ready_s1['handles'])} expected={_NODE_COUNT}",
                    site=_SITE,
                )

            pointer_text_s1 = Path(ready_s1["pointer"]).read_text(encoding="utf-8")
            # POSITIVE CONTROL: the pointer file — every candidate, uncapped — must
            # itself already exceed DIGEST_CHAR_CAP, or a capped digest proves nothing
            # about dropping since there may have been nothing to drop.
            if len(pointer_text_s1) <= DIGEST_CHAR_CAP:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "the oversized fixture's own pointer file (all 60 records, "
                        "uncapped) did not exceed DIGEST_CHAR_CAP, so a digest under "
                        "the cap below would not demonstrate anything was dropped"
                    ),
                    witness=f"pointer_chars={len(pointer_text_s1)} "
                             f"DIGEST_CHAR_CAP={DIGEST_CHAR_CAP}",
                    site=_SITE,
                )

            digest_s1 = ready_s1["digest"]
            if ready_s1["chars"] > DIGEST_CHAR_CAP or len(digest_s1) > DIGEST_CHAR_CAP:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "run_job served a digest over DIGEST_CHAR_CAP for a job that "
                        "kept 60 candidates — the digest must never exceed its cap "
                        "regardless of how many nodes the plan chose"
                    ),
                    witness=f"chars={ready_s1['chars']} len(digest)={len(digest_s1)} "
                             f"DIGEST_CHAR_CAP={DIGEST_CHAR_CAP}",
                    site="src/thalamus/harness/reflex.py::pack_digest",
                )
            if "more in the file" not in digest_s1:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "an oversized job's digest fit under DIGEST_CHAR_CAP without "
                        "reporting anything held back, even though its pointer file "
                        "holds far more than the cap allows — the digest is either "
                        "silently incomplete or the accounting is wrong"
                    ),
                    witness=f"digest={digest_s1!r}",
                    site="src/thalamus/harness/reflex.py::pack_digest",
                )
            if _SUMMARY not in digest_s1:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "none of the 60 candidates' full summary text survived in the "
                        "digest — dropping whole lines should still leave the ones "
                        "that fit intact and unshortened, not empty"
                    ),
                    witness=f"digest={digest_s1!r}",
                    site="src/thalamus/harness/reflex.py::pack_digest",
                )

            # --- the budget half: s1 (unsaturated) delivers; s2 (saturated) refused ---
            digest = reflex_worker.deliver(tmp_path, session_id="s1", agent_id="")
            if not digest:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: the same oversized job did not "
                        "deliver at all against an empty session budget, so a "
                        "refusal under a saturated budget below cannot be told apart "
                        "from oversized jobs never delivering for any reason"
                    ),
                    witness=f"deliver(s1)={digest!r}",
                    site=_SITE,
                )
            if not Path(ready_s1["pointer"]).is_file():
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "a successfully delivered job's pointer file was removed — "
                        "only a budget-refused delivery should unlink it, since a "
                        "served digest still names the file to the agent"
                    ),
                    witness=f"pointer={ready_s1['pointer']!r}",
                    site="src/thalamus/harness/reflex_worker.py::deliver",
                )

            claimed2 = trw._claim(tmp_path, session="s2", use_id="t9")
            outcome2 = trw._run(tmp_path, claimed2)
            if outcome2 != "ready":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="the second oversized fixture (s2) did not reach 'ready'",
                    witness=f"run_job outcome={outcome2!r}",
                    site=_SITE,
                )
            ready_s2 = json.loads(
                next(tmp_path.glob("queue/s2/session/ready/*.json")).read_text()
            )

            sessions_dir = tmp_path / "sessions"
            sessions_dir.mkdir(exist_ok=True)
            (sessions_dir / "s2.jsonl").write_text(
                Firing(
                    ts="", session_id="s2", agent_id="", outcome="served",
                    injected_chars=SESSION_CHAR_BUDGET - 10,
                ).to_json() + "\n"
            )
            refused = reflex_worker.deliver(tmp_path, session_id="s2", agent_id="")
            if refused != "":
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "a result that would cross the session's char budget was "
                        "delivered anyway instead of being dropped whole"
                    ),
                    witness=f"deliver(s2)={refused!r}",
                    site="src/thalamus/harness/reflex_worker.py::deliver",
                )
            from thalamus.harness import reflex_queue  # noqa: PLC0415
            outcomes = reflex_queue.load_outcomes(tmp_path)
            if not outcomes or outcomes[-1].get("outcome") != "budget":
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "a delivery refused for crossing the session budget left no "
                        "'budget' outcome row, so a refused session cannot see why "
                        "the reflex stopped delivering"
                    ),
                    witness=f"last_outcome={outcomes[-1] if outcomes else None!r}",
                    site="src/thalamus/harness/reflex_worker.py::deliver",
                )
            if Path(ready_s2["pointer"]).exists():
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "a delivery refused for crossing the session budget left its "
                        "pointer file behind — nothing was delivered to reference it, "
                        "so it is an orphaned on-disk record of a firing the agent "
                        "never saw"
                    ),
                    witness=f"pointer={ready_s2['pointer']!r}",
                    site="src/thalamus/harness/reflex_worker.py::deliver",
                )
            return None
    finally:
        reflex_worker.available_scopes = original_scopes
        reflex_worker.vocabulary.resolve = original_resolve
        reflex_worker.vocabulary.rows_for = original_rows_for
        agentic.run = original_run


CASE = Case(
    name="reflex-worker-digest-cap-and-budget-drop-whole-under-an-oversized-set",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "an oversized agentic result's digest never exceeds DIGEST_CHAR_CAP, and a "
        "delivery that would cross the session budget is dropped whole with its "
        "pointer file removed"
    ),
    run=run,
)
