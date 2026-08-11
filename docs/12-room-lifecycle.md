# Room Lifecycle — Ceremonies, Dispatch, and What Gets Recorded

**Status:** design, with the capture layer built. The room *boundary* is built —
`--room`, `thalamus room create/list/show`, the outbound room guard, per-room
`CLAUDE_CONFIG_DIR` with its own `projects/` and `sessions/`, and the `thalamus eval
rooms` manipulation check
([lab/045](../lab/045-the-registry-that-was-not-the-socket.md),
[lab/046](../lab/046-the-third-channel-is-the-transcript.md),
[lab/047](../lab/047-the-room-that-was-only-a-variable.md),
[lab/048](../lab/048-the-treatment-that-was-only-a-label.md)). **Items 1–4 of *What is
recorded*, below, are built** — `harness/ceremonies.py` and `thalamus ceremony`. The
ceremonies themselves, dispatch, and the promotion path are not. Nothing here is a
measured result about rooms; rooms have never been measured for efficacy.

## What a room is for

A room puts several long-lived, differently-pinned expert sessions into one
collaboration with a boundary around it. The honest justification is narrow, and
stating it narrowly is what keeps the feature from being decorative.

Under a fixed reasoning-token budget with good context utilization, single-agent
systems are more information-efficient than multi-agent ones — an information-theoretic
argument via the Data Processing Inequality (`scope:literature:claim:be24e99a17184318`),
and measured to hold on multi-hop reasoning across three model families when reasoning
tokens are held constant (`scope:literature:claim:414011b1207b38ef`). Multi-agent
systems become competitive in the specific case where single-agent context utilization
degrades (`scope:literature:claim:24bd7f990bd37f8a`).

Thalamus clears that bar for a reason that is structural rather than hopeful: pinned
sessions hold **genuinely disjoint private memory**. A literature session and a homelab
session do not have overlapping subgraphs, and no single context window holds both.

The consequence is a standing rule:

> **A room is for work no single pinned session could do, because the memory it needs
> lives in more than one scope.** A room opened for a question one expert could answer
> has paid tokens to lose information.

## The test every ceremony must pass

The proposed ceremonies are agile-shaped, and agile ceremonies are scaffolding around
five human constraints: lossy memory of what happened, invisibility of others'
work-in-progress, calendars and capacity, politics and psychological safety, and the
social contract of a public commitment.

> **A ceremony that exists to fix a human constraint is pure token cost here.** Each one
> must earn its place against a constraint agent sessions actually have.

Scored against MAST's measured failure prevalences over 150 traces at κ=0.88
(`scope:literature:claim:d675b5b74b2cdd34`, `scope:literature:claim:8b660e6b3d8c66c0`),
with overall multi-agent failure rates of 41%–86.7% across seven systems
(`scope:literature:claim:c65fffb4ca7bbba9`) as the backdrop:

| Ceremony | Human constraint | Survives? |
|---|---|---|
| Planning / delegation | shared awareness, capacity, commitment | **Yes, as a specification artifact.** Disobeying *task* spec is 11.8% of design failures. Role *casting* is not negotiated here — not because roles are cheap but because a room already has them (see below) |
| Peer refinement | nobody holds it all | **Yes, with the fan-in redesigned** |
| Demo / presentation | stakeholders can't read diffs; morale; a deadline | **No.** Roommates read the artifact losslessly. Replaced by an *executed* acceptance gate, justified by failure-to-recognize-completion at 12.4% |
| Periodic status update | managers can't observe work | **No.** The harness can observe. See below |
| Retrospective | fallible memory; blame-free reconstruction | **Split.** The reconstruction *narrative* is cut; the structured trajectory record it would have been written from is kept, because cross-episode learning consumes it. Generalization is kept as a gated promotion |
| Deliverables report | a legible summary for a person | **Yes**, as a projection over the log and a forecast, not a narrative |

### Roles are already paid for

Agents rarely *disobey* an assigned role — 1.5% of MAST design failures — but that is a
statement about compliance, not about value. In the only head-to-head ablation available,
**removing role assignments from all agents' system prompts produces the most substantial
performance drop of any ablation**, with Executability falling to 0.58 and Quality to
0.2212 (`scope:literature:claim:dc0520a3b45fda00`) — a larger single effect than the whole
phase chain, which moves Quality 0.2512 → 0.3953.

Role specialization therefore outweighs phase structure on the only evidence held. The
consequence for this design is favourable and easy to miss: **a Thalamus room gets that
effect for free**, because every member is a pinned expert before the room exists. The
planning ceremony does not need to cast roles, and stripping it of role negotiation costs
nothing — the roles were assigned at `--agent` time.

### Phases trade off; they are not uniformly additive

The one real per-phase ablation available halts a staged chain after each phase in turn:
halting after the code-complete phase most enhances Completeness, the testing phase is
what carries Executability, and Quality rises steadily as more phases are included
(`scope:literature:claim:7408878870906722`). The underlying table is sharper than the
summary — running the later phases after Complete **lowers** Completeness (0.6250 → 0.5600)
while raising Executability. Adding a stage is a trade, not an improvement, and a lifecycle
that assumes each ceremony is additive is assuming something the only measurement
available contradicts.

**Whether staged structure beats free-form chat at all remains unmeasured.** The staged
systems benchmark against other staged systems; the nearest available result is that
explicitly decomposing a task into subtasks beats a single-step solution, which is a
weaker claim. This is a gap in the record, not a settled point in the design's favour.

