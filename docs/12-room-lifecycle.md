# Room Lifecycle — Ceremonies, Dispatch, and What Gets Recorded

**Status:** design. The room *boundary* is built — `--room`, `thalamus room
create/list/show`, the outbound room guard, per-room `CLAUDE_CONFIG_DIR` with its own
`projects/` and `sessions/`, and the `thalamus eval rooms` manipulation check
([lab/045](../lab/045-the-registry-that-was-not-the-socket.md),
[lab/046](../lab/046-the-third-channel-is-the-transcript.md),
[lab/047](../lab/047-the-room-that-was-only-a-variable.md),
[lab/048](../lab/048-the-treatment-that-was-only-a-label.md)). The lifecycle below is
not built. Nothing here is a measured result about rooms; rooms have never been
measured for efficacy.

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
| Planning / delegation | shared awareness, capacity, commitment | **Yes, stripped.** Disobeying *task* spec is 11.8% of design failures; disobeying *role* spec is 1.5%. The artifact earns its place; the role-casting does not |
| Peer refinement | nobody holds it all | **Yes, with the fan-in redesigned** |
| Demo / presentation | stakeholders can't read diffs; morale; a deadline | **No.** Roommates read the artifact losslessly. Replaced by an *executed* acceptance gate, justified by failure-to-recognize-completion at 12.4% |
| Periodic status update | managers can't observe work | **No.** The harness can observe. See below |
| Retrospective | fallible memory; blame-free reconstruction | **Split.** Reconstruction cut; generalization kept as a gated promotion |
| Deliverables report | a legible summary for a person | **Yes**, as a projection over the log and a forecast, not a narrative |

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
**timeout**, a third state distinct from both. Award follows by mutual selection
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

### 3. Peer review — per deliverable, verdict-structured

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
(`scope:literature:claim:2ccb4a49b8c47659`) — but *"differently-pinned agents avoid
diversity collapse"* is an untested hypothesis in this architecture, not a finding. The
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

**The retrospective is split.** Its reconstruction half is cut: it exists to defeat human
memory decay, and the transcript already holds the episode losslessly. Its generalization
half is kept as **proposals, never as writes** — see below.

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

## Memory: reads stay live and timestamped

**The room does not read a frozen snapshot.** Freezing costs three things:

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

The general form, and the direction to grow in: a frozen per-room copy is the degenerate
special case of transaction-time-as-of reads. Isolation is a property of the *operation*,
not a global setting — the Berenson–Adya hierarchy has been lifted onto the agent write
path, where replay inconsistency reads as a fuzzy read forbidden by snapshot isolation
(`scope:literature:claim:50aceaa7c47f413e`), with bitemporal event/ingestion time as the
established substrate (`scope:literature:claim:b738e9bce09f762f`,
`scope:literature:claim:c1d0cce6d2ffea1e`). The alternative of reading live and detecting
contradictions by similarity is measured to fail: surprise-gate supersession is worse than
naive RAG in the abstention regime, leaking stale facts 25–60% of the time
(`scope:literature:claim:6d92063c4fbf3b77`).

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

1. **A ceremony ledger** — one append-only row per *occasion*, written at ceremony
   **start** so an aborted ceremony still leaves a row:
   `{room, ceremony_kind, occasion_index, ts_start, ts_end, participant_scopes[],
   deliverable_ids[], arm, assignment_seed, prereg_id}`. Modeled on `pins.jsonl`.
2. **Ceremony non-occurrence** — a skipped retrospective is a row. Otherwise a skip is
   indistinguishable from an unlogged ceremony, and the only naturally-occurring ablation
   available is lost.
3. **A stable `deliverable_id`**, minted at planning and carried across every revision.
   Nothing in a finished graph tells you two artifacts at two times were one deliverable.
4. **The assignment record and its seed, written before the ceremony runs.** A
   randomization-inference reference distribution is the set of assignments that *could
   have* happened; unrecorded in advance, that set does not exist.
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
**out of `RoomTopology.edges`** and surfaced as a separate `dispatched` count: a broadcast
is the stimulus, not the collaboration, and folding it into edges would let a room pass
its own manipulation check on operator action alone.

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
contamination is arXiv 2605.17830. Isolation levels over an agent write path are TOKI
(arXiv 2606.06240); bitemporal graph memory is Graffiti-style event/ingestion time.
Event-sourced orchestration with replay verification is ESAA. The statistical position —
few treated clusters, randomization inference, anytime-valid monitoring — is carried in
`eval-methodology` and applied in [04](04-eval-loop.md).

Provisionally not found in the 2026 scan (see [11](11-related-work.md) §4): a measurement
of whether identical-prompt fan-out to heterogeneous specialists yields independent or
correlated contributions; a named pathology for a self-fork participating in a group it
dispatched to; and any measurement of read-snapshot isolation helping or hurting agent
*collaboration*.

## Open questions

- Whether co-assertion within a single ceremony occasion should collapse in
  `witnesses.py`, where room co-membership does not — a [09](09-schema-and-federation.md)
  amendment, not decided here.
- Whether scope pinning buys diversity or only different evidence over identical priors.
- Whether `eval/rooms.py`'s node identity should become a member id rather than a scope,
  which any design placing two same-scope members in one room requires.
- SendMessage delivery between two live room members is **unmeasured** — the room-boundary
  rows in the guard ledger are fixtures. Any part of this design that assumes SendMessage
  delivers to an interactive session is unevidenced.
