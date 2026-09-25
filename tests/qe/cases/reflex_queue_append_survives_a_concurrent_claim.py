"""An append racing a claim must be kept when it holds the key's lock, and is shown to
be lost when it does not — the race-detector control docs/14 §7 names.

`reflex_queue.enqueue()` appends under `with locked(directory):`; `reflex_worker.
claim_next()` renames `pending.jsonl` under the same lock. Both being *the same* lock
on *the same directory* is the whole claim: a trigger arriving while a claim is in
flight either lands in the file before the rename (and travels with the claimed job)
or lands in a fresh `pending.jsonl` after it (and waits for the next claim) — never
astride the rename, where it would be written into a file the worker has already read
and is about to delete. Nothing in `tests/test_reflex_worker.py` drives the two
concurrently; this case does, with real threads contending for the real lock, plus a
deliberately unlocked reproduction of the interleaving the lock exists to rule out —
without it, "the append survived" could just as well mean the race was never attempted.

**Part 1 — kept, with the lock.** A thread holds the key's lock exactly as `enqueue()`
would mid-append (open, write, and pause before releasing). A second thread starts
`claim_next()` against the same key. Positive control: the claim thread must still be
blocked shortly after starting — otherwise `claim_next()` is not actually contending
for this lock, and "the append was kept" below would be true of two operations that
never raced at all. The held append is then released; the invariant is that the claim,
once it proceeds, includes that append in the job it claims.

**Part 2 — lost, without it.** The identical interleaving — open pending.jsonl for
append, have the file renamed out from under the still-open handle, have the claimed
file read and discarded, only then complete the write — is reproduced by hand using
`reflex_queue`'s own low-level `_append_line`, with no `locked()` around any of it. On
Linux an open file description survives a rename of its path, so the late write lands
in the file that has already been read and unlinked, and is gone. This is not a defect
in `enqueue()` — nothing in it is called out of order — it is the failure the lock in
Part 1 is shown to prevent, and the reason `enqueue()` and `claim_next()` share it.

Hermetic: real `threading`, a temporary reflex root, no graph and no subprocess.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_SITE = "tests/qe/cases/reflex_queue_append_survives_a_concurrent_claim.py::run"


def _job(use_id: str) -> dict:
    return {
        "ts": "2026-09-24T12:00:00Z", "session_id": "s1", "agent_id": "", "scope": "main",
        "tool_use_id": use_id, "anchors": ["race_probe_a", "race_probe_b"],
        "observed": "", "transcript": "",
    }


def run() -> Finding | None:
    from thalamus.harness import reflex_queue, reflex_worker  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = reflex_queue.key_dir(root, "s1", "")
        pending = directory / "pending.jsonl"

        # --- Part 1: kept, with the lock -----------------------------------------
        reflex_queue.enqueue(root, _job("seed"))

        lock_acquired = threading.Event()
        release_now = threading.Event()

        def hold_and_append():
            with reflex_queue.locked(directory):
                reflex_queue._append_line(pending, _job("in-flight"))
                lock_acquired.set()
                release_now.wait(timeout=5)

        holder = threading.Thread(target=hold_and_append)
        holder.start()
        if not lock_acquired.wait(timeout=5):
            release_now.set()
            holder.join(timeout=5)
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="the lock-holding thread never reported acquiring the lock",
                witness="lock_acquired event never set",
                site=_SITE,
            )

        claim_result: dict = {}

        def do_claim():
            claim_result["claimed"] = reflex_worker.claim_next(root)

        claimer = threading.Thread(target=do_claim)
        claimer.start()
        time.sleep(0.3)

        # POSITIVE CONTROL: the claim must still be blocked here, or claim_next() is
        # not actually contending for this lock and "the append was kept" below would
        # be true of two calls that never raced.
        if not claimer.is_alive() or "claimed" in claim_result:
            release_now.set()
            holder.join(timeout=5)
            claimer.join(timeout=5)
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "positive control failed: claim_next() proceeded while the key's "
                    "lock was held by another thread, so it is not contending for "
                    "the same lock enqueue() takes — nothing below shows a real race "
                    "being resolved"
                ),
                witness=f"claimer.is_alive()={claimer.is_alive()} "
                         f"claim_result={claim_result!r}",
                site=_SITE,
            )

        release_now.set()
        holder.join(timeout=5)
        claimer.join(timeout=5)

        claimed = claim_result.get("claimed")
        if claimed is None:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="claim_next() returned nothing once the lock was released",
                witness="claim_result empty",
                site=_SITE,
            )
        kept_ids = {line.get("tool_use_id") for line in claimed.lines}
        if "in-flight" not in kept_ids:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary=(
                    "an append that completed under the key's lock, immediately "
                    "before a claim that was blocked waiting on the same lock, is "
                    "missing from the job that claim went on to claim"
                ),
                witness=f"claimed.lines={claimed.lines!r}",
                site="src/thalamus/harness/reflex_queue.py::enqueue",
            )

        # --- Part 2: lost, without it — the race-detector control -----------------
        directory2 = reflex_queue.key_dir(root, "s2", "")
        pending2 = directory2 / "pending.jsonl"
        reflex_queue.enqueue(root, {**_job("seed2"), "session_id": "s2"})

        # A second trigger's append begins (opens for append) without taking the
        # key's lock at all — the interleaving `locked()` exists to prevent.
        late_append = pending2.open("a")
        claimed_path = directory2 / "pending.raced.claimed"
        pending2.rename(claimed_path)  # the claim's rename, unguarded by any lock here
        lines_at_claim_time, _torn = reflex_worker._read_job(claimed_path)
        # Only now does the unlocked append actually land — into the file the claim
        # already read and is about to discard, exactly as `run_job` does.
        late_append.write(json.dumps({**_job("lost"), "session_id": "s2"}) + "\n")
        late_append.close()
        claimed_path.unlink()

        seen_ids = {line.get("tool_use_id") for line in lines_at_claim_time}
        if pending2.is_file():
            more, _ = reflex_worker._read_job(pending2)
            seen_ids |= {line.get("tool_use_id") for line in more}

        if "lost" in seen_ids:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary=(
                    "control failed: the deliberately unlocked append/rename/read/"
                    "delete interleaving did not lose the append it was built to "
                    "lose, so Part 1's 'kept, with the lock' result is not shown to "
                    "be the lock doing anything — the same outcome would occur "
                    "unlocked"
                ),
                witness=f"seen_ids={sorted(filter(None, seen_ids))!r}",
                site=_SITE,
            )

        return None


CASE = Case(
    name="reflex-queue-append-survives-a-concurrent-claim-only-under-the-lock",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary=(
        "an append racing a claim is kept when both hold the key's lock, and is shown "
        "lost when the same interleaving happens without it"
    ),
    run=run,
)
