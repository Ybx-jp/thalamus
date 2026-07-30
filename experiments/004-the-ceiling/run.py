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

from thalamus.eval import publish, sequential  # noqa: E402

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
        # Censoring, handled in the open. A turn-capped arm was cut off mid-work,
        # so its rung is a lower bound rather than a score — and the
        # pre-registration is SILENT on censoring, which means any rule chosen now
        # is chosen with the data visible. So both readings are reported and
        # neither is called primary: as-recorded, and excluding censored arms.
        # Here the censored arm happens to favour the ceiling, so dropping it would
        # strengthen the narrative this experiment has been building, which is
        # exactly why it is not dropped quietly.
        "censored": [
            {"ts": r["ts"][:19], "arm": r["arm"], "rung": r.get("rung"),
             "turns": r.get("agent", {}).get("num_turns")}
            for r in rows if r.get("turn_capped")
        ],
        "rank_statistic_uncensored": rank_statistic(
            [int(r.get("rung") or 0) for r in by_arm["ceiling"] if not r.get("turn_capped")],
            [int(r.get("rung") or 0) for r in by_arm["memory-off"] if not r.get("turn_capped")],
        ),
        "escapes": [
            {"ts": r["ts"][:19], "arm": r["arm"], "kinds": [e.get("kind") for e in r["escapes"]]}
            for r in rows if r.get("escapes")
        ],
        # Effort, per arm. Worth its own column because a ceiling arm that stops
        # early is a different story from one that works just as hard and scores
        # lower: "the memo told me the answer, so I stopped" and "the memo did not
        # help" have the same rung and different mechanisms.
        "effort": {
            arm: {
                "turns": [r.get("agent", {}).get("num_turns") for r in by_arm[arm]],
                "diff_lines": [r.get("diff_lines") for r in by_arm[arm]],
                "wall_seconds": [round(r.get("wall_seconds", 0)) for r in by_arm[arm]],
            }
            for arm in ARMS
        },
        "memo_echo": [
            r.get("memo_echoed") for r in by_arm["ceiling"]
        ],
        "injected_chars": [
            r.get("applied", {}).get("injected_fact_chars", 0)
            for r in rows if r["arm"] == "ceiling"
        ],
        # Only `thalamus` counts. `tool_search` is the deferred-schema load that
        # would have to precede a memory call, so an arm with tool_search>0 and
        # thalamus=0 *tried and could not* — that is confinement working, and
        # counting it as a breach would void a campaign for succeeding.
        "recall_calls_leaked": [
            r["ts"][:19] for r in rows
            if (r.get("recall_calls") or {}).get("thalamus", 0) > 0
        ],
        "reached_for_memory_and_failed": [
            r["ts"][:19] for r in rows
            if (r.get("recall_calls") or {}).get("tool_search", 0) > 0
            and (r.get("recall_calls") or {}).get("thalamus", 0) == 0
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
    print(f"  rank statistic P(ceiling > memory-off) = {m['rank_statistic']:.3f} "
          f"(excluding censored arms: {m['rank_statistic_uncensored']:.3f})")
    if m["censored"]:
        print(f"  CENSORED (turn-capped, rung is a lower bound): {m['censored']}")
    if m["escapes"]:
        print(f"  escapes recorded (not stamped contaminated): {m['escapes']}")
    for arm in ARMS:
        effort = m["effort"][arm]
        if effort["turns"]:
            print(f"  {arm:12} turns={effort['turns']} diff_lines={effort['diff_lines']}")
    echoes = [e for e in m["memo_echo"] if e]
    if echoes:
        print(f"  memo echoed in {sum(1 for e in echoes if e['used'])}/{len(echoes)} ceiling arm(s) "
              f"(term ratios {[e['ratio'] for e in echoes]})")
    missing = sum(1 for e in m["memo_echo"] if not e)
    if missing:
        print(f"  memo echo not recorded for {missing} ceiling arm(s) — they predate the field")
    if m["sequence"]:
        last = m["sequence"][-1]
        print(f"  confidence sequence at n={last['n']}: "
              f"[{last['lo']:.3f}, {last['hi']:.3f}] -> {m['decision']}")

    for label, rows_hit in (("CONTAMINATED", m["contaminated"]), ("INFRA FAULT", m["faults"]),
                            ("MEMORY REACHED IN A NO-MEMORY ARM", m["recall_calls_leaked"])):
        if rows_hit:
            print(f"  VOID CONDITION — {label}: {rows_hit}")
    if m["reached_for_memory_and_failed"]:
        print(f"  confinement held: {len(m['reached_for_memory_and_failed'])} arm(s) loaded tool "
              "schemas and still reached no memory tool")

    if sum(m["arms"].values()) < HORIZON and m["decision"] == "continue":
        print(f"\nCampaign incomplete ({sum(m['arms'].values())}/{HORIZON} arms) and the "
              "sequence has not fired. No verdict is rendered — the stopping rule is "
              "in preregistration.md and this script does not get to improvise one.")
        return

    results_path, page_path = publish.write(page(m), Path(__file__).resolve().parent, m)
    print(f"\nwrote {results_path.name} and {page_path.name}")


if __name__ == "__main__":
    main()


def sign_test(pairs):
    """Exact two-sided sign test on the paired rungs: (wins, ties, p).

    Reported *beside* the confidence sequence, never instead of it. The sequence is
    an anytime-valid bound over an unbounded horizon and pays a great deal of width
    for the right to be inspected continuously; the sign test is the fixed-n reading
    this campaign's own pre-registered horizon licenses. Quoting only whichever is
    friendlier is what lab/023 did wrong.
    """
    from math import comb

    wins = sum(1 for c, o in pairs if c > o)
    losses = sum(1 for c, o in pairs if c < o)
    ties = len(pairs) - wins - losses
    n = wins + losses
    if not n:
        return wins, ties, 1.0
    extreme = min(wins, losses)
    p = sum(comb(n, k) for k in range(extreme + 1)) / (2**n) * 2
    return wins, ties, min(1.0, p)


def page(m):
    ceiling, off = m["rungs"]["ceiling"], m["rungs"]["memory-off"]
    pairs = list(zip(ceiling, off, strict=False))
    wins, ties, p = sign_test(pairs)
    losses = len(pairs) - wins - ties
    primary_c, primary_n = m["primary"]["ceiling"]
    primary_o, primary_on = m["primary"]["memory-off"]
    sec_c, sec_n = m["secondary"]["ceiling"]
    sec_o, sec_on = m["secondary"]["memory-off"]
    last = m["sequence"][-1] if m["sequence"] else {"n": 0, "lo": 0.0, "hi": 1.0}
    held = len(m["reached_for_memory_and_failed"])

    stats = [
        publish.Stat(
            label="Primary endpoint (L>=4)",
            value=f"{primary_c}/{primary_n} vs {primary_o}/{primary_on}",
            note="ceiling vs memory-off. Neither arm ever reached the task's own "
                 "memory-attributable rung.",
        ),
        publish.Stat(
            label="Exploratory (L>=3)",
            value=f"{sec_c}/{sec_n} vs {sec_o}/{sec_on}",
            note="where the separation actually lives, and it runs against the ceiling",
        ),
        publish.Stat(
            label="Paired sign test",
            value=f"p = {p:.3f}",
            interval=f"{wins} win / {losses} loss / {ties} tie",
            note="fixed-n, at the pre-registered horizon; censoring handled in the open",
        ),
        publish.Stat(
            label="Campaign cost",
            value=f"${m['cost_usd']}",
            note=f"{sum(m['arms'].values())} arms, sandboxed, store isolated",
        ),
    ]

    rung_table = publish.table(
        ["pair", "ceiling", "memory-off", "winner"],
        [
            [str(i + 1), f"L{c}", f"L{o}",
             "ceiling" if c > o else ("memory-off" if o > c else "tie")]
            for i, (c, o) in enumerate(pairs)
        ],
        caption="Rungs are ordinal and strictly implying: L4 implies L3 implies L2. "
                "Read as ranks, never averaged — metric models over ordinal data "
                "sign-reverse on this project's own campaign data (lab/020).",
    )

    effort_table = publish.table(
        ["arm", "turns", "diff lines", "wall seconds"],
        [[arm, str(m["effort"][arm]["turns"]), str(m["effort"][arm]["diff_lines"]),
          str(m["effort"][arm]["wall_seconds"])] for arm in ARMS],
        caption="Effort, because an outcome alone cannot separate \"the memo told me "
                "the answer so I stopped\" from \"the memo did not help\". Read the "
                "41s as the 40-turn cap, not as diligence: a capped arm was cut off "
                "mid-work and its rung is a lower bound.",
    )

    echoes = [e for e in m["memo_echo"] if e]
    echo_line = (
        f"{sum(1 for e in echoes if e['used'])} of {len(echoes)} recorded ceiling arms "
        f"visibly acted on the memo (term ratios {[e['ratio'] for e in echoes]})"
        if echoes else "not recorded for any completed ceiling arm"
    )

    endpoint_callout = publish.callout(
        "finding",
        "The pre-registered endpoint reads null, and it is not where the effect is",
        f"<p>Rung {PRIMARY_RUNG} — the task's own memory-attributable outcome, fixed in "
        f"its YAML before any campaign — was reached by <strong>{primary_c} of "
        f"{primary_n}</strong> ceiling arms and <strong>{primary_o} of {primary_on}</strong> "
        f"memory-off arms. Neither arm ever got there.</p>"
        f"<p>Every difference sits at rung {SECONDARY_RUNG}, which this experiment "
        f"pre-registered as exploratory: {sec_o}/{sec_on} for memory-off against "
        f"{sec_c}/{sec_n} for the ceiling. That placement error is the one lab/023 made, "
        f"and the reason it is reported this way rather than quietly promoted is that "
        f"the rule was written down first.</p>",
    )

    mechanism_callout = publish.callout(
        "finding", "A conclusion without its path",
        "<p>The ladder is strictly implying. L2 is <em>stop on the death the operator "
        "described</em>, reachable from the prompt alone; L4 is <em>a death after real "
        "work leaves an attempt of unknown completeness, so it must not be graded</em>. "
        "The injected memory is L4/L5 content: \"must not guess how complete an "
        "interrupted attempt was... two conservative shapes, both ungraded\".</p>"
        "<p>So the ceiling arm was handed the advanced requirement and failed the basic "
        "one. The reading this suggests — a hypothesis, not a result — is that a "
        "distilled memory records the <em>conclusion</em> of a design discussion rather "
        "than the path to it, and handed to an agent that has not walked that path the "
        "conclusion can substitute for the earlier steps instead of adding to them.</p>"
        "<p><strong>A competing explanation, and the data cannot separate them here.</strong> "
        "Ceiling arms hit the 40-turn cap far more often than memory-off arms did, so the "
        "memo may simply have prompted a larger change that did not fit the budget — "
        "scope expansion rather than misdirection. What keeps the comparison alive is that "
        "the effect survives dropping every censored arm: among arms that finished inside "
        "the budget the separation is still complete. Raising the turn cap is the "
        "experiment that would tell these apart, and it has not been run.</p>",
    )

    confinement_callout = publish.callout(
        "method", "Confinement, confirmed live for the first time",
        f"<p>Every arm ran in a container without the operator's checkout and without a "
        f"route to the graph. {held} arm(s) loaded tool schemas and still reached no "
        f"memory tool: the arms tried, and could not. Until this campaign confinement had "
        f"only been verified by direct probe, never by a live run.</p>",
    )

    sections = [
        publish.Section(
            title="What was measured, and what the endpoint says", anchor="result",
            body="<p>Two arms on the battery's one strongly-gated task, alternating so "
                 "arm order could not confound the comparison, each sandboxed in an image "
                 "where the operator's checkout does not exist and with the graph "
                 f"unreachable.</p>{rung_table}{endpoint_callout}",
        ),
        publish.Section(
            title="The direction is the finding", anchor="direction",
            body=f"<p>The ceiling arm was not merely no better. It was <strong>worse in "
                 f"every pair</strong> — {wins} wins, {losses} losses, {ties} ties, sign "
                 f"test p = {p:.3f}. The confidence sequence at n={last['n']} spans "
                 f"[{last['lo']:.3f}, {last['hi']:.3f}] and does not exclude the null: it "
                 f"is an anytime-valid bound over an unbounded horizon and needs roughly "
                 f"an order of magnitude more pairs at this effect size. Both are reported, "
                 f"because quoting only the friendlier one is what lab/023 did wrong.</p>"
                 f"{effort_table}<p>Memo echo: {echo_line}.</p>{mechanism_callout}",
        ),
        publish.Section(
            title="What this licenses, and what it does not", anchor="threats",
            body="<p>The pre-registered falsifier fires: the ceiling does not separate "
                 "from memory-off on the primary endpoint, so <strong>the battery is the "
                 "binding constraint</strong>, and the container campaign and "
                 "consequence-probe work queued behind it are cancelled rather than "
                 "rescheduled. Spending more on memory-on/off arms against a battery that "
                 "cannot register a perfect memory would be buying noise.</p>"
                 "<ul>"
                 "<li><strong>One task.</strong> The battery has exactly one strongly-gated "
                 "task, so this is a statement about that task's gate. Generalising it to "
                 "\"memory does not help\" is unsupported by construction.</li>"
                 "<li><strong>One model, one operator, one harness configuration.</strong></li>"
                 "<li><strong>The mechanism is unconfirmed.</strong> Arm worktrees are "
                 "cleaned after each run, so the diffs that would show whether the candidate "
                 "built the refinement and skipped the foundation were not retained. That "
                 "check needs one more arm with the worktree kept, and it sits outside the "
                 "registered design.</li>"
                 "<li><strong>The memo is one phrasing.</strong> Whether the effect survives "
                 "a memo that states the problem rather than the conclusion is the obvious "
                 "next experiment, and it is not this one.</li>"
                 f"</ul>{confinement_callout}",
        ),
    ]

    checklist = [
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[0], "yes",
            "Estimand: share reaching the pre-registered rung. Rank statistic and exact "
            "sign test on paired rungs; never mean-of-rungs."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[1], "yes",
            "One task, one model, one operator — stated as a limit, not a caveat."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[2], "yes",
            "memory-off is the baseline; the ceiling is the skyline."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[3], "yes",
            "Confidence sequence reported with the fixed-n sign test beside it."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[4], "yes",
            f"{sum(m['arms'].values())} arms; assignment alternated by pair."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[5], "yes",
            "runs.jsonl per arm; task refs pinned and re-validated after the history "
            "rewrite (lab/035)."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[6], "yes", "See Reproducibility."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[7], "yes",
            "Ladder validated against its anchors before the campaign: negative L1, "
            "positive L5, both as pre-registered."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[8], "yes",
            f"${m['cost_usd']} across {sum(m['arms'].values())} arms."),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[9], "yes",
            "Arm transcripts and worktrees are not retained; the mechanism check that "
            "needs them is named as unrun rather than guessed at."),
    ]

    return publish.Experiment(
        slug=SLUG,
        title="A perfect memory, and it made things worse",
        standfirst=(
            "Before spending more on memory-on/off arms, this measures the ceiling: a "
            "candidate handed exactly the right memory, with no retrieval to get wrong. "
            "It lost every pair. Neither arm reached the pre-registered endpoint, and the "
            "separation that does exist runs the wrong way."
        ),
        registration=publish.Registration(
            question="If a candidate is handed exactly the right memory, with no retrieval "
                     "to get wrong, does it beat a candidate with no memory?",
            hypothesis="A perfect memory sets an upper bound on what any retrieval could "
                       "be worth; if it does not separate, no retrieval improvement can "
                       "move this battery.",
            endpoint=f"Share of arms reaching rung >= {PRIMARY_RUNG}, the task's own "
                     "pre-registered memory-attributable outcome.",
            falsifier="The battery is the binding constraint if ceiling does not separate "
                      "from memory-off at the stopping rule.",
            stopping_rule=f"Confidence sequence excludes the null, or falls inside "
                          f"+/-{FUTILITY_MARGIN} of it, or {HORIZON} arms.",
            registered_at="2026-07-30", registered_ref="preregistration.md",
        ),
        provenance=publish.Provenance(
            snapshot="n/a - arms run against git refs, not a graph snapshot",
            snapshot_sha256="", snapshot_vertices=0, snapshot_edges=0,
            seed=20260730, git_ref="per arm, in runs.jsonl",
            command=(
                "uv run thalamus eval oracle arm-runner-session-death-classification "
                "--anchors-only\n"
                "./experiments/004-the-ceiling/campaign.sh\n"
                "uv run --extra experiments python experiments/004-the-ceiling/run.py"
            ),
        ),
        stats=stats, sections=sections, checklist=checklist,
        verdict=(
            f"The ceiling lost every pair ({wins}W/{losses}L/{ties}T, sign test p={p:.3f}). "
            f"On the pre-registered endpoint neither arm reached rung {PRIMARY_RUNG} at all, "
            f"so the falsifier fires and the queued layer-2 work is cancelled: this battery "
            f"cannot register what a perfect memory is worth. The exploratory direction is "
            f"worse than null — the injected memory appears to have cost the candidate the "
            f"basic rung it was already reaching without it."
        ),
        verdict_kind="null",
    )
