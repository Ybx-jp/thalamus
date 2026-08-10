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
| [047](047-the-room-that-was-only-a-variable.md) | The room shipped as a launcher: provisioning it surfaced two silent failures the boundary work missed — `new-session -e` leaks a room into every later window of that session, and `CLAUDE_CONFIG_DIR=$HOME/.claude` costs a session its MCP servers, so a roomless launch must *unset* rather than name the default | build + 2 measurements |
| [048](048-the-treatment-that-was-only-a-label.md) | Rooms were measured for containment and never for efficacy: 1 of 194 sessions carries a room and 5 guard rows exist, the grounding came back empty on 3 of 4 areas, and few-treated-clusters rules out the obvious inference plan — so the manipulation check ships first and finds `alpha` one-way and `symtest` a room of one | design + instrument + 3 bugs |
| [049](049-the-fork-is-the-whole-conversation.md) | A fork is a full rewrite of the parent's conversation with a new session id on every record, so distilling one mints a second Session re-asserting the parent's whole episode — delta-only distillation is exact (562/562 UUID overlap); the pin ledger names a dead session for 3 of 5 scopes; and a first "$1.35/call, money is the wall" finding is withdrawn — warm forks read the parent's whole prefix at 100%, so cost is bimodal on parent *recency* ($0.03 warm / $0.60 cold / 13× mid-turn) | measurements + 5 silent failures + withdrawal |
| [050](050-the-first-live-quick-call.md) | `thalamus quick` answered on its first live call and broke in **eight** places the 27 green unit tests could not reach: the pin ledger's `event` rows overwrote the fork's obligations under last-row-wins (in the launcher *and* in session-end's delta decision), the `<`-prefixed frame break cost the fork every user turn so its delta distilled nothing, the fork closed its own ticket ahead of the gate, `close_connection()` took no argument on the success path, a live-but-never-spoken-to expert is **unforkable** (3 of 4 on this roster), the mid-turn refusal deleted the feature the tier exists for (non-interruption; `--wait` is offered, never imposed), a synchronous `uv run` in SessionEnd is cancelled, and an unanswered quick exchange is a genuine orphan — plus the cost: **$0.975 at 82% cache hit**, so forking is cheap and answering is not | build + 8 defects + cost correction |
| [051](051-the-representation-we-never-measured.md) | The archive is retained but no retrieval path reaches it, and *Fidelity Before Structure* (2601.00821) measures verbatim chunks beating extracted artifacts by 15.9/22.0 pts — surviving under **BM25**, which kills the "we're lexical so it doesn't apply" escape. Reading our own code found the two halves at different poles (`LiteratureClaim` carries a verbatim `citation`, the episodic claims carry nothing) and the 2026-07-14 decision's promised alternative — message-UUID anchors on the edge — **never built**. Eval-methodology refused a downstream campaign as unpowered at our scale (24 arms could not resolve memory on-vs-off) and specified an offline arm-free A/B/C placement assay instead, as an *equivalence* question with a pre-registered margin. **First result:** the citation adds 52% more text and 0.8pp of literal coverage — placement 0.9% against a pre-registered 31% bar, 0/46 sources clearing it — so condition (d) is falsified and `citation` is a provenance mechanism, not a fidelity one. Within-document, chunking reached 13 (GraphRAG) and 82 (Fidelity) matched literals that sit past the truncation point | pre-registration + first result |
| [052](052-the-passage-the-note-came-from.md) | Chunk vertices for the literature corpus only, **co-indexed into the first-pass pool**, with a citation→chunk anchor carrying its location in the source, adjacency and mentions edges, verbatim floor retained. The ~100x node-explosion objection dies on measurement — papers are **2.1%** of the archive, so ~3,790 nodes and 0.4x growth. Co-indexing is the one configuration measured to recover the gap (14.5 of 15.9pp); expansion over verbatim chunks measured a no-op, so adjacency is a secondary affordance, not the mechanism. Semantic "one complete idea" segmentation dropped as a probable red herring (an extra full-corpus LLM pass bought 2.1pp within noise; finer units at constant fidelity cost 3.7 of 16.3pp) | design |
