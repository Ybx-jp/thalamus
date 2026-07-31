# Pre-registration — experiment 006: structure, not dose

Committed **2026-07-30**. No `ceiling-node` arm exists in
`~/.thalamus/counterfactuals/runs.jsonl` at the time of writing, and the arm itself is
unbuilt (see *Prerequisites*).

## What this replaces, and why

The obvious next experiment after 004/005 was **dose**: injected arms reach L≥3 in 1 of
17 while memory-off reaches it in 5 of 6, so the natural question is whether a *smaller*
memo costs the same rungs. A design check before pre-registration
(exchange `scope:main:exchange:34166c3f423141aa`) killed that design on arithmetic, and
this document is what survived it.

**Dose down is a content ablation wearing a dose label.** The injected block is 423
chars of stimulus plus a 67-char `ceiling_prompt` wrapper. Compressing it to one
sentence forces a choice among three separable components, so "which facts survived"
moves with "how much text" and neither can be attributed. experiments/005 already ran
one such choice — `problem_framing`, 370 chars, prescription dropped — at exact
p = 1.000. And 005's own pre-registration requires a test asserting the stimulus keeps
every load-bearing fact, a standard `ceiling-brief` cannot pass. If the dose axis is
ever run it must run **upward** (`ceiling-padded`: identical fact set embedded in more
words), where content is held constant by construction.

**Three arms at n=5 cannot produce their own primary answer.** The exact paired sign
test at 5 pairs needs all five pairs discordant and favourable to reach p ≤ 0.05
(0.5⁵ = 0.031; 4-of-4 gives 0.0625), so the smallest attainable p across three
contrasts is 0.094. Against the pooled injected base rate of 1/17, maximum achievable
power at n=5 is **0.696 even for a treatment that passes L2 every time**. Two arms at
8 pairs — the same 16 arms, ~$37 — reach 0.81 power at p_t = 0.70.

**The axis prior work actually found live is structure, not length.**
`scope:eval-methodology:claim:623b8c4eaa444be8` records structured vs plain-English
context at +36.7–40.0pp (Fisher p ≤ 0.0022, N=30 per cell), from a paper titled
*Structure Beats Verbosity*. The proposed design would have spent its budget on the
inert axis and carried the live one as an afterthought.

## Question

Does a memory delivered as **the retrieval surface actually renders it** — a structured,
cited node — cost the same rungs as the same knowledge delivered as an authored prose
conclusion?

## Stage 0 — the free observational pass, run first

Before any arm is spawned, over the 17 already-recorded injected arms:

1. **Rescore all 17.** `rescored_at` is null on every one, and four `memo_echoed`
   verdicts (10:30, 10:51, 11:00, 11:46 UTC) carry `evidence: "cited by vertex ID"` —
   impossible under the current `__injected_memo__` key, which is named precisely so it
   cannot occur in prose. They are output of the superseded `"memo"` key. The **ratios
   are unaffected** and lab/036's reading rests on ratios, so its conclusion stands;
   what is stale is the evidence string. Recorded here because a corpus carrying
   verdicts from two instruments with nothing saying which is exactly lab/037's class,
   caught in the wild.
2. **Exposure = `memo_echoed.matched`, absolute, never `ratio`.** Denominators already
   differ across arms (37 terms vs 32) and would differ more across stimuli, so a ratio
   silently compares different things.
3. **State the ceiling on what stage 0 can show.** With one L2 event in 15 echo-scored
   arms, the best attainable one-sided permutation p is 1/15 = 0.067 — it cannot reach
   significance whatever the data says. Realised p = 4/15 = 0.267.

Stage 0 is therefore run as a **bound, not a test**: echo spans 0.189–0.784 (4.1×) with
the stimulus held exactly constant, and L2 pass over that entire range is 0 of 12. If
how much of the memo a candidate reproduces drove the outcome, that range should have
produced variation. It did not.

## Design

Two arms, paired, alternating lead, `--sandbox --isolate-store`, 40-turn cap:

- **`ceiling`** — existing. The authored prose conclusion, 423 chars.
- **`ceiling-node`** — the task's `fact_nodes` rendered through the real recall
  formatter: vertex IDs, tiers, and citations as `memory_recall` emits them.

**8 pairs, 16 arms.** Not 5, for the reason above.

## Primary endpoint

**Share of arms passing L≥3**, exact paired test, confidence sequence (α = 0.05,
ρ = 0.05) reported beside it. L≥4 is not the primary: it read null in both 004 and 005,
and lab/024 established that an endpoint above where the effect acts measures nothing.

## Secondary

Full rung distribution; `memo_echoed.matched`; turns, diff lines, turn-cap rate.

## Declared in advance as uninterpretable

- **`ceiling-node` is not a pure dose contrast and is not claimed as one.** The task
  records four `fact_nodes`, so one rendered node is a quarter of the fact set; all four
  rendered is the full set in a different form. Whichever is used, this varies *form*
  and *structure* together, which is the axis the cited work measured — not length.
- The vertex-ID path in attribution will legitimately fire for `ceiling-node` and cannot
  for `ceiling`. Echo is therefore **not comparable across these two arms** and is
  reported per-arm only.
- One task, one model, one operator.
- A null at 8 pairs is "not detectable at this n", not "no effect". Given the base rate,
  **a null is the more likely outcome and is pre-registered as such.**

## Falsifiers

- **Form is not the variable** if `ceiling-node` passes L≥3 at the same rate as
  `ceiling`. The "structure beats verbosity" transfer to this setting then dies, and
  what remains is that injecting *any* correct answer costs rungs regardless of form.
- **Void** if any arm is stamped contaminated, or if `ceiling-node` arms show no echo at
  all — an unread stimulus tests nothing. Note the cited paper's own caveat
  (`scope:eval-methodology:claim:4a0d4b5dcb5f677e`): its comparison held only after a
  leakage audit, and this repo has a measured leak channel at 9 of 88 arms.

## Prerequisites, unbuilt

`ceiling-node` does not exist in `parse_arm`. It needs the recall formatter applied to
`under_specification.fact_nodes` at injection time, and a test asserting the rendered
block carries the same fact set as `fact` — the standard 005 set and `ceiling-brief`
could not meet. `thalamus eval run` refuses an unbuilt arm rather than approximating
it, so this pre-registration cannot be run by accident before that lands.

## Data

`~/.thalamus/counterfactuals/runs.jsonl`, arms `ceiling` and `ceiling-node`, `ts` at or
after the campaign start. Analysis seed `20260731`.
