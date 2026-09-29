"""Concurrent `ceremonies.start()` / `skip()` on one (room, kind) must never share an
`occasion_id`, and the indices they claim must be exactly 1..N.

The write-path concurrency gap of issue #76, filed as #168 (start) and #234 (skip).
`ceremonies._append_occasion` reads the ledger to number the occasion and appends the
row under one `flock`. Two properties follow, and this case asserts both from outside:

1. **Distinct, contiguous ids under real contention.** Writers are hammered as 4
   separate processes and as 8 threads (flock behaves differently across an fd shared by
   threads and across processes), each opening 10-20 occasions in a ledger whose parent
   directory does not exist yet (first-ever creation races too), mixing `start` and
   `skip` on one (room, kind). Every claimed id must be unique and the ids must be
   `<room>:<kind>:1..N` with no gap.
2. **Independent counters.** Concurrent writers on different (room, kind) pairs must
   each see their own 1..N and share nothing.

No barrier is spliced into the module: a lock held across the read makes a
read/append barrier unreachable (the second caller blocks on the flock), so the
earlier forced-window form of this case could only express the broken state. Real
contention over many iterations distinguishes both.

The lock has to cover the write reaching the file, not only the write call: the
row is flushed and fsynced before `LOCK_UN`. With the flush missing, the next locker
reads a ledger that lacks the previous row and reuses its index (duplicates in every run
of the process stress).

**The control.** Sequential opens must yield distinct ids (COLLAPSED_SENTINEL otherwise).
**Driving it red.** Against the parent of cf1df8c (21a385b, index read outside the
lock) the case reports duplicates in the 4-process and 8-thread runs; against cf1df8c
(lock across the read, no flush before unlock) it reports duplicates in the process run.
Removing the `flush()` from `_append_occasion` reproduces the second.
"""

from __future__ import annotations

import collections
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_ROOM = "qe-race-room"
_KIND = "retrospective"


_WORKER = r"""
import sys, json
from pathlib import Path
from thalamus.harness import ceremonies as c
ledger, room, kind, n, mix = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5] == "1"
ids = []
for i in range(n):
    if mix and i % 2:
        ids.append(c.skip(room, kind, reason="qe", path=ledger)["occasion_id"])
    else:
        ids.append(c.start(room, kind, path=ledger)["occasion_id"])
print(json.dumps(ids))
"""


def _procs(ledger: Path, jobs: list[tuple[str, str]], n: int, mix: bool) -> list[str]:
    handles = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(ledger), room, kind, str(n), "1" if mix else "0"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for room, kind in jobs
    ]
    ids: list[str] = []
    for handle in handles:
        out, err = handle.communicate(timeout=60)
        if handle.returncode != 0:
            raise RuntimeError(f"worker failed: {err[-300:]}")
        ids.extend(json.loads(out))
    return ids


def _check(label: str, ids: list[str], expected: dict[tuple[str, str], int]):
    """None when ids are unique and per-(room, kind) exactly 1..N, else a witness."""
    dupes = sorted(k for k, v in collections.Counter(ids).items() if v > 1)
    if dupes:
        return f"{label}: {len(dupes)} duplicated occasion_id(s), e.g. {dupes[:3]} among {len(ids)}"
    for (room, kind), count in expected.items():
        got = sorted(int(i.rsplit(":", 1)[1]) for i in ids if i.rsplit(":", 1)[0] == f"{room}:{kind}")
        if got != list(range(1, count + 1)):
            return f"{label}: {room}:{kind} indices {got[:5]}... are not 1..{count}"
    return None


def run() -> Finding | None:
    from thalamus.harness import ceremonies  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ceremonies.jsonl"
        ceremonies.start(_ROOM, _KIND, path=ledger)
        ceremonies.start(_ROOM, _KIND, path=ledger)
        control_ids = sorted(
            row["occasion_id"] for row in ceremonies.read_rows(ledger)
            if row.get("event") == "start"
        )
        if len(set(control_ids)) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="two sequential start() calls did not claim distinct occasion "
                        "ids, so this case cannot distinguish a race from ordinary behaviour",
                witness=f"sequential control ids: {control_ids}",
                site="tests/qe/cases/ceremony_start_race.py",
            )

    witnesses: list[str] = []
    try:
        # 4 processes, start+skip mixed, same (room, kind), ledger dir absent.
        for trial in range(3):
            with tempfile.TemporaryDirectory() as tmp:
                ids = _procs(Path(tmp) / "new" / "l.jsonl", [(_ROOM, _KIND)] * 4, 15, True)
                w = _check(f"4 processes mixed start/skip (trial {trial})", ids, {(_ROOM, _KIND): 60})
                if w:
                    witnesses.append(w)
                    break
        # 8 threads on one fd-per-call, same (room, kind).
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "new" / "l.jsonl"
            tids: list[str] = []
            lock = threading.Lock()

            def _thread():
                got = [ceremonies.start(_ROOM, _KIND, path=ledger)["occasion_id"] for _ in range(10)]
                with lock:
                    tids.extend(got)

            threads = [threading.Thread(target=_thread) for _ in range(8)]
            [t.start() for t in threads]
            [t.join(timeout=60) for t in threads]
            w = _check("8 threads start", tids, {(_ROOM, _KIND): 80})
            if w:
                witnesses.append(w)
        # Different (room, kind) pairs concurrently: independent counters.
        with tempfile.TemporaryDirectory() as tmp:
            pairs = [("qe-a", "retrospective"), ("qe-a", "review"), ("qe-b", "retrospective"), ("qe-b", "review")]
            ids = _procs(Path(tmp) / "l.jsonl", pairs * 2, 10, False)
            w = _check("4 pairs x 2 processes", ids, {pair: 20 for pair in pairs})
            if w:
                witnesses.append(w)
    except Exception as exc:  # noqa: BLE001
        return Finding(
            failure_class=FailureClass.COLLAPSED_SENTINEL,
            summary="the contention harness itself failed, so it is no evidence about the race",
            witness=f"{type(exc).__name__}: {exc}",
            site="tests/qe/cases/ceremony_start_race.py",
        )

    if not witnesses:
        return None
    return Finding(
        failure_class=FailureClass.INVARIANT_FALSIFIED,
        summary=(
            "concurrent ceremonies.start()/skip() on one (room, kind) claimed duplicate "
            "or non-contiguous occasion ids: the index is computed from a ledger read "
            "that does not yet include the previous writer's row"
        ),
        witness="; ".join(witnesses),
        site="src/thalamus/harness/ceremonies.py:_append_occasion",
    )


CASE = Case(
    name="ceremony-start-serializes-concurrent-opens",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two ceremonies opened at once in the same room must not share one occasion_id",
    run=run,
    issue=168,
    fixed=True,
)
