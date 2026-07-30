#!/usr/bin/env python
"""Experiment 002 — what "33% of injected tokens are wasted" actually supports.

    uv run --extra experiments python experiments/002-what-the-waste-figure-means/run.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from thalamus.eval import calibration, publish, snapshots, waste  # noqa: E402
from thalamus.eval.attribution import JUDGES  # noqa: E402
from thalamus.substrate.writer import close_connection, connect  # noqa: E402

SLUG = "002-what-the-waste-figure-means"
SNAPSHOT = "post-sandbox-purge-20260730"
SEED = 20260730
ROTATIONS = 200
SCOPE = "main"


def measure(url: str, *, scope: str, rotations: int, seed: int) -> dict:
    g = connect(url)
    try:
        cases, census = calibration.load_cases(g, scope=scope)
    finally:
        close_connection(g)

    judge = JUDGES["shipped"]
    result = calibration.score(cases, judge)
    calibration.rotate(cases, judge, result, rotations=rotations, seed=seed)

    est = waste.estimate(cases, result.verdicts)
    token_rate = waste.token_weighted_rate(cases, result.verdicts)
    token_null = waste.token_weighted_null(cases, result.null_by_case)
    corrected = waste.chance_corrected(token_rate, token_null)

    by_tool: dict[str, dict] = {}
    for case in cases:
        judged = result.verdicts.get(case.trace_id, {})
        share = (case.injected_chars / case.returned_count) if case.returned_count else 0.0
        row = by_tool.setdefault(case.tool, {"injected": 0.0, "wasted": 0.0, "traces": 0})
        row["traces"] += 1
        for used in judged.values():
            row["injected"] += share / waste.CHARS_PER_TOKEN
            if not used:
                row["wasted"] += share / waste.CHARS_PER_TOKEN

    top = est.per_session[:5]
    return {
        "census": census,
        "ratio": est.ratio,
        "se": est.se,
        "ci": list(est.ci),
        "naive_se": est.naive_se,
        "sessions": est.sessions,
        "traces": est.traces,
        "verdicts": est.verdicts,
        "injected_tokens": est.injected_tokens,
        "wasted_tokens": est.wasted_tokens,
        "icc": est.icc,
        "design_effect": est.design_effect,
        "sessions_needed": {
            "5pp": est.sessions_needed(0.05),
            "3pp": est.sessions_needed(0.03),
            "2pp": est.sessions_needed(0.02),
        },
        "token_rate": token_rate,
        "token_null": token_null,
        "corrected_waste": corrected,
        "discordance": result.discordance,
        "concentration": [
            {
                "session": row.session_id[:8],
                "wasted": row.wasted,
                "share": row.wasted / est.wasted_tokens if est.wasted_tokens else 0.0,
                "traces": row.traces,
            }
            for row in top
        ],
        "by_tool": by_tool,
    }


def page(m: dict, *, rotations: int, seed: int, row) -> publish.Experiment:
    corrected_pct = m["corrected_waste"] * 100
    earned_pct = 100 - corrected_pct
    top_share = sum(c["share"] for c in m["concentration"][:3]) * 100
    naive_hw = 1.96 * m["naive_se"] * 100
    hw = (m["ci"][1] - m["ci"][0]) / 2 * 100

    stats = [
        publish.Stat(
            label="Wasted, as reported",
            value=f"{m['ratio'] * 100:.1f}%",
            interval=f"95% CI [{m['ci'][0] * 100:.1f}, {m['ci'][1] * 100:.1f}] · ±{hw:.1f}pp",
            note=f"{m['wasted_tokens']:,.0f} of {m['injected_tokens']:,.0f} injected tokens",
        ),
        publish.Stat(
            label="Demonstrably earned",
            value=f"{earned_pct:.1f}%",
            null=f"token-weighted null {m['token_null'] * 100:.1f}%",
            note="after correcting for what the judge scores on unrelated retrievals",
        ),
        publish.Stat(
            label="Design effect",
            value=f"{m['design_effect']:.2f}×",
            interval=f"ICC {m['icc']:.3f} across {m['sessions']} sessions",
            note="verdicts in one session are not independent draws",
        ),
        publish.Stat(
            label="Sessions for ±3pp",
            value=f"{m['sessions_needed']['3pp']}",
            interval=f"{m['sessions']} today",
            note="at the variance measured here",
        ),
    ]

    interval_table = publish.table(
        ["what is being estimated", "value", "95% interval", "resampling unit"],
        [
            [
                "share of injected tokens the judge called unused",
                f"{m['ratio'] * 100:.1f}%",
                f"[{m['ci'][0] * 100:.1f}, {m['ci'][1] * 100:.1f}] (±{hw:.1f}pp)",
                f"session ({m['sessions']} PSUs, jackknife)",
            ],
            [
                "the same, if verdicts were independent draws",
                f"{m['ratio'] * 100:.1f}%",
                f"±{naive_hw:.1f}pp",
                f"verdict ({m['verdicts']:,}) — wrong, shown for scale",
            ],
            [
                "share not distinguishable from topic overlap",
                f"{corrected_pct:.1f}%",
                "not yet interval-bounded (see below)",
                "token-weighted, chance-corrected",
            ],
        ],
        caption="Three different quantities that a bare '33% wasted' has been used to mean.",
    )

    n_table = publish.table(
        ["target precision", "sessions needed", "multiple of today"],
        [
            [f"±{pp}pp", f"{m['sessions_needed'][f'{pp}pp']}", f"{m['sessions_needed'][f'{pp}pp'] / m['sessions']:.1f}×"]
            for pp in (5, 3, 2)
        ],
        caption=f"From the measured jackknife SE of {m['se']:.4f} at {m['sessions']} sessions, "
        "scaling as 1/√n. A superpopulation statement about sessions not yet had.",
    )

    tool_rows = sorted(m["by_tool"].items(), key=lambda kv: -kv[1]["wasted"])
    tool_table = publish.table(
        ["tool", "retrievals", "injected tokens", "wasted", "waste share"],
        [
            [
                tool,
                f"{d['traces']}",
                f"{d['injected']:,.0f}",
                f"{d['wasted']:,.0f}",
                f"{d['wasted'] / d['injected'] * 100:.1f}%" if d["injected"] else "—",
            ]
            for tool, d in tool_rows
        ],
    )

    conc_table = publish.table(
        ["session", "retrievals", "wasted tokens", "share of all waste"],
        [
            [c["session"], f"{c['traces']}", f"{c['wasted']:,.0f}", f"{c['share'] * 100:.1f}%"]
            for c in m["concentration"]
        ],
        caption="Waste is concentrated, which is why the session is the sampling unit.",
    )

    sections = [
        publish.Section(
            title="Three numbers wearing one name",
            anchor="three",
            body=f"""
