#!/usr/bin/env python
"""Experiment 001 — how much of the used-rate is retrieval utility?

Regenerates every number and figure in `index.html` from a pinned snapshot and a
seed. Nothing reads the live graph.

    uv run --extra experiments python experiments/001-the-topic-detector/run.py

Takes a few minutes: the rotation re-judges every case against another session's
output window, once per rotation, for every judge variant.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from thalamus.eval import calibration, publish, snapshots  # noqa: E402
from thalamus.eval.attribution import JUDGES  # noqa: E402
from thalamus.substrate.writer import close_connection, connect  # noqa: E402

SLUG = "001-the-topic-detector"
SNAPSHOT = "post-sandbox-purge-20260730"
CONTRAST = "pre-sandbox-purge"
SEED = 20260730
ROTATIONS = 200
SCOPE = "main"
JUDGE_ORDER = ["shipped", "prose", "tool", "bounded-10", "bounded-3", "bounded-1", "tool-bounded-3"]


def measure(url: str, *, scope: str, rotations: int, seed: int) -> dict:
    """Score every judge and its null against one pinned graph state."""
    g = connect(url)
    try:
        cases, census = calibration.load_cases(g, scope=scope)
    finally:
        close_connection(g)

    results = calibration.calibrate(cases, judges=JUDGE_ORDER, rotations=rotations, seed=seed)
    matched, total = calibration.fidelity(cases, results["shipped"])

    judges = {}
    for name in JUDGE_ORDER:
        result = results[name]
        lo, hi = calibration.cluster_bootstrap(cases, result, seed=seed)
        k_lo, k_hi = calibration.kappa_ci(cases, result, seed=seed)
        judges[name] = {
            "rate": result.rate,
            "rate_ci": [lo, hi],
            "null": result.null_mean,
            "null_ci": list(result.null_ci),
            "kappa": result.kappa,
            "kappa_ci": [k_lo, k_hi],
            "odds_ratio": _odds_ratio(result.rate, result.null_mean),
            "discordance": result.discordance,
            "unpartnered": result.unpartnered,
            "used": result.used,
            "total": result.total,
        }

    # The null's *design* as a variable. lab/032 rotated without a length stratum;
    # this run rotates within one. Reporting both on one corpus is what separates
    # "the instrument changed" from "the yardstick changed".
    flat = calibration.score(cases, JUDGES["shipped"])
    calibration.rotate(
        cases, JUDGES["shipped"], flat, rotations=rotations, seed=seed, stratified=False
    )
    flat_lo, flat_hi = calibration.kappa_ci(cases, flat, seed=seed)

    # Claims are content-addressed, so their text is the text that was judged.
    # Threads and Sessions are upserted latest-wins and can have changed underneath
    # a stored verdict with nothing recording it.
    claim_cases = calibration.restrict(cases, {"claim"})
    claim_result = calibration.score(claim_cases, JUDGES["shipped"])
    calibration.rotate(
        claim_cases, JUDGES["shipped"], claim_result, rotations=rotations, seed=seed
    )
    c_lo, c_hi = calibration.kappa_ci(claim_cases, claim_result, seed=seed)

    shipped = results["shipped"]
    return {
        "null_design": {
            "stratified": {
                "null": shipped.null_mean,
                "kappa": shipped.kappa,
                "kappa_ci": list(judges["shipped"]["kappa_ci"]),
            },
            "unstratified": {
                "null": flat.null_mean,
                "kappa": flat.kappa,
                "kappa_ci": [flat_lo, flat_hi],
            },
        },
        "claims_only": {
            "verdicts": claim_result.total,
            "rate": claim_result.rate,
            "null": claim_result.null_mean,
            "kappa": claim_result.kappa,
            "kappa_ci": [c_lo, c_hi],
            "sessions": len({c.session_id for c in claim_cases}),
        },
        "census": census,
        "cases": len(cases),
        "sessions": len({c.session_id for c in cases}),
        "verdicts": shipped.total,
        "fidelity": {"matched": matched, "total": total},
        "window_chars": {
            "median": statistics.median([c.window_chars for c in cases]) if cases else 0,
            "max": max([c.window_chars for c in cases], default=0),
        },
        "judges": judges,
        "by_tool": {
            tool: {"used": u, "total": t}
            for tool, (u, t) in calibration.by_dimension(
                cases, shipped, lambda case, node: case.tool
            ).items()
        },
        "by_kind": {
            kind: {"used": u, "total": t}
            for kind, (u, t) in calibration.by_dimension(
                cases, shipped, lambda case, node: calibration.node_kind(node)
            ).items()
        },
        "by_stratum": {
            str(stratum): {"used": u, "total": t}
            for stratum, (u, t) in calibration.by_dimension(
                cases, shipped, lambda case, node: case.stratum
            ).items()
        },
    }


def _odds_ratio(rate: float, null: float) -> float:
    """Odds of "used" under the real window against odds under a rotated one.

    Reported beside κ because the two disagree about the bounded judges, and the
    disagreement is informative: κ divides by the headroom above the null, so a
    judge whose null is near zero is scored on a scale where a tiny absolute gain
    looks small; the odds ratio does not rescale. Neither column is publishable
    alone.
    """
    if not 0 < rate < 1 or not 0 < null < 1:
        return float("nan")
    return (rate / (1 - rate)) / (null / (1 - null))


def verdicts_needed(delta: float, discordance: float, design_effect: float = 4.0) -> int:
    """Raw verdicts needed to bound the real-minus-null gap to ±0.010.

    Paired binary difference: SE(Δ) ≈ √(d/n), so n_eff = d / SE², and the cluster
    design effect converts effective verdicts into raw ones. Both inputs are
    measured here rather than assumed — `d` especially, since the required n scales
    linearly in it.
    """
    target_se = delta / 1.96
    n_eff = discordance / (target_se**2)
    return int(n_eff * design_effect)


def page(post: dict, pre: dict | None, *, rotations: int, seed: int, snapshot_row) -> publish.Experiment:
    j = post["judges"]
    shipped = j["shipped"]
    nd = post["null_design"]
    co = post["claims_only"]
    ranked = sorted(JUDGE_ORDER, key=lambda name: j[name]["kappa"], reverse=True)
    best, runner_up = ranked[0], ranked[1]
    fid = post["fidelity"]
    fidelity_rate = fid["matched"] / fid["total"] if fid["total"] else 0.0
    n_needed = verdicts_needed(0.010, shipped["discordance"])
    sessions_needed = int(n_needed / (post["verdicts"] / max(1, post["sessions"])))

    stats = [
        publish.Stat(
            label="Used, as reported today",
            value=f"{shipped['rate'] * 100:.1f}%",
            interval=f"95% CI [{shipped['rate_ci'][0] * 100:.1f}, {shipped['rate_ci'][1] * 100:.1f}], "
            f"clustered on {post['sessions']} sessions",
            null=f"permuted null {shipped['null'] * 100:.1f}%",
        ),
        publish.Stat(
            label="κ — headroom captured",
            value=f"{shipped['kappa']:.3f}",
            note="the share of the available signal the shipped judge actually carries",
        ),
        publish.Stat(
            label="Best of 7 judges",
            value=("none beat it" if best == "shipped" else best),
            interval=(
                f"runner-up {runner_up} at κ {j[runner_up]['kappa']:.3f}"
                if best == "shipped"
                else f"κ {j[best]['kappa']:.3f} vs {shipped['kappa']:.3f} shipped"
            ),
            note=(
                "six pre-registered alternatives, all scored against their own null"
                if best == "shipped"
                else JUDGES[best].description
            ),
        ),
        publish.Stat(
            label="Verdicts in the corpus",
            value=f"{post['verdicts']:,}",
            note=f"{post['cases']} retrievals across {post['sessions']} sessions",
        ),
    ]

    tool_gap = j["tool"]["kappa"] - shipped["kappa"]
    null_halfwidth = (shipped["null_ci"][1] - shipped["null_ci"][0]) / 2
    tool_wins = tool_gap > null_halfwidth
    split_callout = publish.callout(
        "finding" if tool_wins else "caveat",
        "The pre-registered split, tested"
        if tool_wins
        else "The pre-registered hypothesis is falsified",
        (
            f'''<p>Restricting the judge to <strong>tool-call inputs</strong> — a path, a
command, a parameter echoed after the retrieval rather than a word in prose — moves κ
from {shipped['kappa']:.3f} to {j['tool']['kappa']:.3f}, a gain of {tool_gap:+.3f} against a
null half-width of {null_halfwidth:.3f}. Acting on a retrieved path is a narrower
coincidence than repeating a word, and the data agrees.</p>'''
            if tool_wins
            else f'''<p>The hypothesis was that tool-call inputs would discriminate better than
prose, because acting on a retrieved path is a narrower coincidence than repeating a
word. It does not: κ moves {tool_gap:+.3f}, from {shipped['kappa']:.3f} shipped to
{j['tool']['kappa']:.3f}, well inside the null's own half-width of {null_halfwidth:.3f}.</p>
<p>The prose-only judge is the informative half of the comparison: it scores
κ={j['prose']['kappa']:.3f}, clearly <em>worse</em> than either. So prose and tool calls are
not two channels of different quality — the shipped judge is stronger than either
alone because it sees more text, which is the same length effect that shows up in
every other cut of this corpus. The axis is quantity of window, not kind of evidence.</p>'''
        ),
    )

    rows = [
        (
            name,
            j[name]["rate"],
            j[name]["null"],
            tuple(j[name]["rate_ci"]),
            tuple(j[name]["null_ci"]),
        )
        for name in JUDGE_ORDER
    ]
    fig_rates = publish.rate_vs_null(rows, title="Used-rate against its permuted null, by judge")
    fig_kappa = publish.kappa_strip(
        [(name, j[name]["kappa"]) for name in JUDGE_ORDER],
        title="κ — the share of headroom each judge captures",
    )

    judge_table = publish.table(
        ["judge", "used", "null", "κ", "95% CI (used)", "flips under rotation", "what it sees"],
        [
            [
                name,
                f"{j[name]['rate'] * 100:.1f}%",
                f"{j[name]['null'] * 100:.1f}%",
                f"{j[name]['kappa']:.3f}",
                f"[{j[name]['rate_ci'][0] * 100:.1f}, {j[name]['rate_ci'][1] * 100:.1f}]",
                f"{j[name]['discordance'] * 100:.1f}%",
                JUDGES[name].description,
            ]
            for name in JUDGE_ORDER
        ],
        caption=f"{rotations} rotations, seed {seed}. The null re-judges each retrieval against "
        "another session's output window, drawn from the same window-length stratum.",
    )

    tool_table = publish.table(
        ["tool", "verdicts", "used"],
        [
            [tool, f"{d['total']:,}", f"{d['used'] / d['total'] * 100:.1f}%"]
            for tool, d in sorted(post["by_tool"].items(), key=lambda kv: -kv[1]["total"])
        ],
        caption="The shipped judge, split by the tool that did the retrieving.",
    )

    kind_table = publish.table(
        ["node kind", "verdicts", "used"],
        [
            [kind, f"{d['total']:,}", f"{d['used'] / d['total'] * 100:.1f}%"]
            for kind, d in sorted(post["by_kind"].items(), key=lambda kv: -kv[1]["total"])
        ],
    )

    contrast = ""
    if pre:
        pj = pre["judges"]["shipped"]
        contrast = publish.table(
            ["snapshot", "verdicts", "used", "null", "κ"],
            [
                [
                    f"<code>{CONTRAST}</code> (before)",
                    f"{pre['verdicts']:,}",
                    f"{pj['rate'] * 100:.1f}%",
                    f"{pj['null'] * 100:.1f}%",
                    f"{pj['kappa']:.3f}",
                ],
                [
                    f"<code>{SNAPSHOT}</code> (after)",
                    f"{post['verdicts']:,}",
                    f"{shipped['rate'] * 100:.1f}%",
                    f"{shipped['null'] * 100:.1f}%",
                    f"{shipped['kappa']:.3f}",
                ],
            ],
            caption="The same script, the same seed, two pinned graph states.",
        )

    sections = [
        publish.Section(
            title="Why a used-rate is not a result",
            anchor="why",
            body=f"""