## Topology is declared, not derived

A lifecycle says *when* members talk. It does not say *who to whom*, and that residual
is the part measured to matter most: communication topology alone explains **7–40% of
the variance** in whether constraints survive multi-hop forwarding, an effect comparable
in magnitude to the choice of backbone model (`scope:literature:claim:d214a1d799bcaf4f`,
`scope:literature:claim:3fbfc547e3554758`). Suboptimal topology silently erases the
safeguards of capable models (`scope:literature:claim:6d82a6eee6d423f6`). An entire
research line searches topology space because the task underdetermines it
(`scope:literature:claim:de74d45636d93ddb`, `scope:literature:claim:6d396dbbd963d6c8`).

> **The room's topology is an explicit artifact of room-open, on the same footing as the
> task specification.** Who may address whom, and at which ceremony.

Undifferentiated fan-out is not the default to fall back on. Dense unconstrained
connections incur redundant token overhead and accumulate task-irrelevant noise
(`scope:literature:claim:9db15d4954c4958f`), and the measured win goes to minimal
designs with **restricted** communication — one orchestrator, few specialists — which
beat substantially larger single-agent models on tool-intensive work
(`scope:literature:claim:6bd2739f69dd958a`).

## The lifecycle

### 1. Open — the announcement

Room-open emits a **task specification**, not a role assignment ritual. The wire format
is a Contract Net task announcement, which carries four mandatory slots — **task
abstraction, eligibility specification, bid specification, expiration time**
(`scope:literature:claim:379bfe7a08735b1a`). The extra three slots are what turn a
broadcast into *focused addressing*: a member reads the eligibility slot and discards
the rest without paying to process it (`scope:literature:claim:eab9a0a7009286ed`).

Members reply with a **bid or a decline**. Declining is a protocol-legal reply and
carries information — this expert judged itself ineligible. Silence past expiration is a
**timeout**, a third state distinct from both.

Making decline legal is a mitigation with a named instrument behind it. **Instruction
Decay Rate** measures whether an agent keeps obeying a hard behavioral constraint after
peer messages implicitly or explicitly normalize violating it — conformity toward a
dispatcher or a peer — and reaches 10.1% on the weakest model measured. An expert with no
protocol-legal way to say *this is not mine* is an expert under exactly the pressure IDR
scores. Whether a legal decline actually lowers it is testable rather than assumed. Award follows by mutual selection
(`scope:literature:claim:6cf315a4dc9ee645`), and no member is designated manager or
contractor a priori: any node takes either role, which is what lets `main` and an expert
dispatch through one mechanism (`scope:literature:claim:e6ae389d5dbb70cf`).

Also minted at open: a stable **`deliverable_id`** per deliverable, the declared
topology, and a named graph snapshot (see *Memory*, below).

### 2. Work — pull, not push

**There is no periodic status broadcast.** The ceremony exists because a human manager
cannot observe work in progress; the harness can. A self-report costs writer tokens,
costs every reader's tokens, and is unverified where the event log is ground truth. The
two things it is meant to catch are the two the log catches better: step repetition
(15.7%, and an agent in a loop does not know it is looping) and failure to recognize
completion (12.4%) — both log-side predicates
(`scope:literature:claim:d675b5b74b2cdd34`).

A scheduled broadcast is also a fan-in event at every recipient, firing on a timer
rather than at a boundary, and a predictable-length periodic message is a scheduled
compaction pump — compaction compresses trusted and untrusted context uniformly
(`scope:literature:claim:bef29058c20a5485`) and can be forced at a chosen moment by
controlling payload length (`scope:literature:claim:f0229be163340092`).

What replaces it: a **status projection** derived from the event log for the operator,
and a **pull primitive** for members — *what has changed in the room log since my last
read, filtered to my open constraints*. Pull-on-relevance is the side with numbers:
proactive retrieval improved pass@1 by +8.3pp on Terminal-Bench 2.0 and +6.8pp on
tau2-Bench, for both weaker and stronger action agents
(`scope:literature:claim:8e17b07c5293abee`).

The **update** message survives for the case it was actually needed: an operator-initiated
change to the task landing mid-flight. It expects no reply and does not interrupt.

### 3. Peer review — per deliverable, adaptive, verdict-structured

**Review rounds are capped and break early; they do not run to convergence.** Three
independent measurements agree on the shape and disagree only on the ceiling: Self-Refine
caps feedback-refine iterations at **4** per task, continuing until a task-specific quality
criterion is met or the cap is reached (`scope:literature:claim:83138f9449e95a1f`), with
gains concentrated in round one (Code Optimization 22.0 → 27.0 → 27.9 → 28.8); debate
performance rises monotonically with rounds at three agents but **flattens above four**
(`scope:literature:claim:0e96be689f7cd38d`); and in translation most examples reach their
optimal answer after a *single* round, where forcing the debate onward **harms** the
result. Returns can also go negative inside the cap — in multi-aspect tasks an iteration
improves one quality dimension while degrading another.

So the ceremony is an adaptive loop with a hard cap of 4, an early break, and a
**keep-best-scored-output** rule rather than keep-last. A fixed per-deliverable round count
is the shape the evidence argues against.

That has a measurement consequence worth stating: the round count becomes endogenous, so
it is a *mediator* to record and not part of the treatment. The assignable contrast stays
review-versus-equal-cost-non-peer-pass.

