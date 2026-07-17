# Eval Loop — Measuring Memory Utility

**Status:** layer 1 (traces + attribution) and layer 1b (cost accounting) built —
see `src/thalamus/eval/`; layers 2–3 remain design. This is the differentiating component: the project's central
claim is not "I built agent memory" but "I built agent memory **and the evaluation
loop that proves what it's worth**."

## The question

Does this memory system actually make the agent better — and how would you know?

Retrieval precision/recall is a garbage proxy: it grades whether retrieval matched a
query, not whether it changed anything. The metric that matters is **downstream
utility**: did the retrieved memory alter the agent's behavior, and for the better?
Memory quality is a hard-to-measure quality, so we build the missing metric — same
discipline as the taste critic, pointed at memory instead of music.

This is now the field's consensus, not a lone position: the memory survey (arXiv
2603.07670) names the same shift, and a wave of benchmarks — Mem2ActBench (arXiv
2601.19935), MemoryArena (arXiv 2602.16313), AMA-Bench, Momento — measure memory by
downstream, action-coupled outcomes ([11-related-work.md](11-related-work.md) §2).
Those are all **offline benchmarks**: fixed dataset, external grader, run once.
Thalamus's differentiator is the part none of them is — a **live, in-deployment,
self-maintaining loop** over the operator's own sessions. We cite the benchmarks as
the offline half we extend, not a void we fill.

## Layer 1 — Retrieval traces (M2)

Every graph query the agent makes is instrumented via harness hooks
([07-harness-integration.md](07-harness-integration.md)). Per retrieval event:

- session, pinned expert, consulted expert (if an exchange), query, returned nodes;
- **used vs. ignored** — was the retrieved content reflected in what the agent
  actually did (cited in the answer, visible in the diff, referenced in a
  subsequent tool call), or was it dead weight in context?

Used-vs-ignored attribution starts crude (lexical/structural matching between
retrieved content and the session's outputs, judged post-hoc) and that is fine —
a crude measure beats no measure, and refining attribution is itself lab-notebook
material. Traces land as episodic memory (the trace store **is** a property graph),
so the eval loop needs no side database: it reads the same substrate it grades.

**As built:** retrieval results render their vertex IDs inline, so the verbatim
PostToolUse tap *is* the node-level trace — no side schema (docs/09). `thalamus
eval sync` lands tap lines as `Trace` nodes (`Session -[QUERIES]-> Trace -[RETURNS]->
result`), attributing each returned node against the session's retained transcript:
cited-by-ID and thread-slug mentions are strong signals, then lexical term overlap
(≥2 terms and ≥30% — arbitrary dials, here to be pressure-tested). Verdicts live on
the RETURNS edge as `used`/`evidence`. `thalamus eval report` renders per-scope
totals, per-tool counts, miss rate, and the most retrieved-but-ignored nodes — the
layer-3 decay candidates. A trace can only land after its session distills (the
QUERIES edge and the transcript both need it); until then it stays in the tap,
reported as pending. Attribution findings: lab/002.

## Layer 1b — Cost, the denominator

Utility alone is half a fraction. The field grades memory on **performance–cost
frontiers** (BudgetMem, arXiv 2602.06025 — token usage aggregated per query,
converted to cost), and token cost is a session-level metric in the AgentOps
observability taxonomy (arXiv 2411.05285). `thalamus eval cost` is the live-loop
instantiation of both — a *convergence* on prior work, not an extension (see
[11-related-work.md](11-related-work.md) §2b): no new telemetry, every number read
from records the system already keeps.

- **Harness transcripts** (per-API-call usage) bucketed by an operation ontology:
  `interactive`, `extract` (headless distillation/ingest), `expert:<scope>` (via
  the pin ledger — the pin is also the cost attribution), `other` (the
  denominator). The ontology-with-weights pattern is borrowed from the operation
  registry in the operator's own workflow-eval project (nodeglass); its DAG
  topology scorers are **not** adopted — they grade structural action risk, and
  retrieval traces are shallow star graphs where topology says nothing.
- **The trace tap** gives each retrieval's injection cost — the rendered response
  *is* the cost, and it recurs in every later call of the session.
- The weighted-token proxy (cache reads ~0.1x, cache writes ~1.25x, output ~5x)
  is a dial, not a truth — same discipline as the attribution thresholds above.

Standing finding: session length, not retrieval or consultation, dominates token
burn — thalamus's steady-state marginal cost is one extract run per session end.

**The cost-utility join:** Trace nodes carry `injected_chars` at sync (the
rendered response is the injection cost), and `eval report` prices every layer-1
verdict at an even per-node share — so the layer-3 decay ranking orders by
**wasted tokens**, not ignore-counts. The waste ranking surfaces cross-project
bleed that count ranking buries (measured: lab/006–007). This is the first
implemented piece of the per-expert routing signal: scope-level cost-utility is
one report away from grading pin quality.

## Layer 2 — Counterfactuals (M4)

Traces show usage; they can't show *value*. For that, run matched tasks under:

- **memory-on** — full Thalamus;
- **memory-off** — no memory surface at all;
- **memory-degraded** — scope shuffled (wrong expert pinned), stale snapshot, or
  top-k truncated.

Score task outcomes (task success, iterations to done, operator interventions —
exact battery TBD at M4) across arms. This is the difference between "I built
memory" and "I measured what memory is worth." The degraded arm exists because it
isolates *which property* of the memory carries the value — scoping, freshness, or
volume. Task corpus: real sessions replayed where possible; a small fixed battery
of representative coding tasks where replay is impractical. Small and honest beats
large and confounded.

## Layer 3 — Memory that measures itself (M4+)

Close the loop: utility signals feed back into graph maintenance.

- Nodes that are repeatedly **retrieved-but-ignored** decay toward archive.
- Nodes whose use correlates with good outcomes gain retrieval weight.
- Stale literature (superseded versions, dead links) gets flagged for re-ingestion
  or demotion.
- Decay is **archival, never deletion** — utility-driven forgetting must be
  reversible and auditable via the master plane.

This generalizes the refresh-skill maintenance scheme into a principled,
**utility-driven forgetting policy**: a memory system with a learned forgetting
policy grounded in downstream agent outcomes.

## Per-expert utility: grading the roster

Aggregating layer-1/2 signals per expert answers questions no memory demo can:

- Is this expert earning its keep, or is it a graph that likes being built?
- Was pinning this expert to that session right? (Sustained low-utility retrieval
  under a pin grades **pin quality** — the feedback that replaces a learned router;
  see [02-expert-subgraphs.md](02-expert-subgraphs.md).)
- Do consultations to expert X produce used answers? (Grades the exchange graph.)
- Null-hypothesis test for roster growth: if a candidate domain's retrievals don't
  cluster and out-perform "leave it in an existing expert," it isn't an expert.

Verdicts surface on the master plane next to the graphs they grade
([03-master-plane.md](03-master-plane.md)).

## Discipline

- **No unmeasured claims.** Until layer 2 runs, the honest sentence is "instrumented,
  measuring" — never "it makes the agent better."
- Publish negative results in the lab notebook. "The literature expert's retrievals
  were ignored 70% of the time until X" is more valuable — to the design and to the
  portfolio — than a clean win.

## Open questions

- Outcome-metric battery for counterfactual arms — needs to be cheap enough to run
  routinely, or it won't be run.
- Attribution refinement: when does lexical matching mislead, and is an LLM-judge
  pass worth its cost/noise?
- Sample efficiency: a single operator generates limited sessions. Lean on paired
  designs (same task, arms swapped) over volume.