<p>Thalamus records, for every retrieval, which memory nodes it put in front of the
agent — and then judges whether the agent used them, by matching the node's
distinctive terms against what the agent said and did next. That judgement is
cheap, runs after every session, and produces the number the project has been
quoting: <strong>{shipped['rate'] * 100:.1f}% of retrieved nodes used</strong>.</p>

<p>The problem is that a coding session and the memory it retrieves are about the
same subject. Term overlap is guaranteed before any retrieval happens. So the
question is not what the rate is, but how much of it survives when the retrieval is
deliberately mismatched to the work.</p>

<p>The control is a permutation. Re-judge every retrieval against a
<em>different session's</em> output window and see what the judge still calls used.
Whatever it scores there is the floor: vocabulary the sessions share by being the
same project. Two constraints make it a fair floor — the partner is always a
different session, and it is drawn from the same window-length stratum, because the
judge's used-rate moves with window length alone and an unstratified rotation would
measure that instead.</p>

{publish.callout("method", "The estimator", f'''
<p>κ = (p − p̄₀) / (1 − p̄₀): the share of the available headroom the judge captures.
p is the measured rate, p̄₀ the mean over {rotations} rotations. A judge that scores
{shipped['rate'] * 100:.0f}% where chance scores {shipped['null'] * 100:.0f}% is not
{shipped['rate'] * 100:.0f}% right — it is {shipped['kappa']:.1%} of the way from chance to
perfect.</p>''')}
""",
        ),
        publish.Section(
            title="What the judges score",
            anchor="results",
            body=f"""
