"""A job whose session is no longer live must make no model call — checked against a
real session registry, with the live session as the control.

docs/14-memory-reflex.md §7's qe companion list names this: "a job whose session is no
longer live makes no model call (session_end), with the live session as the control."
`tests/test_reflex_worker.py::test_a_job_whose_session_has_ended_makes_no_model_call`
already covers `run_job`'s branch on `alive(session_id)`, but with `alive` replaced by
a plain `lambda s: False` / `lambda s: True` — the very thing this case exists not to
restate, because that mock never touches `reflex_worker.session_alive`, the function
`run_job` actually defaults to when the trigger hook does not override it
(`reflex_worker.py`'s own signature: `alive: Callable[[str], bool] = session_alive`).
`session_alive` reads `quick.live_sessions()` — pid plus `procStart` against `/proc`,
matching a session's own registry descriptor — and nothing in this tree drives that
real read end to end. A mock that always answers the same way cannot show the registry
lookup itself discriminates a real dead process from a real live one.

**The fixture.** Two session descriptors are written into a real (but temporary and
env-redirected) `$CLAUDE_CONFIG_DIR/sessions/`: one naming a process already exited
(`true`, waited on, so its pid is reaped and `/proc/<pid>` is gone) with a `procStart`
that cannot match anything now at that pid; one naming a process still running for the
duration of the check, with its actual `/proc/<pid>/stat` start-time field. Both a job
run against `reflex_worker.session_alive` directly, and the same function passed as
`run_job`'s `alive=` argument, are exercised in one subprocess with `CLAUDE_CONFIG_DIR`
redirected — `home_isolation.py`'s pattern, for the same reason: a bug here must not
consult, and must not appear to consult, the operator's real session registry.

**Positive control.** `session_alive()` on the live session's id must answer True and
`run_job` for it must reach the model-call point (recorded, not really called — the
model route is stubbed) — without this, a False/`session_end` result for the dead
session could just as well mean the registry read answers False for everything, dead
or alive.

**The invariant.** `session_alive()` on the dead session's id must answer False, and
`run_job` for that job must return `session_end` having made zero model calls.

**Shown capable of going red.** Pass `alive=lambda s: True` instead of `alive=
reflex_worker.session_alive` in `run_job`'s call from `reflex.py`'s enqueue path (there
is none today — this is the argument every real caller must keep supplying) and the
dead session's job would proceed to call the model; this case's control distinguishes
that from the real registry-backed function by exercising the function itself, not a
caller's promise to pass it correctly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_worker_session_end_no_model_call.py::run"

_PROBE = r"""
import json, sys
from pathlib import Path
from thalamus.harness import agentic, reflex_queue, reflex_worker
from thalamus.harness.agents import cli_for

dead_id, live_id, root = sys.argv[1], sys.argv[2], Path(sys.argv[3])

calls = []
agentic.run = lambda *a, **k: calls.append(1)
reflex_worker.available_scopes = lambda: ["main"]
reflex_worker.vocabulary.resolve = lambda g, node, scope, knowledge: None
reflex_worker.vocabulary.rows_for = lambda g, vids, scope, knowledge: []


def job_line(session, use_id):
    return {"ts": "2026-09-24T12:00:00Z", "session_id": session, "agent_id": "",
            "scope": "main", "tool_use_id": use_id, "anchors": ["a", "b"],
            "observed": "", "transcript": ""}


reflex_queue.enqueue(root, job_line(dead_id, "d1"))
claimed_dead = reflex_worker.claim_next(root)
outcome_dead = reflex_worker.run_job(claimed_dead, g=object(), root=root,
                                     cli=cli_for("local"), model="m",
                                     alive=reflex_worker.session_alive)

reflex_queue.enqueue(root, job_line(live_id, "l1"))
claimed_live = reflex_worker.claim_next(root)
outcome_live = reflex_worker.run_job(claimed_live, g=object(), root=root,
                                     cli=cli_for("local"), model="m",
                                     alive=reflex_worker.session_alive)