**Rooms stay small.** Increasing debaters from 2 to 3 or 4 *degrades* performance, because
longer debate text causes participants to forget prior views and makes summarization harder
(`scope:literature:claim:4faaac2ea7553b4b`; COMET 84.4 → 83.1 → 82.9). Measured on
translation with same-backbone debaters, so the transfer to a heterogeneous-scope room is
an argument rather than a result — but it is the only direction the evidence points, and it
argues against wide rooms.

Cross-scope critique is the room's value proposition and the configuration the project
has already argued is safe: cross-role review between different scopes, pins and goals
is **peer** review, where self-enhancement bias requires the judge and the judged to be
the same trajectory ([02](02-expert-subgraphs.md)). It is also the only ceremony on this
list that is measurable (see *How this is measured*).

An open caveat, stated because the roster rests on it: differently-*pinned* sessions
differ in retrieved context, not in weights, priors, or decoding. If diversity collapse
in same-model debate is driven by shared priors, scope pinning buys *different evidence
over identical priors*, not diversity. Retrieval state is a real lever — memory-induced
risk is detectable from the retrieval state before generation occurs
(`scope:literature:claim:2ccb4a49b8c47659`).

The debate literature was procured to settle this and **does not support it.** One weak
datapoint in favour: initializing each debating agent with a *different persona* rather
than identical prompts improved MMLU accuracy 71.1 → 74.2 (Du et al., arXiv 2305.14325) —
+3.1 points on one benchmark, from persona diversity inside one model. Against it: MAD
raises diversity substantially over self-reflection (Self-BLEU 19.3 → 49.7, human-judged
bias 29.0 → 24.8) while using **the same backbone in different debate roles**, and the
paper recommends that configuration explicitly; and adding debaters degrades results
(above). CAMEL measures role-play win rates (76.3% vs 10.4% preference) and does not
measure diversity at all, so it cannot support the premise either.

One nearby finding is *not* applicable and is recorded so it does not get misread: with
**different backbone LLMs**, a judge disproportionately favours the debater whose backbone
matches its own. Thalamus members share a backbone and differ in retrieval, so that
particular bias is out of scope here.

Net: one weak supporting number, two pointing the other way. *"Differently-pinned agents
avoid diversity collapse"* remains an untested hypothesis in this architecture, and the
test is cheap: run one critique loop with all roommates on a single scope versus their
own, and measure whether minority constraints survive.

### 4. Acceptance — executed, not presented

The gate is a **completion check run against the deliverable**, not a meeting. What the
demo ceremony was reaching for is the 12.4% failure-to-recognize-completion bucket, and
what that demands is an executed predicate. The gate is also the commitment point: the
deliverable is frozen under its `deliverable_id` and acquires an identity that can be
cited, diffed and resolved later.

### 5. Close — a forecast and a set of proposals

The room emits two things, and neither is a narrative.

**The deliverables report is a forecast.** A machine-readable commitment list —
`{deliverable_id, owner_scope, claim, predicted_artifact, resolve_by}` — which *tooling*
resolves later against git and the graph. This converts a self-report into a falsifiable
prediction, and a forecaster cannot Goodhart a resolution it does not control. It also
yields a calibration curve, which is a real result at any corpus size, unlike a treatment
effect.

**The retrospective is split.** What is cut is the *narrative* — a prose reconstruction
written for a reader who cannot re-read the episode, which is a human constraint. What is
**kept** is the structured trajectory record underneath it: the two affirmative
cross-episode learning methods both consume exactly that, one by comparing a failed
trajectory against a successful trajectory for the same task to pinpoint mistakes, the
other by identifying common patterns across successful trajectories from different tasks
(`scope:literature:claim:bcc46db731c6cbc2`). Cutting reconstruction wholesale would remove
the input the mechanism runs on. The generalization half is kept as **proposals, never as
writes** — see below.

## The fan-in is where rooms fail

The measured harm is specific to **converging-DAG nodes**: an agent weighing competing
parent inputs discards constraints carried by a **minority branch**, a bottleneck
structurally absent from linear chains (`scope:literature:claim:235e5d1161f63190`,
`scope:literature:claim:5a61ed05996e1eca`). A fan-*out* is a diverging node and is not
implicated.

This is load-bearing here because **a phase gate is by construction a converging node**,
so a ceremony list manufactures one per boundary on the critical path. In a room of
heterogeneous experts, the specialist who disagrees with the other three *is* the
minority branch — so an unguarded fan-in preferentially deletes the reason the room was
built, and does it while producing output that reads as consensus.

Two mitigations, both mandatory at every fan-in:

1. **Aggregate verdicts, not prose.** The Consistent Minority Effect — a textually
   *consistent* response winning string-based majority vote despite being a numerical
   minority, because varied benign responses split the vote — is removed by switching to
   **verdict-based aggregation** (`scope:literature:claim:f69e10e3d960b21b`). Asking a
   synthesizer to merge four prose reports is running string-consistency arbitration.
   Asking each member for a structured verdict per open constraint is not. (Measured in a
   memory-poisoning setting; the transfer to a room fan-in is an argument, not a result.)
2. **Persist dissent as a durable artifact.** The failure mode is *discard*, so the fix
   is a record the discard cannot erase. Every fan-in writes which constraints were
   carried by a minority and what became of them.