<p>Seven judges, one corpus, one null each. They differ only in <em>what window they
look at</em>: the shipped judge reads everything the agent said and did after the
retrieval, unbounded; the variants narrow it to prose only, to tool-call inputs
only, or to the next N assistant turns.</p>
{fig_rates}
{fig_kappa}
{judge_table}
{split_callout}
""",
        ),
        publish.Section(
            title="Where the rate comes from",
            anchor="breakdown",
            body=f"""
<p>The shipped judge, split three ways. None of these splits is an effect until it
is read against a null of its own — they are here to show where the verdicts live,
not to rank the strata.</p>
{tool_table}
{kind_table}
<p>Window length is the confound the strata exist to hold: the median window in this
corpus is {post['window_chars']['median']:,.0f} characters and the longest is
{post['window_chars']['max']:,.0f}. Term membership is tested anywhere in that window,
so a longer session mechanically scores more used — the judge partly reports how long
the operator kept working.</p>
""",
        ),
        publish.Section(
            title="What this costs to fix",
            anchor="power",
            body=f"""
<p>The gap between the real rate and the null is
{(shipped['rate'] - shipped['null']) * 100:.1f} points. To bound that gap to ±1 point
you need enough paired verdicts to overcome how often a verdict flips under
rotation — measured here at <strong>{shipped['discordance'] * 100:.1f}%</strong> — inflated
by the clustering of verdicts inside sessions.</p>