<p>Thalamus prices every retrieval: the rendered block has a size, and each node in
it carries a share. Multiply that share by whether the judge called the node used,
and you get the figure the tooling prints — <strong>{m['ratio'] * 100:.1f}% of injected
tokens wasted</strong>.</p>

<p>That figure has been quoted three ways, and they are not the same quantity.</p>
{interval_table}
{publish.callout("method", "Why the session is the unit", f'''
<p>Verdicts inside one session share an output window, a topic and an operator, so
they are not independent draws. Measured here: ICC {m['icc']:.3f}, design effect
{m['design_effect']:.2f}×. Treating {m['verdicts']:,} verdicts as {m['verdicts']:,}
observations would report ±{naive_hw:.1f}pp where the honest interval is ±{hw:.1f}pp.
The estimator is a ratio of totals with a delete-one-session jackknife.</p>''')}
""",
        ),
        publish.Section(
            title="The correction that changes the sentence",
            anchor="correction",
            body=f"""
<p>The interval above prices sampling error only. The deeper problem is what "used"
means: the same judge, pointed at an <em>unrelated</em> session's output, still calls
{m['token_null'] * 100:.1f}% of tokens used (experiment 001, token-weighted here rather
than node-weighted, because the nodes that dominate the token budget are not the ones
that dominate the count).</p>

<p>Correcting for that — κ on the token scale — leaves
<strong>{earned_pct:.1f}% of injected tokens demonstrably earned</strong>. The
defensible sentence is not "a third of the tokens are wasted". It is:</p>

