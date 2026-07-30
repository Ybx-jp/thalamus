#!/usr/bin/env python
"""Experiment 003 — does withholding a memory change what the session does?

Runs from the first day, and reports honestly that there is nothing to report
until the policy has been enabled and has accumulated draws:

    THALAMUS_WITHHOLD=0.25   # in the sessions being measured, not here
    uv run --extra experiments python experiments/003-does-withholding-change-anything/run.py

The design is fixed in preregistration.md, which was committed before any draw
existed. This script computes it; it does not choose it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from thalamus.eval import policy, sequential  # noqa: E402
from thalamus.substrate.writer import close_connection, connect  # noqa: E402

SLUG = "003-does-withholding-change-anything"
RATE = 0.25
HORIZON = 400
FUTILITY_MARGIN = 0.05


def status(url: str) -> dict:
    """What exists so far — the honest precondition check, run before any analysis."""
    records = policy.load()
    g = connect(url)
    try:
        with_propensity = g.V().has_label("Trace").has("propensity").count().next()
        traces = g.V().has_label("Trace").count().next()
    finally:
        close_connection(g)

    joined = with_propensity
    return {
        "records": len(records),
        "traces": traces,
        "traces_with_propensity": with_propensity,
        "join_rate": (joined / len(records)) if records else 0.0,
        "randomized_retrievals": joined,
        "rates_seen": sorted({r.rate for r in records.values()}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://localhost:8182/gremlin")
    args = parser.parse_args()

    state = status(args.url)
    print(f"experiment {SLUG}")
    print(f"  policy records on disk : {state['records']}")
    print(f"  traces carrying a propensity: {state['traces_with_propensity']} of {state['traces']}")
    print(f"  join rate (records -> traces): {state['join_rate'] * 100:.1f}%")

    if not state["records"]:
        print("\nNothing to analyse yet. The policy has never run.")
        print(f"  Enable it in the sessions being measured: THALAMUS_WITHHOLD={RATE}")
        print("  The design is already fixed in preregistration.md — committed before")
        print("  any draw existed, which is the only ordering that makes it a")
        print("  pre-registration rather than a description.")
        return

    if len(state["rates_seen"]) > 1:
        print(f"\nVOID: records carry {len(state['rates_seen'])} different rates "
              f"({state['rates_seen']}). A run pooling two rates is two experiments "
              "(preregistration.md).")
        return

    if state["join_rate"] < 0.90:
        print(f"\nVOID: only {state['join_rate'] * 100:.1f}% of policy records join to a "
              "trace by response hash; the pre-registered floor is 90%. The tap and the "
              "policy disagree about what was rendered, so the assignment cannot be trusted.")
        return

    print(f"\n{state['randomized_retrievals']} randomized retrievals against a horizon of "
          f"{HORIZON}.")
    print("The endpoint (repeat-retrieval rate on overlapping terms) needs the "
          "sequence below; see preregistration.md for why it is not a used-rate.")
    print(f"  stopping rule: exclude the null, or fall inside ±{FUTILITY_MARGIN} of it, "
          f"or reach n={HORIZON}")
    print(f"  monitor: confidence sequence at alpha=0.05, rho=0.05 "
          f"(radius at n={state['randomized_retrievals']}: "
          f"{sequential.radius(max(1, state['randomized_retrievals'])):.3f})")


if __name__ == "__main__":
    main()