<p>That is roughly <strong>{n_needed:,} verdicts</strong>, or about
<strong>{sessions_needed} sessions</strong> at this corpus's
{post['verdicts'] / max(1, post['sessions']):.0f} verdicts per session. The corpus today has
{post['verdicts']:,} verdicts across {post['sessions']} sessions.</p>

{publish.callout("finding", "More data will not rescue this instrument", '''
<p>An order of magnitude more sessions, at one operator's real working rate, is
years. The conclusion is not "collect more" — it is that a lexical judge cannot be
made precise enough at single-operator volume, and the next move is a better
instrument: human-labelled ground truth to calibrate against, and a randomized
withholding policy that makes the counterfactual internal to real work.</p>''')}
""",
        ),
        publish.Section(
            title="Threats to this result",
            anchor="threats",
            body=f"""
{publish.callout("caveat", f"Replay is {fidelity_rate * 100:.1f}% faithful, and fidelity is the wrong measure of the exposure", f'''
<p>Re-judging from the pinned snapshot reproduces {fid['matched']:,} of {fid['total']:,}
verdicts that <code>eval sync</code> stored live. The {fid['total'] - fid['matched']} that
differ are almost all <code>memory_open_threads</code>, and the stored evidence strings
show why: the same node scored "8/29 terms" then and "7/22" now. The node's text
changed.</p>
<p><strong>The exposure is larger than the mismatch count suggests.</strong> Fidelity
counts verdicts that <em>flipped</em>; text can change without flipping one. The right
denominator is every verdict on a mutable node kind — Thread and Session, which are
upserted latest-wins — and that is
{post['verdicts'] - co['verdicts']:,} of {post['verdicts']:,} verdicts
({(post['verdicts'] - co['verdicts']) / post['verdicts'] * 100:.1f}%), not the
{(fid['total'] - fid['matched']) / fid['total'] * 100:.1f}% that visibly disagree. The bias
is directional, too: a session that retrieves a thread and then rewrites that thread's
description moves the real window's terms toward the node, and does not move any
rotated partner's. That inflates the rate and not the null.</p>
<p>The claims-only cut above is the check that this did not produce the headline. The
fix is to record the judged term-set (or its hash) on the RETURNS edge at judgement
time, which makes a verdict a historical fact rather than a re-derivation.</p>''')}

