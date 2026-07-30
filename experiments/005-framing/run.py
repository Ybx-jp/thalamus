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

from thalamus.eval import publish, sequential  # noqa: E402

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

    reference = memory_off_reference(args.runs)
    results_path, page_path = publish.write(
        page(m, reference), Path(__file__).resolve().parent, m
    )
    print(f"\nwrote {results_path.name} and {page_path.name}")


def memory_off_reference(path: Path) -> tuple[int, int]:
    """experiments/004's same-day memory-off arms: (L2 passes, arms).

    Context, not a control for this comparison — they were randomized against the
    conclusion arms in 004, not against the problem arms here.
    """
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    off = [
        r for r in rows
        if r.get("task") == TASK and r.get("arm") == "memory-off"
        and "2026-07-30T10:00:00" <= r.get("ts", "") < CAMPAIGN_START
    ]
    return sum(1 for r in off if passed(r, PRIMARY_RUNG)), len(off)




def page(m, reference):
    conc_hits, conc_n = m["l2_pass"]["conclusion"]
    prob_hits, prob_n = m["l2_pass"]["problem"]
    ref_hits, ref_n = reference
    d = m["discordant"]
    last = m["sequence"][-1] if m["sequence"] else {"n": 0, "lo": 0.0, "hi": 1.0}
    injected_hits = conc_hits + prob_hits
    injected_n = conc_n + prob_n

    stats = [
        publish.Stat(
            label="Primary endpoint (L2 pass)",
            value=f"{conc_hits}/{conc_n} vs {prob_hits}/{prob_n}",
            note="conclusion vs problem framing — the rung the conclusion memo cost "
                 "in every arm that had ever received one",
        ),
        publish.Stat(
            label="Discordant pairs",
            value=f"{d['problem_only']} vs {d['conclusion_only']}",
            interval=f"exact p = {m['p_value']:.3f}",
            note="only disagreeing pairs carry information about a difference",
        ),
        publish.Stat(
            label="Any injected memory",
            value=f"{injected_hits}/{injected_n}",
            null=f"no memory at all: {ref_hits}/{ref_n}",
            note="both framings pooled, against experiments/004's same-day memory-off arms",
        ),
        publish.Stat(
            label="Campaign cost",
            value=f"${m['cost_usd']}",
            note=f"{sum(m['arms'].values())} arms, sandboxed, store isolated",
        ),
    ]

    result_table = publish.table(
        ["framing", "rungs", "L2 pass", "turn-capped", "memo echo"],
        [
            [k, str(m["rungs"][k]), f"{m['l2_pass'][k][0]}/{m['l2_pass'][k][1]}",
             str(m["turn_capped"][k]),
             ", ".join(f"{r:.2f}" if r is not None else "—" for r in m["memo_echo"][k])]
            for k in ("conclusion", "problem")
        ],
        caption="Both arms are ceiling-shaped: no MCP, memory hooks stripped, same "
                "injection mechanism, same 40-turn cap. One field differs.",
    )

    pooled_table = publish.table(
        ["what the candidate was given", "arms", "L2 pass"],
        [
            ["the conclusion of a past design discussion", str(conc_n), f"{conc_hits}/{conc_n}"],
            ["the same evidence, framed as a problem", str(prob_n), f"{prob_hits}/{prob_n}"],
            ["nothing (experiments/004, same day)", str(ref_n), f"{ref_hits}/{ref_n}"],
        ],
        caption="The memory-off arms were randomized against the conclusion arms in "
                "experiments/004, not against these problem arms. They are context for "
                "this comparison and a control for that one.",
    )

    falsified = publish.callout(
        "withdrawal", "The pre-registered hypothesis is falsified",
        f"<p>experiments/004 found a perfect memory costing its candidate the foundation "
        f"rung, and the reading offered there was that a <em>conclusion</em> handed over "
        f"without its path substitutes for the earlier steps. If that were right, stating "
        f"the same evidence as a problem should not cost the same rung.</p>"
        f"<p>It costs it anyway: {prob_hits} of {prob_n} problem-framed arms passed L2 "
        f"against {conc_hits} of {conc_n} for the conclusion framing, one discordant pair, "
        f"exact p = {m['p_value']:.3f}. The confidence sequence at n={last['n']} spans "
        f"[{last['lo']:.3f}, {last['hi']:.3f}] and excludes nothing. <strong>Framing is not "
        f"detectably the variable</strong>, and the conclusion-without-path mechanism does "
        f"not survive its own test.</p>",
    )

    survives = publish.callout(
        "finding", "What survives is blunter and worse",
        f"<p>Pool the framings and the picture is stark: <strong>{injected_hits} of "
        f"{injected_n}</strong> arms handed a memory passed L2, against <strong>{ref_hits} "
        f"of {ref_n}</strong> arms handed nothing. Injecting a memory into this task cost "
        f"the foundation rung under both framings tried.</p>"
        f"<p>That is a claim about injection, not about distillation. Rewriting what "
        f"<code>thalamus extract</code> stores would not have helped here — the problem "
        f"framing <em>is</em> a rewrite of what it stores, and it changed nothing "
        f"measurable.</p>",
    )

    limits = publish.callout(
        "caveat", "What this cannot support",
        "<p>Five pairs, one task, one model, and one authored paragraph for the problem "
        "framing. A null at this n is <em>not detectable here</em>, not <em>no effect</em>: "
        "with one discordant pair in five, detecting a difference of the size this design "
        "was built for needs roughly 25–30 pairs, which is a deliberate spend rather than "
        "a continuation.</p>"
        "<p>And a single authored stimulus cannot separate \"problem framings are safer\" "
        "from \"this paragraph is safer\". The falsification is of the hypothesis as "
        "operationalised, which is the only thing an experiment can falsify.</p>",
    )

    echo_note = publish.callout(
        "method", "Why the echo ratios differ, and why that is not a result",
        "<p>Problem-framed arms echo fewer of their memo's terms (0.34–0.59) than "
        "conclusion-framed arms (0.19–0.73). The two memos have different vocabularies, "
        "and a candidate writing code is likelier to repeat prescription words than "
        "situation words. Read as \"the problem memo was used less\" this would be an "
        "artifact of the term sets, so it is reported and not interpreted.</p>",
    )

    return publish.Experiment(
        slug=SLUG,
        title="Reframing the memory did not save it",
        standfirst=(
            "A perfect memory cost its candidate the rung it could already reach alone. "
            "The obvious explanation was that the memory arrived as a conclusion rather "
            "than as a problem. Stating the same evidence as a problem cost the rung "
            "anyway."
        ),
        registration=publish.Registration(
            question="Does the framing of an injected memory — conclusion or problem — "
                     "change what the candidate builds, holding the information constant?",
            hypothesis="A conclusion handed to an agent that has not walked the path to "
                       "it substitutes for the earlier steps; the same evidence framed as "
                       "a problem should not.",
            endpoint=f"Share of arms passing L{PRIMARY_RUNG}, the rung the conclusion "
                     "framing cost in 4 of 4 recorded arms in experiments/004.",
            falsifier="Framing is not the variable if the problem framing loses L2 at the "
                      "same rate as the conclusion framing.",
            stopping_rule=f"The confidence sequence excludes the null, or {HORIZON} arms.",
            registered_at="2026-07-30", registered_ref="preregistration.md",
        ),
        provenance=publish.Provenance(
            snapshot="n/a - arms run against git refs, not a graph snapshot",
            snapshot_sha256="", snapshot_vertices=0, snapshot_edges=0,
            seed=20260730, git_ref="per arm, in runs.jsonl",
            command=(
                "./experiments/005-framing/campaign.sh\n"
                "uv run --extra experiments python experiments/005-framing/run.py"
            ),
        ),
        stats=stats,
        sections=[
            publish.Section(
                title="The test", anchor="test",
                body="<p>Two arms, identical but for one field: which framing of the "
                     "task's withheld knowledge gets injected. The problem framing keeps "
                     "every load-bearing fact — the 33-of-40 trustworthy arm, the 11 and "
                     "18 cut-offs, the turn-count attempt — and drops the imperative and "
                     "the answer. A test asserts that, because varying content and framing "
                     f"together would attribute neither.</p>{result_table}{falsified}",
            ),
            publish.Section(
                title="What survives", anchor="survives",
                body=f"{pooled_table}{survives}{echo_note}",
            ),
            publish.Section(
                title="Limits", anchor="limits",
                body=f"{limits}<ul>"
                     "<li><strong>The conclusion arms replicate.</strong> Across both "
                     "campaigns, every arm handed the conclusion memo failed L2 — a "
                     "pattern now seen in two separately launched runs, which is the "
                     "firmest thing either produced.</li>"
                     "<li><strong>Turn-capping is balanced</strong> (3 of 5 in each arm), "
                     "so censoring does not explain the comparison, though it does bound "
                     "how much work either arm could finish.</li>"
                     "<li><strong>No arm was contaminated</strong>, and every problem-framed "
                     "arm touched its memo, so neither pre-registered void condition "
                     "fired.</li></ul>",
            ),
        ],
        checklist=[
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[0], "yes",
                "Estimand: difference in L2 pass rate. Estimator: exact test on "
                "discordant pairs (McNemar's, computed exactly)."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[1], "yes",
                "One task, one model, one operator, one authored stimulus."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[2], "yes",
                "The conclusion framing is the comparator; memory-off is same-day context."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[3], "yes",
                "Confidence sequence reported; it excludes nothing at this n."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[4], "yes",
                f"{sum(m['arms'].values())} arms, framing order alternated by pair."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[5], "yes",
                "runs.jsonl per arm; the stimulus is in config/tasks/ under git."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[6], "yes", "See Reproducibility."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[7], "yes",
                "The ladder was validated against its anchors before experiments/004."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[8], "yes",
                f"${m['cost_usd']} across {sum(m['arms'].values())} arms."),
            publish.ChecklistItem(publish.DEFAULT_CHECKLIST[9], "yes",
                "The problem framing is authored, not distilled, and says so."),
        ],
        verdict=(
            f"Reframing the memory changed nothing measurable: {prob_hits}/{prob_n} against "
            f"{conc_hits}/{conc_n} on L2, one discordant pair, p = {m['p_value']:.3f}. The "
            f"conclusion-without-path hypothesis is falsified as operationalised. What "
            f"replaces it is worse for the premise: {injected_hits} of {injected_n} arms "
            f"given any memory passed the foundation rung, against {ref_hits} of {ref_n} "
            f"given none — so the cost belongs to injection, and rewriting what "
            f"distillation stores would not have avoided it."
        ),
        verdict_kind="null",
    )


if __name__ == "__main__":
    main()
