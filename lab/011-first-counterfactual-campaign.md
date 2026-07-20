# 011 — First counterfactual campaign: memory-on lost, and both probe classes measured nothing

**Date:** 2026-07-19 · **Component:** eval loop layer 2 (`thalamus eval run`, `config/tasks/`) · **Status:** campaign complete, 4/4 runs recorded; verdicts scoped below

## The setup

Both seed tasks (memorization stratum, replayed from this same day's session),
memory-on vs memory-off, balanced order (task 1 on→off, task 2 off→on),
`--full-auto`, sonnet, 40-turn cap. Runs in
`~/.thalamus/counterfactuals/runs.jsonl`; sessions
`a3e54368`/`35f77310` (reader task), `c710bdf8`/`122d0ea8` (consultation task).

**Disclosed up front:** the campaign ran *before the authoring session
distilled* — the graph did not yet hold the solution memos the memorization tag
anticipates. Memory-on arms carried general project memory only (both invoked
the session-start pattern: `memory_open_threads` + `memory_recall_by_project`;
memory-off made zero thalamus calls). So this campaign measured the ambient
memory surface, not solution recall. n=2 paired tasks, one model, one operator.

## What the runs said

| task · arm | accepted | cost | wall | turns |
|---|---|---|---|---|
| reader · memory-on | **NO** (left `tests/test_reader.py` in a collection error) | $1.67 | 317s | cap |
| reader · memory-off | yes | $1.00 | 180s | cap |
| consultation · memory-off | yes | $1.32 | 240s | cap |
| consultation · memory-on | yes | $1.64 | 321s | cap |

- **Acceptance:** memory-off 2/2, memory-on 1/2. The one failure is nuanced:
  the *behavioral* oracle passed (the recall fix worked) while the suite was
  left broken mid-edit — the session hit the turn cap before cleaning up.
- **Cost and wall time:** memory-on cost more (+52% avg) and ran slower on
  *both* tasks, direction consistent across the pair. With injected
  session-start recall and no solution memo to find, the surface was overhead.
- **The cap bound in 4/4 runs.** Every session was truncated, none concluded
  naturally — iterations-to-done is censored at the cap, and the memory-on
  failure is plausibly truncation interacting with recall's early-turn spend.

## The probe finding (the sharper negative)

**Every probe hit in every arm, including memory-off.** Both memory-off agents
independently used `re.escape` (the diff probe) and preserved the
empty-scope refusal (the other diff probe); the transcript probes matched
gremlin/diagnostic text any competent attempt produces. As authored, the
probes measured *base-model competence*, not memory consequence — the MQuAKE
analogy only holds if the probed implication is something the model could not
derive without the memory. The smoke run had already caught prompt-echo
pre-satisfaction (now a mechanical battery refusal); this campaign adds the
harder authoring rule that no validator can check: **a probe must target
knowledge unreachable from the prompt plus general competence** — session
UUIDs, lab-entry numbers, dial values, named thread slugs.

## Honest verdict, scoped

Within this campaign (memorization stratum, pre-distillation memory, n=2,
sonnet, cap-censored): the memory surface produced no outcome advantage, cost
+52%, and was present in the only failed run. This is not "memory doesn't
work" — it is the ambient-surface baseline the design predicted layer 1
waste-share numbers would show up in outcomes, and it is exactly the negative
result the discipline says to publish. No cross-arm claim beyond this
paragraph exists.

## What this buys the design

1. **Re-run after distillation** — the same campaign once this session's memos
   land grades the memorization stratum as designed; today's numbers are its
   pre-registered baseline.
2. **Record cap-hits explicitly** — the runner should stamp `turn_capped` on
   the record instead of leaving it inferable from `num_turns`.
3. **Probe authoring rule** (docs/04): target memory-only knowledge; the
   battery validator can catch prompt echo, only authorship can catch
   competence echo.
4. **Cost asymmetry is measurable at n=2** — the +52% is the layer-1b
   injection-cost story reaching outcomes; the conditioning tier (docs/07)
   exists precisely to make that spend conditional.