{publish.callout("caveat", "The bounded judges have no headroom, and κ and the odds ratio disagree", f'''
<p>Pre-registered as a condition that would make a result uninterpretable, and it
fired: <code>bounded-1</code> and <code>bounded-3</code> score
{j['bounded-1']['rate'] * 100:.1f}% and {j['bounded-3']['rate'] * 100:.1f}% used, against
nulls near zero. A judge with almost no positives is being scored on almost no
headroom, so its κ is unstable — read those rows as "no signal available", not as
"no signal found".</p>
<p>The disagreement is the interesting part. On the odds-ratio scale the bounded
judges order cleanly — {j['bounded-1']['odds_ratio']:.1f}× at one turn,
{j['bounded-3']['odds_ratio']:.1f}× at three, {j['bounded-10']['odds_ratio']:.1f}× at ten,
{j['shipped']['odds_ratio']:.1f}× unbounded — the opposite ranking to κ, which divides by a
headroom that shrinks with the window. Neither column decides it. Measuring whether
utility decays with distance needs a within-session shifted-window design, not a
comparison of judges with different base rates.</p>''')}

<p>Other limits, stated rather than implied:</p>
<ul>
<li><strong>One operator, one machine, one harness configuration.</strong> This is an
observational result about a single deployment, not a benchmark.</li>
<li><strong>The frame is blind to non-retrieval.</strong> A node that was never
returned has no edge, so harm from failing to retrieve is structurally invisible
here.</li>
<li><strong>The null tests the judge, not the retrieval.</strong> Permutation can say
how much of a verdict is vocabulary; it cannot say whether the retrieval changed what
the agent did. That needs randomized withholding.</li>
<li><strong>Ranker configurations are mixed.</strong> Most of this corpus predates the
ranker ledger, so these rates straddle configuration changes.</li>
</ul>
""",
        ),
    ]

    if contrast:
        sections.insert(
            3,
            publish.Section(
                title="The purge comparison, withdrawn",
                anchor="purge",
                body=f"""
{publish.callout("withdrawal", "This was pre-registered as a control. It is not one.", f'''
<p>On 2026-07-30 the graph lost 307 Session vertices that were never sessions —
headless distillation subprocesses that had been firing the SessionEnd hook and
distilling themselves, 69% of all sessions. The pre-registration treats "did κ move
across the purge?" as a falsifier, on the reasoning that extraction self-talk is the
most topic-matched prose in the corpus and would inflate a topic detector.</p>
<p><strong>It could not have moved.</strong> Those sessions made no retrievals. Both
snapshots yield the same {post['cases']} retrievals across the same
{post['sessions']} sessions; they contributed no output window to the rate and were
never in the rotation pool. The only difference is {abs(pre['verdicts'] - post['verdicts'])}
verdicts ({abs(pre['verdicts'] - post['verdicts']) / pre['verdicts'] * 100:.2f}%) that
pointed at purged <em>nodes</em>. Reporting the non-move as a passed control would
imply a test that had a way to fail.</p>''')}
{contrast}
<p>What the comparison does establish, narrowly: the 37 verdicts that pointed at
sandbox nodes were not carrying the instrument. That is worth one sentence, not a
control.</p>
""",
            ),
        )

    sections.insert(
        3,
        publish.Section(
            title="The yardstick moves more than the judges do",
            anchor="null-design",
            body=f"""