{publish.callout("finding", "What the corpus supports", f'''
<p>About <strong>{earned_pct:.0f}%</strong> of injected retrieval tokens are
demonstrably earned. The remaining <strong>{corrected_pct:.0f}%</strong> is not
distinguishable, by this instrument, from tokens that would have looked equally
"used" had they been retrieved for a different session entirely.</p>
<p>That is not a claim that {corrected_pct:.0f}% of the memory is useless. It is a
statement about the instrument's resolution: it cannot tell the difference, and
neither can anyone quoting its output.</p>''')}

<p>This corrected figure has no interval yet, and that is deliberate rather than an
oversight. Its uncertainty is the uncertainty of a difference between two rates
measured on the same verdicts, which needs the paired estimator experiment 001 built
for κ — extended to token weights. Pending that, it is reported as a bound with its
inputs shown, not as a point estimate with a false interval.</p>
""",
        ),
        publish.Section(
            title="How much more data would fix the interval",
            anchor="power",
            body=f"""
<p>The uncorrected figure's precision is a straightforward function of session count
at the variance measured here.</p>
{n_table}
<p>The corrected figure is much harder. Its estimand is a difference of about
{(m['token_rate'] - m['token_null']) * 100:.1f} points between two rates on the same
verdicts, and verdicts flip under rotation {m['discordance'] * 100:.1f}% of the time.
Bounding that difference to ±1 point needs roughly
{int(m['discordance'] / ((0.01 / 1.96) ** 2) * m['design_effect']):,} verdicts —
around {int(m['discordance'] / ((0.01 / 1.96) ** 2) * m['design_effect'] / (m['verdicts'] / m['sessions']))}
sessions at this corpus's {m['verdicts'] / m['sessions']:.0f} verdicts per session,
against {m['sessions']} today.</p>
{publish.callout("finding", "Precision on the uncorrected figure is reachable; on the corrected one it is not", f'''
<p>{m['sessions_needed']['3pp']} sessions is a matter of months at one operator's
working rate. The number needed to pin the corrected figure is an order of magnitude
beyond that. So the uncorrected waste rate can be made precise by waiting, and the
quantity anyone actually cares about cannot — which is the argument for changing the
instrument rather than growing the corpus.</p>''')}
""",
        ),
        publish.Section(
            title="Where the waste sits",
            anchor="breakdown",
            body=f"""
{tool_table}
{conc_table}
<p>The top three sessions carry {top_share:.0f}% of all wasted tokens. Concentration
that heavy is the substantive reason the session is the sampling unit, and it is also
a hint about where a targeted fix would pay: a retrieval-shape change that only
affects long sessions would move most of this number.</p>
""",
        ),
        publish.Section(
            title="Threats to this result",
            anchor="threats",
            body=f"""
{publish.callout("caveat", "The per-node price is uniform, and nodes are not", '''
<p>The graph records the size of the whole rendered block and the number of nodes in
it, not the size of each node. So the price is <code>injected_chars /
returned_count</code>: a 40-token thread title and a 400-token claim in the same
retrieval are charged identically. The direction of the bias depends on whether long
nodes are used more often than short ones — which is measurable, and is not measured
here. Until it is, read every token figure as node-count-weighted in disguise.</p>''')}

{publish.callout("caveat", "Injected once, paid for repeatedly", '''
<p>A retrieval's tokens ride along in every subsequent API call of the session, so
the true cost of a wasted retrieval is its size times the number of later calls. The
cost module counts that multiplier separately and this experiment does not use it:
these are single-injection tokens, which understates the real spend by a factor
nobody has pinned.</p>''')}