print(json.dumps({
    "session_alive_dead": reflex_worker.session_alive(dead_id),
    "session_alive_live": reflex_worker.session_alive(live_id),
    "outcome_dead": outcome_dead,
    "outcome_live": outcome_live,
    "model_calls": len(calls),
}))
"""


def run() -> Finding | None:
    from thalamus.harness.quick import _proc_start  # noqa: PLC0415

    dead_id = "qe-scratch-session-end-dead"
    live_id = "qe-scratch-session-end-live"

    with tempfile.TemporaryDirectory() as fake_home, tempfile.TemporaryDirectory() as tmp:
        sessions_dir = Path(fake_home) / "sessions"
        sessions_dir.mkdir(parents=True)
        root = Path(tmp)

        dead = subprocess.Popen(["true"])
        dead.wait(timeout=10)
        (sessions_dir / f"{dead.pid}.json").write_text(json.dumps({
            "sessionId": dead_id, "pid": dead.pid,
            # Non-empty and unmatchable: the dead pid's own /proc entry is gone, so
            # any non-empty procStart here fails the mismatch check in live_sessions()
            # (an EMPTY procStart would instead skip that check entirely).
            "procStart": "99999999",
        }))

        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
        try:
            proc_start = _proc_start(live.pid)
            if not proc_start:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "could not read /proc/<pid>/stat for the still-running "
                        "control process, so no live registry entry could be built"
                    ),
                    witness=f"live pid={live.pid}",
                    site=_SITE,
                )
            (sessions_dir / f"{live.pid}.json").write_text(json.dumps({
                "sessionId": live_id, "pid": live.pid, "procStart": proc_start,
            }))

            env = dict(os.environ)
            env["CLAUDE_CONFIG_DIR"] = fake_home
            proc = subprocess.run(
                [sys.executable, "-c", _PROBE, dead_id, live_id, str(root)],
                capture_output=True, text=True, env=env, timeout=30, check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary="the probe subprocess failed, so nothing below is evidence",
                    witness=f"rc={proc.returncode} stderr={proc.stderr.strip()[:500]}",
                    site=_SITE,
                )
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        finally:
            live.kill()
            live.wait(timeout=5)

        # POSITIVE CONTROL: the live session must read alive and its job must have
        # reached the model-call point, or a dead session reading "not alive" could
        # just mean the registry read answers False for everything.
        if not data["session_alive_live"] or data["outcome_live"] == "session_end":
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: a session registered as a live "
                    "process was not read as alive (or its job was still discarded "
                    "as session_end), so 'the dead session made no model call' below "
                    "cannot be told apart from every job being discarded regardless"
                ),
                witness=f"data={data!r}",
                site=_SITE,
            )
        if data["model_calls"] != 1:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: the live session's job did not reach "
                    "the model-call point exactly once, so the model-call count "
                    "below is not a meaningful signal"
                ),
                witness=f"model_calls={data['model_calls']!r}",
                site=_SITE,
            )

        if data["session_alive_dead"]:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "session_alive() reported a session naming an exited process as "
                    "alive, against a real (temporary) session registry"
                ),
                witness=f"data={data!r}",
                site="src/thalamus/harness/reflex_worker.py::session_alive",
            )
        if data["outcome_dead"] != "session_end":
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "a job whose session names an exited process was not discarded "
                    "as session_end"
                ),
                witness=f"data={data!r}",
                site="src/thalamus/harness/reflex_worker.py::run_job",
            )
        if data["model_calls"] != 1:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "a job for a session that is no longer live still made a model "
                    "call — exactly one model call was made in total, for the live "
                    "session's job, and the dead session's job should have "
                    "contributed zero"
                ),
                witness=f"data={data!r}",
                site="src/thalamus/harness/reflex_worker.py::run_job",
            )
        return None


CASE = Case(
    name="reflex-worker-session-end-job-makes-no-model-call",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "a job whose session names an exited process is discarded as session_end and "
        "makes no model call, checked against a real session registry"
    ),
    run=run,
)