3. **Route hard constraints past the aggregator, not through it.** Converging DAG
   produces the *lowest* mean tracer durability of the evaluated topologies for three of
   four models, while direct-routing topologies preserve tracers almost completely. So
   aggregation is what you do with *opinions*; a constraint that must survive travels
   direct to the party that has to honour it, and appears at the fan-in as a checked
   precondition rather than as one input among four.

Two consequences follow, and they bound the first mitigation rather than reversing it.
**Minimize the number of fan-ins** — verdict aggregation is the right thing to do at a
converging node, and a converging node is still the worst-measured topology, so a ceremony
that adds one must be paying for it. And **consensus events are themselves the vector for
false-belief spread**: Consensus Pollution Rate — the fraction of downstream responses
endorsing or implicitly relying on a single falsehood seeded in one agent's context —
reaches 40.3% on the weakest model measured. Maximizing consensus events maximizes
exposure, which is a second reason the answer is *fewer, better-structured* fan-ins rather
than more.

## The retrospective is a promotion event

The retrospective is the only ceremony whose output outlives the room, and in a system
with persistent memory that makes it the highest-volume, highest-generality **promotion**
event in the lifecycle. A bad retrospective is not a wasted hour; it is a durable defect
injected into every future room.

The harm side is dense and quantified:

- Agent architectures typically have **no validation step between the memory write
  decision and persistent storage** (`scope:literature:claim:ac991558bec41e1d`).
- MemoryGraft achieved persistent cross-session compromise of an experience store with
  **10 poisoned seeds in 110 entries → 48% poisoned retrieval proportion**
  (`scope:literature:claim:a6011bd18cd6ced3`), exploiting "the semantic imitation
  heuristic, the tendency to replicate patterns from retrieved successful tasks"
  (`scope:literature:claim:bbe6f608a3dd4614`) — which is a precise description of what a
  retrospective writes.
- Skill-Procedure Insertion commits an adversarial step to procedural memory, after which
  the self-improvement loop reinforces it across future executions
  (`scope:literature:claim:16a25e687e4906c3`). A scheduled retrospective is an
  institutionalized skill-synthesis trigger.
- Violation rates **trend upward with accumulated memory**, the failure mode named
  temporal memory contamination (`scope:literature:claim:3795a661d0275a29`,
  `scope:literature:claim:67264a3927e4ebe1`).
- A classifier at the gate does not fix it: retraining PIGuard on memory-poisoning data
  moves TPR 38.33% → 47.67% at FPR 0.33% → 5.33%
  (`scope:literature:claim:1e534d23abeacde5`), and no provenance-free retrieval-time
  filter can achieve a non-trivial worst-case certificate against an adaptive
  multi-session adversary (`scope:literature:claim:b2dc45c539882811`).

The design response is the one this project already reached on its own write path: **gate
the promotion of content into persistent memory — the untrusted-to-trusted transition —
rather than filtering input** (`scope:literature:claim:85be2ae986dfc53b`,
[05](05-trust-model.md)). Concretely, a retrospective emits proposals; promotion carries
provenance; retrospective-authored claims are scope-tagged distinctly and **decayable**,
so the question *"which future rooms did this reach, and did it help?"* stays answerable.
Building the amplifier without the meter is the failure to avoid.

**The gate is graded, not binary.** The working prior art is ExpeL's insight store, which
promotes and demotes through four operators — ADD, EDIT, UPVOTE, DOWNVOTE — where each
insight carries an importance count starting at two, moves with UPVOTE/EDIT/DOWNVOTE, and
is **removed when it reaches zero**. That is a promotion gate with a demotion path and a
built-in death, which is strictly better here than an accept/reject decision made once at
write time: the hazard being defended against compounds with accumulated exposure, so the
defence has to keep acting after the write. Agent Workflow Memory pairs the same shape with
an evaluator gating induction on judged success.

## Memory: isolation is per operation, not per room

**The room does not read a frozen snapshot.** Freezing *everything the room reads* costs
three things:

1. A room on a read-only snapshot cannot recall **its own** earlier work — on day two, a
   member reading a day-one snapshot cannot see its own day-one distillation. The pinned
   snapshot server is read-only by design (`scope:eval-methodology:claim:d86a0f06cd12eeeb`),
   so reads and writes would address different stores.
2. Staleness grows with room duration, duration correlates with task difficulty, and so
   frozen reads handicap hard rooms by construction — a confound aligned with the
   outcome.
3. Cross-pollinating memory is a mechanism of the treatment, not noise in it.

What replaces it is stronger and mostly built. **Reproducibility of a published number is
a property of the analysis, not of the run**, which is what `substrate/snapshots.py`
exists for: take a named snapshot at room-open and room-close, register both, let the
room read live. Run-level replay is already covered by the trace tap
(`~/.thalamus/traces/*.jsonl`), which records verbatim what each recall actually
returned, whether or not the store moved.

### The adjudicating read is the exception

"Live everywhere" would be the wrong conclusion, and a room that resolves disagreements is
exactly where it breaks. Isolation is a property of the **operation**, not a global
setting: the Berenson–Adya hierarchy has been lifted onto the agent write path, where each
contradiction-resolution operator carries an isolation *precondition* — last-writer-wins at
read-committed, **evidence-weighted merge at snapshot isolation**, await-confirmation at
read-committed-with-callback, per-rule at serializable — and replay inconsistency reads as
a fuzzy read forbidden by snapshot isolation (`scope:literature:claim:50aceaa7c47f413e`).
Unversioned live reads are read-committed at best, the level that admits replay
inconsistency: *re-adjudicating the same contradiction returns a different winner.*

