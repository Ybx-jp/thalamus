"""`policy.load()` keys the withholding ledger by `response_sha256` alone, so two ledger
rows that legitimately share a rendered response collapse into one loaded record.

Issue #143 measured this against the live ledger: 751 rows over 741 distinct hashes, 741
records recoverable through `load()`, 10 silently shadowed. The duplicate hash is not
corruption — the same recall response served twice hashes identically, and the ledger
stores that as two withholding *decisions* over one rendered payload — but the loader's
`dict[str, WithholdRecord]` can hold only the last row written for a given hash, so the
first decision (its `offered`/`withheld` sets, its seed, its ts) is unrecoverable and any
downstream count is under by however many collisions occurred.

Driven through `policy.log`/`policy.load` themselves against a throwaway ledger
directory, never `~/.thalamus/policy`, so the fixture is real ledger rows on disk and not
a hand-typed dict imitating one.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..model import Case, FailureClass, Finding, Substrate, Tier

_T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _row(policy_mod, *, ts, seed, offered, withheld):
    return policy_mod.WithholdRecord(
        version=policy_mod.POLICY_VERSION,
        rate=0.5,
        session_id="",
        scope="probe",
        tool="recall",
        ts=ts.isoformat(),
        seed=seed,
        offered=offered,
        withheld=withheld,
    )


def run() -> Finding | None:
    from thalamus.eval import policy  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- CONTROL: a two-row fixture with DISTINCT hashes must load as 2, or "load
        # returned fewer rows" cannot be told apart from a loader that returns nothing at
        # all regardless of what was written. ---
        control_base = root / "control"
        policy.log(_row(policy, ts=_T0, seed="seed-a", offered=["v1", "v2"], withheld=["v2"]),
                   "response body A", base=control_base)
        policy.log(_row(policy, ts=_T0 + timedelta(minutes=1), seed="seed-b",
                        offered=["v3", "v4"], withheld=["v4"]),
                   "response body B", base=control_base)
        control_loaded = policy.load(base=control_base)
        if len(control_loaded) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="load() did not return 2 rows for a two-row, distinct-hash "
                        "fixture, so this case cannot tell a real hash collision from a "
                        "loader that drops rows outright",
                witness=f"control fixture (2 distinct hashes) loaded as "
                        f"{len(control_loaded)}",
                site="tests/qe/cases/policy_load_collision.py",
            )

        # --- The defect: two rows over ONE rendered response, i.e. one recall answer
        # served to two different withholding decisions -- exactly what the ledger
        # records when the same response renders twice. ---
        collision_base = root / "collision"
        rendered = "identical rendered response body"
        sha = policy.response_key(rendered)
        row_a = _row(policy, ts=_T0, seed="seed-a", offered=["v1", "v2"], withheld=["v2"])
        row_b = _row(policy, ts=_T0 + timedelta(hours=1), seed="seed-c",
                     offered=["v5", "v6"], withheld=["v5"])
        policy.log(row_a, rendered, base=collision_base)
        policy.log(row_b, rendered, base=collision_base)

        loaded = policy.load(base=collision_base)

        # --- GREEN direction: the same two written rows, deduped by (sha, ts) instead of
        # by sha alone, recover both -- so a loader keyed on the full identity the ledger
        # actually carries would not lose either row, and the red below is the key
        # collision itself and not a broken comparator. ---
        lines = [
            line
            for path in sorted(collision_base.glob("*.jsonl"))
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        keyed_by_sha_and_ts = {
            (json.loads(line)["response_sha256"], json.loads(line)["ts"]): line
            for line in lines
        }
        if len(keyed_by_sha_and_ts) != 2:
            return Finding(
                failure_class=FailureClass.COLLAPSED_SENTINEL,
                summary="keying the same two written rows by (sha, ts) also collapsed "
                        "them, so this fixture cannot demonstrate the fix direction "
                        "either",
                witness=f"{len(lines)} lines written, "
                        f"{len(keyed_by_sha_and_ts)} distinct (sha, ts) keys",
                site="tests/qe/cases/policy_load_collision.py",
            )

        if len(loaded) == 2:
            return None  # load() already preserves both rows

        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary=(
                "policy.load() keys the withholding ledger by response_sha256 alone, so "
                "two ledger rows sharing one rendered response collapse into a single "
                "loaded record and the earlier withholding decision is silently dropped"
            ),
            witness=(
                f"wrote 2 rows sharing response_sha256={sha[:16]} "
                f"(ts={row_a.ts} seed={row_a.seed} offered={row_a.offered} vs "
                f"ts={row_b.ts} seed={row_b.seed} offered={row_b.offered}); "
                f"load() returned {len(loaded)} record(s) for this hash; keying by "
                f"(sha, ts) instead recovers {len(keyed_by_sha_and_ts)}"
            ),
            site="src/thalamus/eval/policy.py::load",
        )


CASE = Case(
    name="policy-load-collapses-hash-collision",
    tier=Tier.FAST,
    substrate=(Substrate.HERMETIC,),
    classes=(FailureClass.INVARIANT_FALSIFIED, FailureClass.COLLAPSED_SENTINEL),
    summary="two withholding-ledger rows that share one rendered response must both "
            "survive policy.load(), not collapse into whichever the dict keeps last",
    run=run,
    issue=143,
    fixed=False,
)
