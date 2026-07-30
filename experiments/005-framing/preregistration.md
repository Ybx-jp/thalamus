# Pre-registration — experiment 005: conclusion or problem

Committed **2026-07-30**, before any `ceiling-problem` arm has run. No such record
exists in `~/.thalamus/counterfactuals/runs.jsonl` at the time of writing.

## Question

Does *how* a memory is framed — as the conclusion of a past design discussion, or as
the situation and evidence that produced it — change what the candidate builds, holding
the information constant?

## Why this question

experiments/004 handed a candidate the perfect memory for its task and measured it
losing every pair. The follow-up at double the turn budget ruled out censoring: the arm
finished in 36 of 80 turns, wrote the memo's design into its diff in its own words, and
still failed **L2 and L3** — the foundation rungs every memory-off arm passed.

The reading that survives is that a conclusion, handed to an agent that has not walked
the path to it, can substitute for the earlier steps rather than add to them. If that is
right, the damage should be a property of the *framing*, not of the content, and stating
the same facts as a problem should not cost the same rungs.

## Design

Two arms, both `ceiling`-shaped — no MCP, memory hooks stripped, the same injection
mechanism — differing in one field:

- **`ceiling`** — `under_specification.fact`: the conclusion. *"The runner must not
  guess… the surviving design is two conservative shapes, both ungraded."*
- **`ceiling-problem`** — `under_specification.problem_framing`: the same evidence with
  the prescription withheld. The 33-of-40 trustworthy arm, the 11 and 18 cut-offs, and
  the turn-count attempt are all preserved; the imperative and the answer are not.

The problem framing is an **authored stimulus**, written 2026-07-30 and disclosed as
such. It is not a distillation of any real session, and a test asserts that it keeps
every load-bearing fact and none of the prescription — otherwise this experiment would
vary content and framing together and could attribute neither.

5 pairs, 10 arms, alternating which framing leads, `--sandbox --isolate-store`, 40-turn
cap (the campaign default, so the comparison with experiments/004 holds).

## Primary endpoint

**Share of arms passing L2**, the rung reachable from the prompt alone and the one the
conclusion framing cost in 4 of 4 recorded arms.

This is a different endpoint from experiments/004's, and the reason is stated rather
than discovered: 004 pre-registered rung ≥ 4 and *neither arm ever reached it*, so it
cannot discriminate anything here. L2 is chosen because 004 measured it as where the
effect lives — which makes this a confirmatory test of a finding from exploratory data,
not a second look at the same data.

## Secondary endpoints

Reported whatever they show, never promoted:

1. Full rung distribution and the per-rung pass pattern.
2. Memo-echo ratio per arm — whether the candidate acted on the memo at all, which is
   what separates "framing changed the use" from "framing changed whether it was used".
3. Turns, diff lines, and the turn-cap rate.

## Reference cohort, and its limit

experiments/004's six `memory-off` arms ran the same day, same task, same model, same
sandbox, and are reported beside these as context. They were **not** randomized
concurrently with these arms and are not a control for this comparison; the randomized
contrast here is conclusion against problem.

## Analysis

Exact test on the paired L2 outcome, with a confidence sequence (α = 0.05, ρ = 0.05)
reported beside it. At 5 pairs neither will be decisive on its own and both are shown,
which is the rule experiments/004 followed after lab/023.

## Stopping rule

The confidence sequence excludes the null, or 10 arms.

## Falsifiers

- **Framing is not the variable** if `ceiling-problem` loses L2 at the same rate as
  `ceiling`. The damage would then be a property of injecting *any* memory into this
  task, and the "conclusion replaced the path" reading dies.
- **The experiment is void** if any arm is stamped contaminated, or if
  `ceiling-problem` arms fail to echo the memo at all — an unused memo tests nothing
  about framing.

## Declared in advance as uninterpretable

- One task, one model, one operator, and one author for the problem framing. A single
  authored stimulus cannot separate "problem framings are safer" from "this particular
  paragraph is safer".
- 5 pairs cannot detect a small difference. A null here is "not detectable at this n",
  not "no effect".

## Data

`~/.thalamus/counterfactuals/runs.jsonl`, arms `ceiling` and `ceiling-problem`, `ts` at
or after the campaign start. Analysis seed `20260730`.