A verdict-based fan-in **is** an evidence-weighted merge. So:

> **Ordinary recall reads live. An adjudicating read — any fan-in resolving competing
> member verdicts — reads as-of a pinned transaction time and logs the adjudicating judge
> by key.** Keyed logging of the judge is what makes the verdict replayable at all; a
> verdict-based room with a live-read judge and no keyed verdict log admits replay
> inconsistency by construction.

This costs nothing the room needs. The three costs above are costs of freezing *ordinary
recall* — a member's own history, the fresh cross-scope material, the mid-room
cross-pollination. None of them apply to a single adjudication step reading a pinned point
for the duration of one resolution.

The alternative of reading live and resolving contradictions by similarity is measured to
fail outright: surprise-gate supersession is worse than naive RAG in the abstention regime,
leaking stale facts 25–60% of the time (`scope:literature:claim:6d92063c4fbf3b77`).

### Two time axes, not one

"Timestamped" understates what is required. The substrate is **bitemporal** — event time
separated from ingestion/transaction time (`scope:literature:claim:b738e9bce09f762f`,
`scope:literature:claim:c1d0cce6d2ffea1e`) — and collapsing them is measured to cost real
accuracy: separating dialogue time from occurrence time recovers **12.2 accuracy points**
on LongMemEval and LoCoMo, an axis production memories routinely collapse. A room-open
snapshot name pins the transaction axis; it does not supply the event axis, and the two are
not substitutes.

## Correlated writes, and the occasion as event identifier

The sharper hazard is on the **write** side. Members of one room distilling at close
produce highly correlated writes asserting substantially the same conclusions, and a
convergence count over distinct asserting sessions reads one room's single opinion as
N-fold independent corroboration.

[09](09-schema-and-federation.md) §Scope settles the general case and this design lives
inside it: a fork **collapses** because the dependence is certain; a room is **flagged and
left counted**, because a room hosts many turns and is therefore not an event identifier,
so collapsing by it would trade a false-count error for a false-collapse error.
`substrate/witnesses.py` implements exactly that, and the note surfaces in the recall path.

A **ceremony occasion is an event identifier** in the way a room is not. Four members
answering one announcement is one event. Whether co-assertion within a single occasion
should collapse — where co-membership does not — is an open schema question, carried by
the same `occasion_id` the ceremony ledger records. It is not decided here.

The cheap falsifier, to run after the first real multi-member room: execute the
convergence traversal and check whether any claim's supporting sessions all share a room.
If none do, the hazard is theoretical.

## What is recorded from ceremony one

Capture is now-or-never; analysis never is
([lab/048](../lab/048-the-treatment-that-was-only-a-label.md)). Items 1–4 make later
analysis *possible*; 5–10 make it *honest*. If anything is cut, it is not from 1–4.

**Items 1–4 are built** — `harness/ceremonies.py`, driven by `thalamus ceremony
start/end/skip/mint/revise/assign/show/audit`, writing
`~/.thalamus/ceremonies/ceremonies.jsonl`.

1. **A ceremony ledger** — one append-only row per *occasion*, written at ceremony
   **start** so an aborted ceremony still leaves a row:
   `{room, ceremony_kind, occasion_index, ts_start, ts_end, participant_scopes[],
   deliverable_ids[], arm, assignment_seed, prereg_id}`. Modeled on `pins.jsonl`.
   `ts_end` arrives as its own `end` row rather than as a mutation, so an append-only
   file never has to be rewritten in place; the pairing key is `occasion_id`,
   `<room>:<kind>:<index>`, which is also what item 8 puts on the session record.
2. **Ceremony non-occurrence** — a skipped retrospective is a row. Otherwise a skip is
   indistinguishable from an unlogged ceremony, and the only naturally-occurring ablation
   available is lost. **A skip consumes an occasion index**: the counter numbers the
   moments a ceremony was due, not the times it ran, so renumbering around a skip would
   erase the non-occurrence the row exists to preserve.
3. **A stable `deliverable_id`**, minted at planning and carried across every revision.
   Nothing in a finished graph tells you two artifacts at two times were one deliverable.
   Minting one title twice yields two ids rather than merging, because a false merge
   interleaves two revision histories beyond later separation.
4. **The assignment record and its seed, written before the ceremony runs.** A
   randomization-inference reference distribution is the set of assignments that *could
   have* happened; unrecorded in advance, that set does not exist. The row carries what
   a seed alone cannot replay: the eligible units *as they stood*, the arm sizes, the
   block (the room, which is how the never-swap-across-rooms restriction becomes
   structural), the space, and a versioned `procedure` naming the deal that consumed the
   seed.

**The four share one ledger, and every row carries an `event`.** Sharing is what makes
"the assignment preceded the occasion" answerable by *position* rather than by a
second-resolution timestamp two writes can tie on. The discriminator is not optional
decoration: undiscriminated rows sharing the pin ledger are what made last-row-wins
read a correctly-launched fork as having met no obligation.

`thalamus ceremony audit` reads the ledger against these obligations and exits non-zero
on a defect it can still name today: an occasion carrying an arm nothing assigned in
advance, an assignment written after its occasion started, a realized arm contradicting
the deal, a deliverable id used but never minted, an orphaned end, a duplicated
occasion id. A `start` row never defaults its `arm` from the assignment — copying one
into the other would make a randomization that was not honoured unobservable from
either record alone.
5. **Commitment rows** — `{room, deliverable_id, owner_scope, commitment_text,
   predicted_artifact, resolve_by}`.
