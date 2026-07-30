#!/usr/bin/env python
"""Experiment 005 — does the framing of an injected memory change what gets built?

    uv run --extra experiments python experiments/005-framing/run.py

Design fixed in preregistration.md, committed before the first arm ran. This
script computes it and refuses to interpret an incomplete or void campaign.
"""

from __future__ import annotations

import argparse
import json
import sys
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from thalamus.eval import sequential  # noqa: E402

SLUG = "005-framing"
TASK = "arm-runner-session-death-classification"
ARMS = ("ceiling", "ceiling-problem")
CAMPAIGN_START = "2026-07-30T16:00:00"
PRIMARY_RUNG = 2  # L2: the rung the conclusion framing cost in 4 of 4 (lab/036)
HORIZON = 10
RUNS = Path.home() / ".thalamus" / "counterfactuals" / "runs.jsonl"


def load(path: Path = RUNS) -> list[dict]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [
        r for r in rows
        if r.get("task") == TASK and r.get("arm") in ARMS and r.get("ts", "") >= CAMPAIGN_START
    ]


def passed(row: dict, level: int) -> bool:
    return any(e.get("level") == level and e.get("passed") for e in row.get("acceptance", []))


def discordant_test(pairs: list[tuple[bool, bool]]) -> tuple[int, int, float]:
    """Exact test on discordant pairs only — McNemar's, done exactly.

    Concordant pairs carry no information about a *difference*: two arms that both
    pass, or both fail, say the same thing under either framing. Only the pairs
    that disagree do, which is why the effective n here is far below the arm count
    and why the pre-registration says 5 pairs cannot detect a small difference.
    """
    problem_only = sum(1 for c, p in pairs if p and not c)
    conclusion_only = sum(1 for c, p in pairs if c and not p)
    n = problem_only + conclusion_only
    if not n:
        return problem_only, conclusion_only, 1.0
    extreme = min(problem_only, conclusion_only)
    p = min(1.0, sum(comb(n, k) for k in range(extreme + 1)) / (2**n) * 2)
    return problem_only, conclusion_only, p


def analyse(rows: list[dict]) -> dict:
    by_framing = {
        "conclusion": [r for r in rows if r.get("framing") == "conclusion"],
        "problem": [r for r in rows if r.get("framing") == "problem"],
    }
    l2 = {k: [passed(r, PRIMARY_RUNG) for r in v] for k, v in by_framing.items()}
    pairs = list(zip(l2["conclusion"], l2["problem"], strict=False))
    problem_only, conclusion_only, p = discordant_test(pairs)

    differences = sequential.paired_differences(
        [1.0 if pr else 0.0 for _c, pr in pairs],
        [1.0 if c else 0.0 for c, _p in pairs],
    ) if pairs else []
    states = sequential.track(differences) if differences else []

    return {
        "arms": {k: len(v) for k, v in by_framing.items()},
        "rungs": {k: [r.get("rung") for r in v] for k, v in by_framing.items()},
        "l2_pass": {k: (sum(v), len(v)) for k, v in l2.items()},
        "pairs": len(pairs),
        "discordant": {"problem_only": problem_only, "conclusion_only": conclusion_only},
        "p_value": p,
        "sequence": [
            {"n": s.n, "mean": s.mean, "lo": s.interval[0], "hi": s.interval[1]} for s in states
        ],
        "memo_echo": {
            k: [(r.get("memo_echoed") or {}).get("ratio") for r in v]
            for k, v in by_framing.items()
        },
        "turn_capped": {k: sum(1 for r in v if r.get("turn_capped")) for k, v in by_framing.items()},
        "cost_usd": round(sum(r.get("agent", {}).get("cost_usd", 0) for r in rows), 2),
        "contaminated": [r["ts"][:19] for r in rows if r.get("contaminated")],
        "unused_memo": [
            r["ts"][:19] for r in rows
            if r.get("framing") == "problem" and not (r.get("memo_echoed") or {}).get("matched")
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNS)
    args = parser.parse_args()

    rows = load(args.runs)
    if not rows:
        print(f"No framing-campaign records at or after {CAMPAIGN_START}.")
        return

    m = analyse(rows)
    print(f"experiment {SLUG} — {sum(m['arms'].values())} arm(s), ${m['cost_usd']}")
    for framing in ("conclusion", "problem"):
        hits, total = m["l2_pass"][framing]
        print(f"  {framing:11} n={total} rungs={m['rungs'][framing]} "
              f"L{PRIMARY_RUNG} pass={hits}/{total} capped={m['turn_capped'][framing]} "
              f"echo={m['memo_echo'][framing]}")
    d = m["discordant"]
    print(f"  discordant pairs: {d['problem_only']} favour problem, "
          f"{d['conclusion_only']} favour conclusion -> exact p = {m['p_value']:.3f}")
    if m["sequence"]:
        last = m["sequence"][-1]
        print(f"  confidence sequence at n={last['n']}: [{last['lo']:.3f}, {last['hi']:.3f}]")

    if m["contaminated"]:
        print(f"  VOID — contaminated: {m['contaminated']}")
    if m["unused_memo"]:
        print(f"  VOID — problem arms that never touched the memo: {m['unused_memo']}")

    if sum(m["arms"].values()) < HORIZON:
        print(f"\nCampaign incomplete ({sum(m['arms'].values())}/{HORIZON} arms). No verdict.")
        return

    (Path(__file__).resolve().parent / "results.json").write_text(
        json.dumps({"experiment": SLUG, "results": m}, indent=2, sort_keys=True) + "\n"
    )
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
