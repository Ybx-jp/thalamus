"""A job past its deadline is `timeout`, never `empty` — against a genuinely blocked
network call, not a cooperative sleep.

docs/14-memory-reflex.md §7 names this directly: "a job past its deadline is timeout,
never empty." `tests/test_reflex_worker.py::
test_a_job_past_its_deadline_is_timeout_never_empty` already drives `run_job`'s
`_Clock`/`SIGALRM` path, but the "work" it interrupts is a plan that calls
`time.sleep(2.0)` — and `time.sleep` is cooperative by construction: CPython checks
for a pending signal and re-raises into the caller as soon as the sleep call returns
control, which every blocking call is not guaranteed to do. The worker's real jobs
spend nearly all of their wall time inside `urllib.request.urlopen` against ollama's
`/api/chat` (`harness/extraction.py`), a C-level blocking socket read with its own
timeout, and `reflex_worker.py`'s module docstring states the design's whole claim
about this: the deadline is "enforced by a timer around the whole loop rather than by
the model or a socket timeout alone" specifically because the model side cannot be
trusted to return in time. Nothing in this tree shows `SIGALRM` actually interrupts a
real blocked socket read before this case.

**The fixture.** A bare TCP server accepts one connection and then sends nothing —
holding the socket open past any deadline this case sets. The agentic plan
(`agentic.run`, monkeypatched) is a real `urllib.request.urlopen` call against that
server with a generous 30 s socket timeout, run through the genuine `run_job` with a
0.3 s job deadline.

**Positive control.** The stub server must actually accept the connection before this
case reads anything from the run — without it, a "timeout" outcome could be produced
by a connection failure that never touched the wall clock at all.

**The invariant.** `run_job` must return `timeout` (never `empty`), within a
generous multiple of the 0.3 s deadline (not merely inside `urlopen`'s own 30 s socket
timeout, which would mean the clock never fired and something else ended the call).

Hermetic: a loopback TCP server on an ephemeral port, no graph and no real model.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_worker_deadline_interrupts_blocking_call.py::run"


def _job_line(use_id="t1"):
    return {
        "ts": "2026-09-24T12:00:00Z", "session_id": "s1", "agent_id": "", "scope": "main",
        "tool_use_id": use_id, "anchors": ["deadline_probe_a", "deadline_probe_b"],
        "observed": "", "transcript": "",
    }


def run() -> Finding | None:
    import tempfile
    from pathlib import Path

    from thalamus.harness import agentic, reflex_queue, reflex_worker  # noqa: PLC0415
    from thalamus.harness.agents import cli_for  # noqa: PLC0415

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = threading.Event()

    def accept_and_hang():
        try:
            server.settimeout(5.0)
            conn, _addr = server.accept()
            accepted.set()
            time.sleep(3.0)  # hold the socket open; send nothing back
            conn.close()
        except OSError:
            pass

    acceptor = threading.Thread(target=accept_and_hang, daemon=True)
    acceptor.start()

    def hanging_plan(job, *, result, **kwargs):  # noqa: ARG001
        # Stands in for a hung `/api/chat` call: a real blocking C-level socket read
        # with its own generous timeout, well past the job's own deadline below.
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30)
        result.stopped = "stop_tool"  # unreachable if the clock does its job
        result.kept = []
        return result

    original_run = agentic.run
    agentic.run = hanging_plan
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            reflex_queue.enqueue(tmp_path, _job_line())
            claimed = reflex_worker.claim_next(tmp_path)

            started = time.monotonic()
            outcome = reflex_worker.run_job(
                claimed, g=object(), root=tmp_path, cli=cli_for("local"), model="m",
                alive=lambda s: True, deadline_seconds=0.3,
            )
            elapsed = time.monotonic() - started
    finally:
        agentic.run = original_run
        server.close()
        acceptor.join(timeout=5)

    # POSITIVE CONTROL: the stub server must have actually accepted the connection, or
    # a "timeout" outcome below could be produced by a connection failure that never
    # engaged the wall clock at all.
    if not accepted.is_set():
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary=(
                "the stub server never accepted the plan's connection, so the run "
                "below never actually blocked on real network I/O"
            ),
            witness=f"accepted={accepted.is_set()}",
            site=_SITE,
        )

    if outcome == "empty":
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "a job blocked on a real, never-responding network call past its "
                "deadline was recorded as empty rather than timeout — an operator "
                "reading 'empty' would conclude the graph had nothing, not that the "
                "job never got the chance to look"
            ),
            witness=f"outcome={outcome!r} elapsed={elapsed:.2f}s",
            site="src/thalamus/harness/reflex_worker.py::run_job",
        )
    if outcome != "timeout":
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "a job blocked on a real, never-responding network call past its "
                "deadline did not end as timeout"
            ),
            witness=f"outcome={outcome!r} elapsed={elapsed:.2f}s",
            site="src/thalamus/harness/reflex_worker.py::run_job",
        )
    # The clock's own deadline is 0.3s; anything near urlopen's 30s timeout would mean
    # SIGALRM never actually interrupted the blocked read and something else ended it.
    if elapsed > 3.0:
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "the job did eventually report timeout, but only after several "
                "seconds against a 0.3s deadline — the wall clock did not interrupt "
                "the blocked network call promptly, which is the property "
                "reflex_worker.py's own docstring rests the design on"
            ),
            witness=f"elapsed={elapsed:.2f}s deadline_seconds=0.3",
            site="src/thalamus/harness/reflex_worker.py::_Clock",
        )
    return None


CASE = Case(
    name="reflex-worker-deadline-interrupts-a-real-blocked-network-call",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "a job blocked on a real, never-responding network call past its deadline "
        "ends as timeout, promptly, never empty"
    ),
    run=run,
)