6. **Resolution rows, written by tooling and never by a member**, at each later occasion
   and at a fixed post-close horizon.
7. **The out-of-room comparator, identified contemporaneously.** The arms are
   solo / ticket / room; a comparator chosen after the fact is a dead comparison.
8. **A ceremony-occasion id on the session record**, so `eval/cost.py` can attribute burn
   per ceremony.
9. **Room provenance on every claim the room produces**, so `witnesses.py` can flag
   correlated witnesses.
10. **The pre-registration itself, committed to git before room one**: primary endpoint,
    harm endpoint, α, ρ, equivalence margin, exclusion rule, and the falsifiers.

**Dispatch rows** live in `~/.thalamus/guards/` in the existing row shape, carrying
`dispatch_id`, `fanout`, `via`, `sender`, `target`, and a per-target delivery outcome
(pre-flight status, performed-or-refused, post-send `updatedAt` delta). They are kept
**out of `RoomTopology.edges`**: a broadcast is the stimulus, not the collaboration, and
folding it into edges would let a room pass its own manipulation check on operator
action alone. The exclusion is structural rather than remembered — rows carry
`guard: "dispatch"`, which `eval/rooms.py`'s existing `guard == "room-boundary"` filter
drops without needing to know dispatch exists.

## Delivery mechanics

Delivery to a live pinned session is `tmux send-keys`, which is the only substrate the
console can use — it is a stdlib HTTP server with no messaging socket. Measured behavior
against a real interactive session:

| target status | text | the following Enter |
|---|---|---|
| `idle` | lands in the composer | submits it |
| `busy` | lands in the composer | **queues** — order preserved, processed as the next turn |
| `waiting` | **discarded** | **actuates the highlighted default** |

The third row is why dispatch pre-flights. A permission prompt or trust dialog turns a
blind send into an approval of a tool call the sender knows nothing about, and the first
message to a freshly spawned member is the most likely to hit it.

> **Dispatch reads `$CLAUDE_CONFIG_DIR/sessions/<pid>.json` per target, delivers on
> `idle` and `busy`, and refuses on `waiting`, naming the target.** Never a bare Enter
> into a `waiting` window.

**Built** — `harness/dispatch.py`, `thalamus dispatch <room> [message]` with `--to`,
`--partial`, `--dry-run` and the four announcement slots. A status outside the measured
three is refused rather than assumed to behave like `idle`.

**Pre-flight covers the whole fan-out, not each target in turn.** Delivering to the
reachable members and skipping the rest is the tolerant-looking choice that corrupts the
protocol: an announcement admits a bid, a decline, and silence-past-expiration as three
distinct states, so a member that never *received* one is silent in a way that reads as
a timeout. Every target is therefore pre-flighted before any is written to, and one
undeliverable target refuses the whole dispatch naming it. `--partial` proceeds and
records the undelivered names **on every row**, which is what keeps the later reading of
a silence honest rather than merely permitted.

`harness/quick.py` already parses that descriptor (`LiveSession.status`, `between_turns`),
and for a room the descriptors live in the room's own `sessions/`, so enumerating them
*is* enumerating live membership. Liveness is `pid` + `procStart` against `/proc`; where
the tmux window list and the descriptor roster disagree, dispatch refuses rather than
guesses. Confirmation is `updatedAt` advancing plus a new user record in the JSONL —
never grepping the pane, which `capture-pane` truncates to the visible height.

Dispatch follows the console's confirmed-spawn path and never `pin.spawn` directly:
`tmux new-window` exits 0 whether or not the command execs
([console-hazards.md](console-hazards.md)). Members must launch via `pin.spawn --room`
with the room passed explicitly, because `room_members()` reads the room off `pins.jsonl`
and a room whose members carry no room row is invisible to `eval rooms`.

**Roommates launch in an auto permission mode.** A dispatched member that stops at a
permission prompt is a dispatch that silently did not happen, and nothing in `pin.py`
passes a permission mode today, so every spawned member currently launches in manual mode.
The mode is `acceptEdits` plus a **room-owned** `settings.local.json` allowlist rather
than a blanket bypass: `acceptEdits` alone silently denies Bash, and bypass removes the
one control measured to fully stop prompt injection — with policy checks enabled FIDES
stops all attacks in AgentDojo, without them every planner succumbs
(`scope:literature:claim:073ccf38c98a731a`) — while turn caps buy nothing, attack success
being flat across caps of 3, 5 and 7 (`scope:literature:claim:bfeb0aa001de6b45`). The
room's config dir partitions discovery, transcripts and MCP servers and **nothing else**:
not the filesystem, the network, or the operator's credentials.

## How this is measured

Room-level causal inference is **hopeless at this corpus size, and no design fixes it.**
Two independent reasons: the randomization-inference floor, computed from
`eval/randomization.py` — 5 rooms give a floor of 0.100 and 6 give 0.067, so the design
cannot produce p ≤ 0.05 at *any* effect size, with `smallest_design(alpha=0.05)`
returning (7, 3) — and, decisively, rooms will not be randomized. A room is opened when
work seems to warrant it, so treatment is self-selected and confounded with task size and
difficulty, leaving randomization inference without a reference distribution. Effective
sample size collapses to the number of clusters.

