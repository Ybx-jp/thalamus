# The Limit Lab

One-page entries, each in the same shape: **what broke → why (root cause in harness
terms) → workaround or wall.** This is the notebook, written for us.

Work published for readers outside the project lives in [`experiments/`](../experiments/):
pre-registered, regenerated end to end from a pinned graph snapshot and a seed, with
every rate reported beside its null. When a lab figure and an experiment disagree, the
experiment wins — it is the one that can be re-run. [lab/034](034-the-corrections-the-instrument-forced.md)
holds the standing withdrawal list.

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
| [027](027-the-wall-that-moved.md) | Cursor re-verified: the contract held, the injection wall moved, the installer was the real gap | workaround + one wall |
| [028](028-the-transcript-that-keeps-no-receipts.md) | Cursor distills, and the trust floor had to be told the difference between "nothing fetched" and "cannot know" | workaround |
| [029](029-the-bleed-that-was-not-a-leak.md) | Lexical recall is project-blind; off-project carries 83% of the waste and 38% of the value; both consultations were wrong about the mechanism | measurements + corrections |
| [030](030-the-miss-rate-was-the-consultation.md) | The 41% miss rate is consultation into thin expert subgraphs; the floor never cut fan-out (query shape did); three instrument errors caught | correction + measurements |
| [031](031-the-dial-that-had-nothing-to-tune.md) | Detail cap stays at 8: used-rate is ~60% flat across position, length and ranking; the elision stub was hiding the cap | null result + fix |
| [032](032-the-instrument-is-a-topic-detector.md) | Attribution scores 59% used against an unrelated session's output vs 63% against the real one — 4pp of signal on a 59pp floor | calibration |
| [033](033-the-graph-was-mostly-remembering-itself.md) | Distillation's own headless subprocess fired the SessionEnd hook, so 69% of Session vertices were memory about the act of remembering | fix |
| [034](034-the-corrections-the-instrument-forced.md) | Calibrating the used-rate against a null withdrew more numbers than it produced — and the published experiments moved to `experiments/` | corrections |
| [035](035-the-battery-that-could-not-be-run.md) | A history rewrite killed all six task refs; validation kept saying "Battery OK" because it never checked that the oracle could be reached | fix |
| [036](036-the-ceiling-that-lost.md) | A candidate handed the perfect memory lost every pair, and neither arm ever reached the endpoint it was measured on | null + cancelled programme |
| [037](037-the-verdicts-that-could-not-be-replayed.md) | A stored verdict that is a function of state the record does not carry is a re-derivation wearing a record's clothes | audit: 4 fixed, 4 open |
| [038](038-the-corpus-that-moved-under-its-own-numbers.md) | The run log was rewritten in place and neither backup predates the rescore; 88 judgements exist nowhere | fix + one unrun falsifier |
| [039](039-the-benchmark-that-could-not-tell-defense-from-refusal.md) | MPBench declined: dataset-only artifact, 2/6 classes reach us, and its ASR null is confounded with the model's refusal | declined + taxonomy adopted |
| [040](040-the-floor-that-skipped-the-entrypoint.md) | The ingress floor covers `Claim` subtypes and skips `Thread` — the node served first to every session; the one-line fix silently no-ops | gap + schema change |
| [041](041-three-proposals-and-the-audit-nobody-ran.md) | Three schema proposals: similarity merging falsified (14 of 307,720 pairs ≥0.4, and it would preferentially merge contradictions), `Claim→Thread` blocked on 50 unlabelled audit items, belief revision deferred (+2.31pp against a 13.4pp MDE) | build nothing + 1 fix |
| [042](042-the-brief-nobody-cites.md) | The used-vs-ignored replay is underpowered at this corpus size (effective n≈36, ±16pp on the deciding rate); and across 55 exchanges an expert has never cited a Claim its own brief handed it directly | no signal available + finding |
| [043](043-two-forks-and-i-measured-the-wrong-one.md) | No fork, no warm context and no corroboration hazard in-process — the wall withdrawn, the fork ships, and `forked_from` is the dependence the graph can know exactly | withdrawal + schema change |
| [044](044-the-103-byte-cliff.md) | `XDG_RUNTIME_DIR` is honoured for binding, but over 103 bytes the socket silently falls back to a shared `/tmp` dir — an invalid A/B had concluded the override disables binding | refutation + measurement |
| [045](045-the-registry-that-was-not-the-socket.md) | The room boundary is the config dir, not the socket: discovery reads `$CLAUDE_CONFIG_DIR/sessions/*.json`, so three isolated socket registries all listed each other while a per-room config dir partitions cleanly — and the send path refuses even a member's exact ref leaked out-of-band | refutation + shipping shape |
| [046](046-the-third-channel-is-the-transcript.md) | `--resume` consults neither roster and reads transcripts, so the `projects/` symlink that saved the room's distillation let a non-member fork a member's session and read its context; the room dir must own `projects/` on persistent disk | withdrawal + shape that closes both directions |