<p>The null is a design, not a constant. This experiment rotates within a
window-length stratum; the earlier hand-run rotation behind lab/032 did not. On this
one corpus, with everything else held fixed:</p>
{publish.table(
    ["rotation design", "null", "κ", "95% CI on κ"],
    [
        ["stratified on window length", f"{nd['stratified']['null'] * 100:.1f}%",
         f"{nd['stratified']['kappa']:.3f}",
         f"[{nd['stratified']['kappa_ci'][0]:.3f}, {nd['stratified']['kappa_ci'][1]:.3f}]"],
        ["unstratified", f"{nd['unstratified']['null'] * 100:.1f}%",
         f"{nd['unstratified']['kappa']:.3f}",
         f"[{nd['unstratified']['kappa_ci'][0]:.3f}, {nd['unstratified']['kappa_ci'][1]:.3f}]"],
    ],
    caption="Same snapshot, same seed, same judge. Only the partner-selection rule differs.",
)}
{publish.callout("finding", "Read κ figures with their null's design attached", f'''
<p>The two designs differ by
{abs(nd['stratified']['kappa'] - nd['unstratified']['kappa']):.3f} in κ — larger than the
spread between the best and worst of the three judges that have any signal at all.
A κ quoted without saying how its null was drawn is not comparable to another κ.</p>
<p>It was put to this experiment that the difference from the project's earlier
hand-run figure (κ≈0.086) would be mostly this — the same instrument read against a
looser yardstick. The measurement says otherwise, and in the opposite direction:
dropping the stratum makes the null <em>easier</em> here ({nd['unstratified']['null'] * 100:.1f}%
against {nd['stratified']['null'] * 100:.1f}%) and κ correspondingly <em>higher</em>
({nd['unstratified']['kappa']:.3f}), which moves away from 0.086 rather than toward it. So
the null design is worth a lot, and it is not what explains the older number; the
remaining candidates are corpus construction (that figure was computed over
tap-reconstructed traces, this one over the graph's own Trace census) and a
three-rotation null with no interval. Neither is worth a rerun: both figures'
intervals are wide enough to contain each other.</p>''')}
""",
        ),
    )

    sections.insert(
        4,
        publish.Section(
            title="The auditable subset: claims only",
            anchor="claims",
            body=f"""