> **"Does the lifecycle work?" is descriptive forever at this corpus size.** Rooms are
> reported as a case series — manipulation check, cost, and commitment-resolution rate per
> room — with no p-value attached.

The rule that makes the ceremony list tractable:

> **A ceremony is measurable if and only if it has multiple independently-assignable
> occasions within a single room.**

By that test **peer review is the only measurable ceremony** — many occasions per room,
assignable per deliverable, with rooms as exchangeability blocks and permutation
restricted so a deliverable is never swapped across rooms. Status updates have many
occasions but permanent carryover, which is also why switchback is the wrong frame here:
it requires a finite specifiable carryover order, and a ceremony's carryover is permanent.
Planning, acceptance and the retrospective are one occasion each and are not measurable at
this n. Restructuring a ceremony to fire more often so it becomes countable would be
changing the ceremony to suit the instrument.

The peer-review ablation's control must be an **equal-cost non-peer pass** — otherwise the
contrast is "an extra agent spent tokens", which measures compute rather than feedback.
Cost-match via `eval/cost.py` and pre-register the match. Monitoring is
`eval/sequential.py` with ρ and the equivalence margin pre-registered before room one, so
futility is a reportable outcome.

**Endpoints.** The deliverables report is *not* the endpoint, and no LLM judge over it can
be: grading it is grading prose the treated unit wrote about itself. This project has
measured what its cheap judges carry — `eval/attribution.py` scores roughly 59 points of
shared-project vocabulary against 4 points of discrimination — so a house-style judge on
room reports is that instrument with its floor removed. Instead:

- **Primary** — the downstream fate of the room's commitments, measured outside the room:
  did the predicted artifact appear, did the delegated item become a claim, and does a
  later **non-room** session build on it, re-litigate it, or retract it. Signed both ways.
  Resolve through the rake pipeline's pair emission and adjudication, **not** through
  content-addressed claim convergence, whose base rate is near the floor (4 in 504 across
  125 sessions) and would read as "nothing durable happened" regardless of truth.
- **Harm** — inflated-witness count: claims converging across ≥2 member scopes whose
  provenance is one room. No judge required; `witnesses.py` already computes the reading.
  Two named instruments sit alongside it: **Instruction Decay Rate** (does a member
  abandon a hard constraint after peers normalize violating it — conformity toward a
  dispatcher) and **Consensus Pollution Rate** (seed one falsehood in one member's
  context, measure how widely it spreads — conformity toward a majority). Worst values
  observed on the weakest model evaluated: IDR 10.1%, CPR 40.3%. CPR is the direct
  measurement of the harm the fan-in design is built against.

  What these two buy is a **seeded stimulus**, not a judge-free score. The planted
  constraint and the planted falsehood give ground truth by construction, which is the
  property the deliverables report can never have. But the scoring still has a judgment
  step — IDR is the fraction of constrained turns *judged* as violating
  (`scope:literature:claim:5be3b4fa2fc79e05`), CPR the fraction of downstream responses
  *judged* as influenced (`scope:literature:claim:9acb46f8bac39eba`). The exact-match
  members of the family are RTD and CLC. So the judge cost is carried here, not
  eliminated, and the claim to defend is that the *stimulus* is known — never that these
  metrics avoid a judge.
- **Denominator** — cost per ceremony, via `eval/cost.py` keyed on the occasion id.

**No collaboration-volume quantity is an outcome.** More ceremonies means more sends, so a
lifecycle-heavy room scores higher on edge counts by construction. `RoomTopology.occurred`
sets the bar at exactly one edge for that reason, and density is not a score.

**Falsifiers, all three registered before room one:**

- **F1** — if a majority of rooms fail the `eval rooms` manipulation check, the ceremony
  structure produced no collaboration and the lifecycle is a label on solo sessions. If
  realized topologies do not *vary* across rooms, topology-as-independent-variable is dead
  for this corpus.
- **F2** — if the fraction of ceremony outputs referenced in any later session *outside*
  the ceremony that produced them is indistinguishable from `attribution.py`'s permutation
  null, the ceremonies produce write-only artifacts and the lifecycle is overhead. Read
  with the null beside the number and with room-mates excluded as null partners.
  Precedent: [lab/042](../lab/042-the-brief-nobody-cites.md).
- **F3** — the peer-review ablation reaching `futile` under a pre-registered margin is a
  result, not a failure.

Exclusion happens **before** outcomes are read: a room that fails the manipulation check
is excluded, never dropped after the fact.

## Prior work

The dispatch format is **Contract Net** (Smith 1980, hand-fed): task announcement with
task abstraction, eligibility, bid specification and expiration; focused addressing;
negotiation by mutual selection; roles not fixed a priori. Thalamus's announcement is an
*instantiation*, not an extension — announce-with-eligibility-and-expiry is 1980 prior art
and is never described as new here. Topology-as-independent-variable and the
converging-node minority-branch discard are AgentCollabBench (arXiv 2605.08647); group-as-
atomic-unit and communication compression are GoAgent; the failure taxonomy and
prevalences are MAST; verdict-based aggregation against the Consistent Minority Effect is
SMSR (arXiv 2606.12703); the write-path-over-input-boundary gate is arXiv 2606.04329, the
experience-store amplification is MemoryGraft (arXiv 2512.16962), and temporal memory
contamination is arXiv 2605.17830. Isolation-level preconditions on contradiction-resolution
operators are TOKI (arXiv 2606.06240); bitemporal graph memory is Graphiti-style
event/ingestion time. Event-sourced orchestration with replay verification is ESAA.
Phase and role ablations are ChatDev (arXiv 2307.07924) and MetaGPT (arXiv 2308.00352);
refinement-round caps are Self-Refine (arXiv 2303.17651) and Du et al. (arXiv 2305.14325);
debate diversity, debater-count degradation and degeneration-of-thought are Liang et al.
(arXiv 2305.19118); role-play without a diversity measurement is CAMEL (arXiv 2303.17760);
the graded insight gate is ExpeL (arXiv 2308.10144) with Agent Workflow Memory
(arXiv 2409.07429) as the induction-gated variant. The statistical position — few treated
clusters, randomization inference, anytime-valid monitoring — is carried in
`eval-methodology` and applied in [04](04-eval-loop.md).

