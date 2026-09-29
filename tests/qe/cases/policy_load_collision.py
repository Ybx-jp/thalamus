"""`policy.load()` keeps every withholding-ledger row that shares a rendered response.

The ledger stores the same recall response served twice as two withholding decisions
over one hash, so `load()` keys by `(response_sha256, ts)` and both survive (issue #143;
the live ledger has 751 rows over 741 hashes). Driven through `policy.log`/`policy.load`
against a throwaway directory, never `~/.thalamus/policy`.

Asserted: the two-row collision loads as 2 (with a distinct-hash control loading as 2);
a row whose `ts` is an unhashable list or dict is skipped without costing the well-formed
row after it; and `eval sync`'s sha map keeps last-record-in-file-order when an identical
`(sha, ts)` row recurs non-adjacently (A, B, A2 gives A2). The pairing rule for repeated
servings is open in #328, so last-wins is pinned as the current behaviour, not endorsed.

Drive it red: key `load()` by `response_sha256` alone (collision check), build the key
outside the malformed-row guard (list-`ts` check), or drop the pop-before-insert (order
check). Each was run red against the pre-fix parent or the intermediate fix.
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


def _write_rows(base: Path, name: str, lines: list[str]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_text("\n".join(lines) + "\n")


def _raw(sha, ts, seed):
    return json.dumps({
        "version": "v", "rate": 0.5, "session_id": "", "scope": "probe", "tool": "recall",
        "ts": ts, "seed": seed, "offered": ["a", "b"], "withheld": ["b"],
        "response_sha256": sha,
    })


def _adversarial_rows(policy, root: Path) -> Finding | None:
    """Attacks on the (sha, ts) key itself, run once the basic collision is fixed."""
    from thalamus.eval.sync import _withheld_by_sha  # noqa: PLC0415

    sha = "a" * 64
    other = "b" * 64

    # A row whose ts is not a hashable scalar must be skipped like any other malformed
    # row: the key tuple is built outside the try, so an unhashable ts raises out of
    # load() and takes every well-formed row (and eval sync / withholding) with it.
    for bad_ts in ([], {}):
        base = root / f"badts-{type(bad_ts).__name__}"
        _write_rows(base, "2026-08.jsonl",
                    [_raw(sha, bad_ts, "bad"), _raw(other, "2026-08-01T00:00:00", "good")])
        try:
            records = policy.load(base=base)
        except Exception as exc:  # noqa: BLE001
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="policy.load() raises on a ledger row whose ts is unhashable "
                        "instead of skipping it like every other malformed row",
                witness=f"ts={bad_ts!r} row followed by a well-formed row: load() "
                        f"raised {type(exc).__name__}: {exc}",
                site="src/thalamus/eval/policy.py::load",
            )
        if [r.seed for r in records.values()].count("good") != 1:
            return Finding(
                failure_class=FailureClass.INVARIANT_FALSIFIED,
                summary="a malformed-ts row cost the well-formed row after it",
                witness=f"ts={bad_ts!r}: seeds loaded {[r.seed for r in records.values()]}",
                site="src/thalamus/eval/policy.py::load",
            )

    # sync's sha map is last-record-in-file-order (#328 leaves that rule open, so it is
    # pinned as-is). A row repeated with an identical (sha, ts) later in the file must
    # not move a sha's winner: dict re-assignment keeps the first insertion position, so
    # A, B, A' would make B the last entry although A' is last in the file.
    base = root / "order"
    _write_rows(base, "2026-08.jsonl", [
        _raw(sha, "2026-08-01T00:00:00", "A"),
        _raw(sha, "2026-08-01T00:00:05", "B"),
        _raw(sha, "2026-08-01T00:00:00", "A2"),
    ])
    winner = _withheld_by_sha(base)[sha].seed
    if winner != "A2":
        return Finding(
            failure_class=FailureClass.INVARIANT_FALSIFIED,
            summary="eval sync's sha map no longer pairs a repeated response with the "
                    "last record in file order when an identical (sha, ts) row recurs "
                    "non-adjacently",
            witness=f"file order A, B, A2 (A and A2 share sha and ts): sync map winner "
                    f"is {winner!r}, the parent commit's last-wins gives 'A2'",
            site="src/thalamus/eval/sync.py::_withheld_by_sha",
        )
    return None


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
            return _adversarial_rows(policy, root)

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
    fixed=True,
)
