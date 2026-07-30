# Pre-registration — experiment 004: the ceiling

Committed **2026-07-30**, before the first ceiling arm has been run. No `ceiling`
record exists in `~/.thalamus/counterfactuals/runs.jsonl` at the time of writing.

## Question

If a candidate is handed exactly the right memory, with no retrieval to get wrong,
does it beat a candidate with no memory at all?

This gates the rest of layer 2. Every memory-on/off campaign so far has asked whether
*retrieval* helps, and none has established that the battery can register the help of
memory at all. If a perfect memory does not separate from no memory, then no ranking
change, no dial and no better instrument can move this battery, and the sensible
response is to stop running arms rather than to run more.

## Arms

Both sandboxed (`--sandbox --isolate-store`), one commit of history in the worktree,
`--full-auto`, on `arm-runner-session-death-classification` — the battery's one
strongly-gated task, whose `under_specification.fact` is the memory being handed over.

- **`ceiling`** — memory-off's stripped harness (no MCP, memory hooks removed) plus
  the withheld fact injected into the prompt, framed as recall rather than as
  instruction.
- **`memory-off`** — the same harness, nothing injected.

`memory-on` is deliberately **not** in this campaign. The question is about the
battery's sensitivity, and adding the arm whose treatment is under dispute would
invite reading a three-way comparison that this n cannot support.

## Primary endpoint

**Share of arms reaching rung ≥ 4** on the graded oracle. Rung 4 is the task's own
pre-registered memory-attributable outcome (`gates_rungs: [4]`), fixed in the task
YAML before any campaign, and this experiment does not move it.

lab/023 is the reason for saying so explicitly: its pre-registered rung ≥ 4 endpoint
read null while rung ≥ 3 separated cleanly, and the correct response was to report
the pre-registered endpoint as primary and the lower rung as exploratory. The same
rule binds here in advance.

## Secondary endpoints

Exploratory, reported whatever they show, never promoted:

1. Share reaching rung ≥ 3.
2. The rank statistic over rungs (Mann-Whitney-style P(ceiling > off)). **Not**
   mean-of-rungs: ordinal-as-interval sign-reverses on this project's own data
   (lab/020), and every power number derived from it is withdrawn (lab/034).
3. Cost and turns per arm, so the ceiling's price is on the record beside its effect.

## Analysis

Exact one-sided test on the pre-registered endpoint, monitored with a confidence
sequence (`eval/sequential.py`, α = 0.05, ρ = 0.05) so the campaign may be inspected
while it runs without spending its own error rate.

## Stopping rule

Whichever comes first:

1. the confidence sequence on the rank statistic excludes 0.5;
2. the sequence lies entirely within ±0.05 of 0.5 (futility);
3. **12 arms**, 6 per side, alternating so arm order cannot confound the comparison.

12 is a budget decision, stated as one: at roughly $2 an arm on the last campaign
that is about $25. It is enough to detect a large effect and explicitly not enough to
detect a small one — and "the ceiling's effect on this battery is small" is itself the
finding that would stop layer 2.

## Falsifiers

- **The battery is the binding constraint** if ceiling does not separate from
  memory-off at the stopping rule. E1's container sibling and the consequence-probe
  work are then cancelled rather than queued.
- **The campaign is void** if any arm is stamped contaminated by the leak detectors,
  dies of a session fault, or if confinement fails — the arms run in an image where
  the operator's checkout does not exist, and that has never been verified by a live
  campaign, only by direct probe (`scope:eval-methodology:thread:arm-confinement-unverified-live`).

## Declared in advance as uninterpretable

- A ceiling arm that ignores the injected fact entirely. It would be scored on the
  same rungs as any other arm, but the write-up must say how many arms visibly used
  the memo, because "perfect memory, ignored" and "perfect memory, useless" are
  different findings and the rung alone cannot separate them.
- One task. Whatever this measures is about *this* task's gate, and the battery has
  one strongly-gated task. Generalising to "memory does not help" would be
  unsupported by construction.

## Data

`~/.thalamus/counterfactuals/runs.jsonl`, filtered to this task and to arms
`ceiling` and `memory-off` with `ts` at or after the campaign start. Analysis seed
`20260730`.