<ul>
<li><strong>Non-retrieval is invisible.</strong> A node that was never returned has
no edge, so this frame can price what retrieval cost but never what forgetting cost.</li>
<li><strong>One operator, one machine, one harness configuration.</strong> The n
calculations are superpopulation statements about that operator's future sessions.</li>
<li><strong>27% of verdicts sit on mutable node text</strong> (experiment 001):
threads and sessions are overwritten latest-wins, so some of these verdicts price
text that has since changed.</li>
</ul>
""",
        ),
    ]

    checklist = [
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[0], "yes",
            "Estimand: wasted / injected tokens. Estimator: ratio of totals, sessions as PSUs, "
            "delete-one-session jackknife.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[1], "yes", "One operator; superpopulation over future sessions."
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[2], "yes",
            f"Token-weighted permuted null {m['token_null'] * 100:.1f}% from {rotations} rotations.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[3], "yes",
            "Session-clustered. The naive verdict-level interval is shown beside it for scale.",
        ),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[4], "yes", f"seed {seed}, {rotations} rotations."),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[5], "yes", f"snapshot {row.name}, sha256 {row.sha256[:16]}."
        ),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[6], "yes", "See Reproducibility."),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[7], "no",
            "No human-labelled gold set exists yet, so the judge underlying the estimand is "
            "bounded against chance but not against truth.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[8], "yes", "This experiment is the cost side of the frontier."
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[9], "yes",
            "The corrected figure is reported without an interval, and the reason is stated "
            "rather than a placeholder being supplied.",
        ),
    ]

    return publish.Experiment(
        slug=SLUG,
        title="What “a third of the tokens are wasted” actually supports",
        standfirst=(
            f"Thalamus reports {m['ratio'] * 100:.0f}% of injected memory tokens as unused. With "
            f"sessions as the sampling unit that is {m['ratio'] * 100:.1f}% ±{hw:.1f}pp — and once "
            f"corrected for a judge that calls {m['token_null'] * 100:.0f}% of unrelated tokens used, "
            f"what the corpus supports is that about {earned_pct:.0f}% of injected tokens are "
            f"demonstrably earned."
        ),
        registration=publish.Registration(
            question="What interval does the token-waste figure carry once the clustering of "
            "verdicts inside sessions is respected, and what does it become after correcting "
            "for the judge's chance level?",
            hypothesis="The published point estimate is materially less precise than it looks, "
            "and the chance correction changes the headline more than the interval does.",
            endpoint="Ratio of totals (wasted / injected tokens), sessions as primary sampling "
            "units, delete-one-session jackknife; plus the token-weighted chance-corrected share.",
            falsifier="If the session-clustered interval is no wider than the verdict-level one, "
            "clustering is not material here and the simpler estimator stands.",
            stopping_rule="Census at the pinned snapshot; no sampling decision to stop. "
            f"{rotations} rotations for the null, fixed before the run.",
            registered_at="2026-07-30",
            registered_ref="preregistration.md",
        ),
        provenance=publish.Provenance(
            snapshot=row.name,
            snapshot_sha256=row.sha256,
            snapshot_vertices=row.vertices,
            snapshot_edges=row.edges,
            seed=seed,
            git_ref=row.git_ref,
            command=(
                "thalamus snapshot --list\n"
                "uv run --extra experiments python \\\n"
                f"    experiments/{SLUG}/run.py --rotations {rotations} --seed {seed}"
            ),
        ),
        stats=stats,
        sections=sections,
        checklist=checklist,
        verdict=(
            f"{m['ratio'] * 100:.1f}% of injected tokens were judged unused, 95% CI "
            f"[{m['ci'][0] * 100:.1f}, {m['ci'][1] * 100:.1f}] with sessions as the sampling unit — "
            f"a ±{hw:.1f}pp interval where the verdict-level one would have claimed ±{naive_hw:.1f}pp. "
            f"Chance-corrected, the supportable claim is that about {earned_pct:.0f}% of injected "
            f"tokens are demonstrably earned. Reaching ±3pp on the uncorrected figure needs "
            f"{m['sessions_needed']['3pp']} sessions; the corrected one cannot be reached by waiting."
        ),
        verdict_kind="measured",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotations", type=int, default=ROTATIONS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--scope", default=SCOPE)
    parser.add_argument("--snapshot", default=SNAPSHOT)
    args = parser.parse_args()

    row = snapshots.find(args.snapshot)
    print(f"[1/2] measuring against {row.name}")
    with snapshots.serve(args.snapshot) as url:
        m = measure(url, scope=args.scope, rotations=args.rotations, seed=args.seed)
    print(f"      R = {m['ratio']:.4f} [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}] over {m['sessions']} sessions")

    print("[2/2] rendering")
    experiment = page(m, rotations=args.rotations, seed=args.seed, row=row)
    results_path, page_path = publish.write(
        experiment,
        Path(__file__).resolve().parent,
        {"measurement": m, "rotations": args.rotations, "seed": args.seed},
    )
    print(f"      {results_path.relative_to(REPO)}")
    print(f"      {page_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