Provisionally not found in the 2026 scan (see [11](11-related-work.md) §4), each checked
against a procurement pass rather than a single recall: a measurement of whether
identical-prompt fan-out to *differently-specialized* agents yields independent or
correlated contributions — the debate literature measures diversity for one backbone in
different debate roles, which is a different construct; a comparison of staged workflows
against free-form chat, since the staged systems benchmark only against each other; a named
pathology for a self-fork participating in a group it dispatched to; and any measurement of
read-snapshot isolation helping or hurting agent *collaboration*.

## What a room would need on Cursor

Measured 2026-08-10 against a live Cursor CLI (`2026.08.04-aaa8809`, lab/054), while
none of this design is built. Recorded as findings; the build-or-not decision is
open, and none of the three channels below has been designed for.

**The boundary channel ports.** `XDG_CONFIG_HOME` moves Cursor's config root to
`$XDG_CONFIG_HOME/cursor/` without moving `$HOME`, and `HOME` moves it too. Both
then report `Not logged in`, so credentials follow the root and a room would have to
provision them — the same obligation `ensure_room` already carries for
`.credentials.json` on Claude Code.

**The discovery channel has nothing behind it.** A room partitions the roster because
peer discovery enumerates `$CLAUDE_CONFIG_DIR/sessions/<pid>.json` and reads each
descriptor's `messagingSocketPath`. **Cursor writes no `sessions/` directory at
all**, and `~/.cursor/agent-cli-state.json` is two fields of global state. So moving
the config root partitions a roster that does not exist: the structural boundary
doing the real work on Claude Code has no Cursor referent, rather than a weaker one.

**The delivery channel does not port.** There is no `--name` and no peer-messaging
surface, so members cannot be addressed. The room guard's roommate pattern matches a
name the launcher gives; without names it has no allow-path.

**The resumption channel ports, and means something different.** Cursor has
`--resume [chatId]` and `create-chat`, but `--resume` continues the parent chat
rather than forking it, so the quick protocol's delta-only distillation — an exact
set difference over message UUIDs — has no Cursor analogue in this shape.

The live-measured consequence for what a Cursor room could be: **isolation without
addressing.** The lab/048 hazard that shape invites is the *inverse* of the obvious
one, and the difference decides what to build. A Cursor room does not produce a
falsely-labelled treatment: `hooks/cursor/session-start.sh` writes
`{session_id, scope, cwd, ts}` and **no `room`** (against
`hooks/claude-code/session-start.sh`, which resolves one), so a Cursor member stamps no
room provenance; and ceremony rows come from an explicit `thalamus ceremony` verb, not
from a member's lifecycle, so they exist only where someone writes them. A Cursor room
is therefore **invisible rather than mislabelled** — it cannot be counted as a room arm,
which also means it cannot be excluded as a failed one. That argues for more capture,
not for refusing to launch one. `thalamus dispatch` is the same story from the other
end: it resolves panes through the pin ledger's `tmux_pane`, which the Cursor
session-start hook does not write, so a Cursor member is undispatchable by the same
absence that makes it uncountable.

Independently of that decision, `pin.py:246` returns a hardcoded
`("CLAUDE_CONFIG_DIR", …)` pair, so the room's boundary is spelled as one harness's
variable rather than declared as a capability.

## Open questions

- Whether co-assertion within a single ceremony occasion should collapse in
  `witnesses.py`, where room co-membership does not — a [09](09-schema-and-federation.md)
  amendment, not decided here.
- Whether scope pinning buys diversity or only different evidence over identical priors.
  Procured against and **not supported**: one weak datapoint for (persona diversity, +3.1
  MMLU), two against (same-backbone debate already achieves the diversity gain; more
  debaters degrades results). The single-scope-versus-own-scope critique loop is the test.
- Whether adding a ceremony is worth the converging node it installs, given that phases are
  measured to trade off rather than accumulate and that staged-versus-free-form has never
  been measured at all.
- Whether `eval/rooms.py`'s node identity should become a member id rather than a scope,
  which any design placing two same-scope members in one room requires.
- SendMessage delivery between two live room members is **unmeasured** — the room-boundary
  rows in the guard ledger are fixtures. Any part of this design that assumes SendMessage
  delivers to an interactive session is unevidenced.
- Decline-as-a-legal-reply has real prior art — Smith's refusal message carries a
  justification slot — but it is present only in the hand-fed text and is not carded as a
  claim, so the design's most-defended dispatch decision currently has no citable vertex.
  An ingest pass over the refusal and immediate-response-bid sections would close it.
