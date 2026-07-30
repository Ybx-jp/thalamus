#!/usr/bin/env python
"""Experiment 004 — does a perfect memory beat no memory on this battery?

    uv run --extra experiments python experiments/004-the-ceiling/run.py

Reads `~/.thalamus/counterfactuals/runs.jsonl`. The design is fixed in
preregistration.md, committed before the first ceiling arm ran; this script
computes it and refuses to interpret an incomplete or void campaign.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from thalamus.eval import sequential  # noqa: E402

SLUG = "004-the-ceiling"
TASK = "arm-runner-session-death-classification"
ARMS = ("ceiling", "memory-off")
CAMPAIGN_START = "2026-07-30T10:00:00"
PRIMARY_RUNG = 4
SECONDARY_RUNG = 3
HORIZON = 12
FUTILITY_MARGIN = 0.05
RUNS = Path.home() / ".thalamus" / "counterfactuals" / "runs.jsonl"


def load(path: Path = RUNS) -> list[dict]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [
        r for r in rows
        if r.get("task") == TASK and r.get("arm") in ARMS and r.get("ts", "") >= CAMPAIGN_START
    ]


def rank_statistic(treated: list[int], control: list[int]) -> float:
    """P(ceiling > memory-off) + ½P(tie) — the rank-based read.

    Not mean-of-rungs: metric models over ordinal data sign-reverse, demonstrated
    on this project's own campaign data (lab/020), and every power number derived
    from that mean is withdrawn (lab/034).
    """
    if not treated or not control:
        return 0.5
    wins = sum((t > c) + 0.5 * (t == c) for t in treated for c in control)
    return wins / (len(treated) * len(control))


def analyse(rows: list[dict]) -> dict:
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    rungs = {arm: [int(r.get("rung") or 0) for r in runs] for arm, runs in by_arm.items()}

    def share(values: list[int], threshold: int) -> tuple[int, int]:
        return sum(1 for v in values if v >= threshold), len(values)

    # One paired observation per (ceiling, memory-off) pair, in campaign order.
    pairs = list(zip(rungs["ceiling"], rungs["memory-off"], strict=False))
    differences = sequential.paired_differences(
        [1.0 if c > o else 0.5 if c == o else 0.0 for c, o in pairs],
        [0.5] * len(pairs),
    ) if pairs else []
    states = sequential.track(differences) if differences else []

    return {
        "arms": {arm: len(runs) for arm, runs in by_arm.items()},
        "rungs": rungs,
        "primary": {arm: share(vals, PRIMARY_RUNG) for arm, vals in rungs.items()},
        "secondary": {arm: share(vals, SECONDARY_RUNG) for arm, vals in rungs.items()},
        "rank_statistic": rank_statistic(rungs["ceiling"], rungs["memory-off"]),
        "pairs": len(pairs),
        "sequence": [
            {"n": s.n, "mean": s.mean, "lo": s.interval[0], "hi": s.interval[1]} for s in states
        ],
        "decision": (
            sequential.decide(
                states[-1], null=sequential.NO_DIFFERENCE,
                margin=FUTILITY_MARGIN, horizon=HORIZON // 2,
            )
            if states else "continue"
        ),
        "cost_usd": round(sum(r.get("agent", {}).get("cost_usd", 0) for r in rows), 2),
        "contaminated": [r["ts"][:19] for r in rows if r.get("contaminated")],
        "faults": [r["ts"][:19] for r in rows if r.get("infra_faults")],
        "turn_capped": sum(1 for r in rows if r.get("turn_capped")),
        "injected_chars": [
            r.get("applied", {}).get("injected_fact_chars", 0)
            for r in rows if r["arm"] == "ceiling"
        ],
        "recall_calls_leaked": [
            r["ts"][:19] for r in rows
            if sum((r.get("recall_calls") or {}).values()) > 0
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNS)
    args = parser.parse_args()

    rows = load(args.runs)
    if not rows:
        print(f"No campaign records yet for `{TASK}` at or after {CAMPAIGN_START}.")
        return

    m = analyse(rows)
    print(f"experiment {SLUG} — {sum(m['arms'].values())} arm(s), ${m['cost_usd']}")
    for arm in ARMS:
        used, total = m["primary"][arm]
        s_used, s_total = m["secondary"][arm]
        print(f"  {arm:12} n={total:<3} rungs={m['rungs'][arm]}  "
              f"L>={PRIMARY_RUNG}: {used}/{total}  L>={SECONDARY_RUNG}: {s_used}/{s_total}")
    print(f"  rank statistic P(ceiling > memory-off) = {m['rank_statistic']:.3f}")
    if m["sequence"]:
        last = m["sequence"][-1]
        print(f"  confidence sequence at n={last['n']}: "
              f"[{last['lo']:.3f}, {last['hi']:.3f}] -> {m['decision']}")

    for label, rows_hit in (("CONTAMINATED", m["contaminated"]), ("INFRA FAULT", m["faults"]),
                            ("RECALL IN A NO-MEMORY ARM", m["recall_calls_leaked"])):
        if rows_hit:
            print(f"  VOID CONDITION — {label}: {rows_hit}")

    if sum(m["arms"].values()) < HORIZON and m["decision"] == "continue":
        print(f"\nCampaign incomplete ({sum(m['arms'].values())}/{HORIZON} arms) and the "
              "sequence has not fired. No verdict is rendered — the stopping rule is "
              "in preregistration.md and this script does not get to improvise one.")
        return

    (Path(__file__).resolve().parent / "results.json").write_text(
        json.dumps({"experiment": SLUG, "results": m}, indent=2, sort_keys=True) + "\n"
    )
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
