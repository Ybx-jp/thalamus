"""A killed `worker.lock` holder must be reclaimable; a live one must refuse.

docs/14-memory-reflex.md §7's qe companion list for thalamus PR #280 names this
directly: "a killed `worker.lock` holder is reclaimed and a live one refuses."
`reflex_worker.py`'s own module docstring states the design's whole claim about why
this needs no cleanup path: "the kernel releases the lock when the process dies, so
there is no stale lock to clear." `tests/test_reflex_worker.py::
test_a_worker_finding_the_lock_held_runs_nothing` covers the "live one refuses" half,
but entirely in-process — it holds the flock itself and checks a second acquisition
attempt fails, which says nothing about the "reclaimed" half the docstring actually
rests its no-stale-lock claim on. Two different file descriptors in one process can
already contend for a flock, so that test never crosses a real process boundary and
never kills anything; the design's load-bearing claim — the OS, not this code, is what
prevents a stale lock — is untested anywhere in this tree until a real process holding
the lock is actually killed.

**The experiment.** A real subprocess opens `worker.lock` and takes the exclusive
flock, then blocks (a long sleep) so the lock stays held past the moment this case
checks it.

**Positive control.** While that subprocess is alive, `worker_running()` must report
the lock held, and `reflex_worker.work()` started against it must run zero jobs —
without this, "nothing ran after the kill" cannot be told apart from "the lock was
never actually contended in the first place", which would report a no-op lock
mechanism as a working one.

**The invariant.** The holder is killed (`SIGKILL`) and reaped. `worker_running()`
must then report the lock free, and a job enqueued afterward must be claimable — not
left stranded behind a lock file nobody will ever clear, which is the failure mode the
module docstring's claim exists to rule out.

Hermetic: a temporary directory as the reflex root, a `python -c` subprocess as the
lock holder, killed and reaped by this case regardless of outcome.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_worker_lock_reclaimed_after_death.py::run"

_HOLDER = """
import fcntl, sys, time
handle = open(sys.argv[1], "a")
fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
print("locked", flush=True)
time.sleep(60)
"""


def run() -> Finding | None:
    from thalamus.harness import reflex_queue, reflex_worker  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        lock_path = reflex_queue.worker_lock_path(root)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        holder = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, str(lock_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            line = holder.stdout.readline()
            if line.strip() != "locked":
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "the lock-holding subprocess never reported holding the "
                        "lock, so nothing below is evidence about reclaiming it"
                    ),
                    witness=f"stdout={line!r} stderr={holder.stderr.read()!r}",
                    site=_SITE,
                )

            # POSITIVE CONTROL: with the holder alive, the lock must read held and a
            # worker must run nothing against it.
            if not reflex_queue.worker_running(root):
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: worker_running() reported False "
                        "while a live subprocess holds the exclusive flock"
                    ),
                    witness=f"holder pid={holder.pid}",
                    site=_SITE,
                )
            ran_while_live = reflex_worker.work(root, connect_graph=lambda: None)
            if ran_while_live != 0:
                return Finding(
                    failure_class=FailureClass.COLLAPSED_SENTINEL,
                    summary=(
                        "positive control failed: a worker ran jobs while a live "
                        "process held worker.lock, so the lock is not exclusive "
                        "across process boundaries and 'reclaimed after death' below "
                        "would mean nothing"
                    ),
                    witness=f"reflex_worker.work() returned {ran_while_live}",
                    site=_SITE,
                )

            holder.kill()
            holder.wait(timeout=10)

            # THE INVARIANT: the kernel drops the dead holder's flock, so a worker
            # must be able to take it — not remain refused by a lock nobody holds.
            deadline = time.monotonic() + 5.0
            reclaimed = False
            while time.monotonic() < deadline:
                if not reflex_queue.worker_running(root):
                    reclaimed = True
                    break
                time.sleep(0.05)
            if not reclaimed:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "worker_running() kept reporting the lock held after its "
                        "holder was killed and reaped — a killed worker.lock holder "
                        "must be reclaimable, contradicting the module's own claim "
                        "that the kernel leaves no stale lock to clear"
                    ),
                    witness=f"holder pid={holder.pid} returncode={holder.returncode}",
                    site="src/thalamus/harness/reflex_queue.py::worker_running",
                )

            reflex_queue.enqueue(root, {
                "ts": "2026-09-24T12:00:00Z", "session_id": "s1", "agent_id": "",
                "scope": "main", "tool_use_id": "t1", "anchors": ["reclaim_probe_a",
                "reclaim_probe_b"], "observed": "", "transcript": "",
            })
            claimed = reflex_worker.claim_next(root)
            if claimed is None:
                return Finding(
                    failure_class=FailureClass.INVARIANT_FALSIFIED,
                    summary=(
                        "a job could not be claimed after the dead worker.lock "
                        "holder was reclaimed, even though worker_running() reports "
                        "the lock free"
                    ),
                    witness=f"worker_running={reflex_queue.worker_running(root)}",
                    site="src/thalamus/harness/reflex_worker.py::claim_next",
                )
            return None
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=5)


CASE = Case(
    name="reflex-worker-lock-reclaimed-after-holder-death",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="a killed worker.lock holder must be reclaimable; a live one must refuse",
    run=run,
)