<p>Not every verdict can be re-derived. <code>Claim</code> vertices are
content-addressed on (kind, normalised description), so rewriting a claim mints a
<em>new</em> vertex and the text behind a stored verdict is still the text that was
judged. <code>Thread</code> and <code>Session</code> are upserted latest-wins: their
titles, descriptions and summaries are overwritten in place, and
<code>ingested_at</code> carries the writing session's timestamp rather than the
write time, so nothing in the graph records that the text moved.</p>

<p>That splits the corpus into an auditable part and an exposed one.
{co['verdicts']:,} of {post['verdicts']:,} verdicts ({co['verdicts'] / post['verdicts'] * 100:.1f}%)
are claims; the rest sit on text that may have changed underneath them.</p>

{publish.table(
    ["corpus", "verdicts", "used", "null", "κ", "95% CI on κ"],
    [
        ["all node kinds", f"{post['verdicts']:,}", f"{shipped['rate'] * 100:.1f}%",
         f"{shipped['null'] * 100:.1f}%", f"{shipped['kappa']:.3f}",
         f"[{shipped['kappa_ci'][0]:.3f}, {shipped['kappa_ci'][1]:.3f}]"],
        ["claims only (immutable text)", f"{co['verdicts']:,}", f"{co['rate'] * 100:.1f}%",
         f"{co['null'] * 100:.1f}%", f"{co['kappa']:.3f}",
         f"[{co['kappa_ci'][0]:.3f}, {co['kappa_ci'][1]:.3f}]"],
    ],
    caption="κ intervals are paired: each bootstrap draw resamples sessions and recomputes "
            "the rate and its null together, because κ is a contrast.",
)}

