# The Limit Lab

One-page entries, each in the same shape: **what broke → why (root cause in harness
terms) → workaround or wall.**

Starts at M2, when the eval loop can actually measure the effect of a break. Entries
that end in *"wall"* are as valuable as ones that end in *"workaround"* — a
documented, measured limit of the harness is precisely the artifact this lab exists
to produce. See [docs/07-harness-integration.md](../docs/07-harness-integration.md).

Also the home for negative results from the eval loop
([docs/04](../docs/04-eval-loop.md)): *"the literature expert's retrievals were
ignored 70% of the time until X"* is worth more than a clean win.

## Entries

| # | Entry | Ends in |
|---|---|---|
| [001](001-sessionend-hook-snapshot.md) | The session that installs a SessionEnd hook is never distilled by it | workaround |
| [002](002-truncated-source-attribution.md) | Attribution against a truncated Source snapshot silently under-counts | workaround |
| [003](003-the-process-is-the-pin.md) | The process boundary that blocked pinning is the pinning mechanism | workaround |
| [004](004-agent-teams-first-contact.md) | Agent Teams: pins inherit, coordination leaves no artifact, the lead armed the wrong repo | measurements |
| [005](005-transcript-ingress-canary.md) | A poisoned WebFetch result lands tier 2, not tier 1 — the laundering floor, canary-tested | workaround |
| [006](006-priced-verdicts-first-run.md) | First priced verdicts: half the injected retrieval tokens were ignored | measurements |
| [007](007-query-shape-refinement.md) | Query-shape autopsy: the hook was innocent, the dump was guilty | workaround |
| [008](008-gremlin-guard-baseline.md) | Gremlin guard baseline: the archive convicted the guard, not the queries | workaround |
| [009](009-memory-disagreement-adjudication.md) | Memory disagreement: the graph out-remembered the operator | adjudicated |
| [010](010-cursor-harness-port.md) | Cursor harness port: most of the suite crosses as adapters | workaround + two walls |
| [011](011-first-counterfactual-campaign.md) | First counterfactual campaign: memory-on lost, and both probe classes measured nothing | measurements |
| [012](012-post-distillation-rerun-found-a-harness-bug.md) | The re-run's headline numbers were voided by a session-start scoping bug | bug + fix |
| [013](013-the-fix-lands-but-recall-goes-unused.md) | The fix validated live; neither memory-on arm called recall anyway; a third bug found under questioning | fixes |
| [014](014-the-first-clean-campaign-and-a-split-verdict-on-recall.md) | The first campaign with zero infra faults — and a split verdict on recall | measurements |
| [015](015-three-models-and-the-recall-gradient.md) | Three models, twelve arms: a recall gradient, and a metric that was lying | measurements + fix |
| [016](016-the-replication-that-killed-the-hypothesis.md) | The replication that killed the hypothesis, and the guard that was too specific | falsification |
| [017](017-the-mutant-gate-and-the-suite-that-rewarded-imitation.md) | The mutant gate, and the test suite that rewarded imitation | gate passed 7/7 |
| [018](018-the-first-graded-campaign.md) | The first graded campaign: the ladder's interior is real, the cells are not interpretable | mixed verdicts |
| [019](019-the-task-that-withholds-something.md) | The task that withholds something, and the three facts that couldn't gate it | instrument |
| [020](020-the-first-gated-campaign.md) | The first gated campaign: an under-specified prompt induces recall and does not move the score | measurements |
| [021](021-the-escape-detector-and-three-corrections.md) | The escape detector, and three corrections from the eval-methodology scope | corrections |
| [022](022-confinement-and-the-leak-nobody-was-watching.md) | Confinement, and the leak nobody was watching | workaround |
| [023](023-the-first-valid-memory-contrast.md) | The first campaign where memory-on could actually reach memory: recall hit the ceiling, the outcome did not move | measurements (null) |
| [024](024-the-endpoint-was-in-the-wrong-place.md) | The endpoint was above the rung the treatment moved; and the battery is the wrong instrument for the thesis | measurements + design |
| [025](025-the-expert-you-do-not-spawn.md) | Self-answering a consultation cost 17 citations and the objection that killed the design; and the component already existed | measurements + corrections |
| [026](026-the-session-i-thought-i-was.md) | A session misidentified its own id, "caught" a fork risk that was another session's, and the trace tap caught that | incident + retraction |