{publish.callout("finding", "The headline number survives on the auditable subset", f'''
<p>κ on claims alone is {co['kappa']:.3f} against {shipped['kappa']:.3f} on everything,
and the two intervals overlap heavily. The mutable-text exposure is real and worth
fixing, but it is not what produced the result — which is the thing that had to be
checked before any of this could be quoted.</p>''')}
""",
        ),
    )

    checklist = [
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[0], "yes",
            "Estimand: share of returned nodes the agent used. Estimator: κ against a "
            "stratified cross-session permutation null.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[1], "yes",
            "One operator, one machine, one harness configuration; observational.",
        ),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[2], "yes", f"{rotations} rotations per judge."),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[3], "yes",
            "Sessions are the resampling unit; verdicts within a session are not independent.",
        ),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[4], "yes", f"seed {seed}, {rotations} rotations."),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[5], "yes",
            f"snapshot {snapshot_row.name}, sha256 {snapshot_row.sha256[:16]}.",
        ),
        publish.ChecklistItem(publish.DEFAULT_CHECKLIST[6], "yes", "See Reproducibility."),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[7], "no",
            "No human-labelled gold set exists yet. The permutation bounds the judge "
            "against chance; it cannot bound it against truth. That set is the next instrument.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[8], "n/a",
            "Injection cost is measured, but this experiment reports discrimination "
            "rather than utility per token; cost belongs to the token-waste experiment.",
        ),
        publish.ChecklistItem(
            publish.DEFAULT_CHECKLIST[9], "yes",
            "The graph is not published; the reason is stated below rather than left blank.",
        ),
    ]

    return publish.Experiment(
        slug=SLUG,
        title="The used-rate is mostly a topic detector",
        standfirst=(
            f"Thalamus judges whether a retrieved memory was used by matching its terms against "
            f"what the agent did next. Re-judged against an unrelated session's output, that judge "
            f"still says {shipped['null'] * 100:.0f}% used — so of the "
            f"{shipped['rate'] * 100:.0f}% it reports, only κ={shipped['kappa']:.2f} of the available "
            f"headroom is retrieval utility. Six alternative judges were pre-registered against it; "
            + ("the best of them, " + best + ", improves on that." if j[best]["kappa"] > shipped["kappa"] + null_halfwidth
               else "none of them beats it.")
        ),
        registration=publish.Registration(
            question="How much of the used-vs-ignored rate is retrieval utility rather than "
            "shared project vocabulary, and does any judge variant separate them better?",
            hypothesis="The shipped lexical judge carries little discrimination above a "
            "cross-session permutation null; narrowing the window to tool-call inputs "
            "carries more, because acting on a retrieved path is a narrower coincidence "
            "than echoing a word.",
            endpoint="κ = (p − p̄₀)/(1 − p̄₀) per judge, node-weighted, over all attributed "
            "RETURNS edges in scope main.",
            falsifier="If κ for the tool-only judge does not exceed the shipped judge's by more "
            "than the null's own interval, the prose/tool split is not the axis that matters "
            "and the hypothesis is wrong.",
            stopping_rule=f"{rotations} rotations per judge, fixed before the run; the corpus is "
            "the whole census at the pinned snapshot, so there is no sampling decision to stop.",
            registered_at="2026-07-30",
            registered_ref="preregistration.md",
        ),
        provenance=publish.Provenance(
            snapshot=snapshot_row.name,
            snapshot_sha256=snapshot_row.sha256,
            snapshot_vertices=snapshot_row.vertices,
            snapshot_edges=snapshot_row.edges,
            seed=seed,
            git_ref=snapshot_row.git_ref,
            command=(
                "thalamus snapshot --list                     # verify the pinned state\n"
                "uv run --extra experiments python \\\n"
                f"    experiments/{SLUG}/run.py --rotations {rotations} --seed {seed}"
            ),
        ),
        stats=stats,
        sections=sections,
        checklist=checklist,
        verdict=(
            f"The shipped judge captures κ={shipped['kappa']:.3f} of the headroom above chance — "
            f"about {shipped['kappa'] * 100:.0f}% of the way from a coin-flip-on-vocabulary to a "
            f"perfect judge. "
            + (
                f"The pre-registered alternative, tool-call inputs only, does not beat it "
                f"({j['tool']['kappa']:.3f}, gap {tool_gap:+.3f} against a null half-width of "
                f"{null_halfwidth:.3f}): the hypothesis is falsified, and no reweighting of the "
                f"same lexical evidence rescues the instrument. "
                if not tool_wins
                else f"Restricting it to tool-call inputs raises that to {j['tool']['kappa']:.3f}. "
            )
            + f"Bounding the real-minus-null gap to ±1 point would need ~{sessions_needed} sessions "
            f"against {post['sessions']} today, so the answer is a different instrument, not a "
            f"bigger corpus."
        ),
        verdict_kind="measured" if tool_wins else "null",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotations", type=int, default=ROTATIONS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--scope", default=SCOPE)
    parser.add_argument("--snapshot", default=SNAPSHOT)
    parser.add_argument(
        "--skip-contrast", action="store_true", help="Skip the pre-purge comparison run"
    )
    args = parser.parse_args()

    row = snapshots.find(args.snapshot)
    print(f"[1/3] measuring against {row.name} ({row.vertices}V/{row.edges}E)")
    with snapshots.serve(args.snapshot) as url:
        post = measure(url, scope=args.scope, rotations=args.rotations, seed=args.seed)
    print(f"      {post['verdicts']:,} verdicts / {post['cases']} retrievals / "
          f"{post['sessions']} sessions")

    pre = None
    if not args.skip_contrast:
        print(f"[2/3] measuring against {CONTRAST}")
        with snapshots.serve(CONTRAST, port=8184) as url:
            pre = measure(url, scope=args.scope, rotations=args.rotations, seed=args.seed)
        print(f"      {pre['verdicts']:,} verdicts / {pre['sessions']} sessions")

    print("[3/3] rendering")
    experiment = page(post, pre, rotations=args.rotations, seed=args.seed, snapshot_row=row)
    results_path, page_path = publish.write(
        experiment,
        Path(__file__).resolve().parent,
        {"post": post, "pre": pre, "rotations": args.rotations, "seed": args.seed},
    )
    print(f"      {results_path.relative_to(REPO)}")
    print(f"      {page_path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
