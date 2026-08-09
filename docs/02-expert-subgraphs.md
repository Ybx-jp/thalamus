# Expert Subgraphs — the Specialist Roster

**Status:** built — the consultation-ticket protocol (see "The ticket protocol"
below), expert #2 (evaluation-methodology, [08](08-roster-candidates.md)), and
session pinning (one process = one pin — "the process is the pin",
[07](07-harness-integration.md)) are all live.

## The idea

A specialist is not a fine-tune and not a prompt wearing a costume. A specialist is
a **retrieval scope**: a curated domain subgraph plus its **own episodic memory** —
what it has been asked, what it retrieved, what happened next. Specialization lives
entirely in memory, in context, inspectable and hot-swappable. That is the thesis:
**an in-context, memory-learned specialist roster.**

Each expert owns two graph regions behind one contract manifest:

- **Knowledge subgraph** — the curated domain network (e.g., the technical-literature
  graph fed by ingestion). Grows by ingestion and by distilled experience.
- **Episodic subgraph** — the expert's lived history: sessions it served, retrievals
  it answered, exchanges with other experts, outcomes attributed back to it by the
  eval loop. This is what makes the expert *learned* rather than merely curated —
  and it compounds: an expert that has served fifty sessions is materially better
  than its knowledge graph alone.

Both regions conform to the federation contract; the episodic schema follows the
base memory system's design (session summaries + open threads as entrypoints).

## Routing: pin an expert to the session

Per-query routing (classify each query, pick an expert) is a hard, failure-prone
subsystem, and a bad router makes a roster strictly worse than one big graph.
Thalamus sidesteps it: **routing is session-granular.** One expert is pinned to a
session at session start, and every memory operation in that session flows through
the pinned expert's scope.

Why this is the right trade:

- **Human-legible.** "This session is a StepMania-research session" is a decision
  the operator can see, predict, and override. A per-query classifier is invisible
  until it's wrong.
- **Coarse-grained is honest.** Coding sessions have a dominant domain; matching the
  common case beats optimizing the rare one.
- **It makes episodic memory coherent.** A session's whole history lands in one
  expert's episodic subgraph, so the expert accumulates *narrative* experience —
  not fragments scattered across a roster.

Pinning mechanics (process-level detail in
[07-harness-integration.md](07-harness-integration.md)): the pin is decided at
*launch* (`thalamus pin <scope>` / `thalamus roster`), carried by the process
environment, enforced server-side by the MCP server that read it at startup, and
recorded tier-0 in the pin ledger. The eval loop's per-expert utility signal
(`thalamus eval pins`, [04-eval-loop.md](04-eval-loop.md)) is *designed* to grade
pin quality — sustained low-utility retrievals in pinned sessions meaning either the
pin or the expert needs work, disambiguated by whether the expert's knowledge earns
its keep when consulted from other scopes. **That reading is suspended and the
report says so.** Pinned utility is within-scope and consulted utility is
cross-scope, and the used-vs-ignored judge scores 62.9% against a retrieval's own
output window versus 5.0% against a different project's session (lab/032, an
arm-level contrast lab/034 leaves standing while withdrawing that entry's absolute
denominators): it would manufacture "ignored under its own pin, used when consulted"
for free. Each side needs its own permutation null before the pair means anything.
The judge's own discrimination at the shipped operating point is κ = 0.140, 95% CI
[0.028, 0.272], against a permuted floor of 57.3% (experiments/001, pinned snapshot
`post-sandbox-purge-20260730`) — a floor that is itself a vocabulary-overlap
artifact, and therefore a lower bound for any population more lexically correlated
than two sessions of one project.

## Inter-expert exchange: the subagent protocol

Sessions cross domains anyway — mid-session, the pinned expert will face a question
outside its scope. The answer is not to re-route the session; it's **consultation**:
the pinned expert consults another expert through the harness's own subagent
protocol (a subagent invoked with the consulted expert's scope), and the exchange is
preserved as episodic memory **on both sides**.

- The **consulting** expert records: what it asked, what came back, whether the
  answer was used, outcome attribution.
- The **consulted** expert records: what it was asked, what it served — its episodic
  memory grows even in sessions it wasn't pinned to, and it reads that record back
  through `memory_consultations`.
- The **master plane** records the exchange edge (who asked whom, when, about what),
  which is how the operator watches the roster actually collaborate.

This is the move that makes the roster more than a partition scheme: inter-expert
exchanges are **first-class memory events**, not lost context in a subagent
transcript. Over time the exchange edges form a collaboration graph — which experts
get consulted together, which consultations produce used answers — and that graph is
itself eval-loop input.

Consultation crosses the federation contract like everything else: the consulted
expert returns *data with provenance*, never directives
([05-trust-model.md](05-trust-model.md)).

## The ticket protocol

**The mint is the write.** `consult_request(expert, question)` mints a single-use
consultation ticket, and minting it *is* opening the `Exchange` record in the graph —
the ticket ID is the Exchange vertex ID, so an unrecorded consultation is impossible
by construction. `consult_answer(ticket, answer)` is the only close path: it validates
that every citation in the answer (backticked vertex IDs, exactly as recall renders
them) resolves inside the consulted scope, rejects uncitable advice with the ticket
left open, and on success records the answer and burns the ticket.

Mechanics, in the order a consultation runs:

1. **Mint** — the server (never the model) validates the expert against the manifest
   roster, assembles the **expert brief** from the consulted scope's own memory (open
   threads, recent sessions, question-matched recall; manifest identity is the only
   tier-0 framing — no hand-written personas), and writes the Exchange: `main` scope,
   `status: open`, with `role: brief` REFERENCES edges to every node the brief served.
   A scope with nothing to cite refuses the mint — an expert with no memory cannot
   produce a citable answer. The question is classified at mint (`kind: design |
   general`, the same lexical rule `conditioning.sh` fires on at UserPromptSubmit),
   so what kind of ticket this was is a stored fact rather than a later judgement.
2. **Scoped retrieval** — the consulting session spawns a subagent voicing the expert;
   the recall tools accept the ticket and resolve the granted scope **from the
   exchange record server-side**. An invented or burned ticket grants nothing and
   fails closed. Grants are per-exchange and non-transitive (depth 1, as designed).
3. **Close** — the validated answer lands on the Exchange with `role: citation`
   REFERENCES edges: the answer's evidence-support record. The ticket is burned;
   answered exchanges refuse further answers and grant no further retrieval.
   Closing a `kind: design` ticket **is** the signal that a design was settled — the
   reason to ask an expert was to act on the answer — so the close names the
   `thalamus-design-readiness` check there rather than waiting for the consulting
   agent to judge that the moment has arrived. Advisory: the check never blocks work
   and never changes a design.
   **Reading its own record** is a separate surface, not a ticket grant: an Exchange
   is a `main`-scope vertex, so the expert's scope filter cannot reach it, and the
   ticket that could dies at the moment of closing — the grant resolves to the
   consulted scope and expires with `status: open`. `memory_consultations` closes
   that gap by confining on the Exchange's `expert` property instead of its scope
   segment, serving answered exchanges only. Server-decided like every other read
   (no ticket, no scope parameter), and it is a read allowance rather than a
   contract change: the contract governs writes, and `main → expert` is already the
   mandated topology. Open tickets stay invisible — an open ticket is a question
   being asked *now*, and serving it through recall would let a session discover
   work it was never handed.
4. **Attribution** — the MCP server cannot see its caller's session (a measured
   harness limit, lab/001), so the Session -[CONSULTS]-> Exchange edge and the
   trace's `exchange_id` land at `eval sync` time, joined through the ticket the
   PostToolUse tap recorded verbatim. Consultation transcripts are sidechains in the
   parent session's JSONL, already retained by the archive; the exchange record
   anchors into them, so later enrichment is `extract` over an anchored slice.

The audit half ([01](01-federation-contract.md)): `thalamus contract check` verifies
CONSULTS edges connect Session → Exchange only, exchange statuses stay in the minted
vocabulary, and an answered exchange carries at least one citation edge — an
answered-but-uncited exchange means something wrote around the protocol.

### Prior work

The 2026 literature already names both halves of this design. The exchange record is
**execution provenance** — "the typed graph of an agent execution", explicitly
including multi-agent collaboration steps — and citation validation is **evidence
tracing**, "the projection of execution provenance onto evidence-support relations"
(survey, arXiv 2606.04990; in the graph as feed `thalamus`). The citation gate's
placement is the write-path stance of the memory-poisoning literature: consultation
is a memory write channel, and "existing prompt injection defenses fail to cover
memory poisoning" (arXiv 2606.04329), so the defense sits where the exchange is
written, not where the answer is read.

The delegation shape is older than any of that and is not ours: Contract Net
(Smith 1980, in the graph as feed `thalamus`) runs task announcement → bid → award
between manager and contractor nodes, and its award both records the agreement and
confers the task — record-creation and authority-grant already coupled. What the
protocol here adds is that the record is *memory*: retained, citable, and closed
only by an answer whose citations resolve. The pure-shared-medium alternative is
equally prior — Hearsay-II's knowledge sources (Erman et al. 1980, same feed)
coordinate solely through a blackboard, keeping no per-exchange record at all.
The surviving claim is confined to the memory-formation half and stays provisional
([11-related-work.md](11-related-work.md) §4).

## What an expert knows about its own corpus

**A document's contribution is earned at runtime, not declared at ingest.** "How does
this paper bear on the scope" is already answerable from structure that exists: an
`Exchange` records the question asked, and its `REFERENCES {role: citation}` edges
record which claims the validated answer rested on. Walk a `Source` to its claims and
back out through those edges and you have the paper's contribution in its own earned
terms — the actual questions it was cited to answer, verbatim, no summarization step:

    g.V().hasLabel('Exchange').as('e').outE('REFERENCES').has('role','citation')
      .inV().hasLabel('Claim').out('DERIVED_FROM').hasLabel('Source')
      .has('title', containing('<paper>')).select('e').dedup().values('question')

This is **better evidence than a precomputed summary**, because it records what the
paper was *used for* rather than what someone anticipated it might be good for. It is
also the shape the literature argues for: BudgetMem (arXiv 2602.06025) characterizes
offline, query-agnostic memory construction as inefficient and prone to discarding
query-critical information, and positions runtime utilization as the alternative. A
per-document summary written against a declared concern list at ingest time is exactly
the construction it criticizes, and the cost of getting the concern list wrong is
silent — the discarded material leaves no trace. So no `Contribution` node type, no
declared concern vocabulary, and no recompute pass. **The exchange questions are the
concerns, revealed rather than declared.**

The consequence for the local/global split ([11](11-related-work.md) §3e): the *local*
surface is the traversal above and it is already built. The *global* surface — "how
does this corpus position us on X" — is a reduce over the questions and cited claims a
topic has accumulated, run when asked. Precomputation buys nothing at this corpus size
that the reduce does not, and GraphRAG's community layer is not taken at all: its
demonstrated benefit sits three orders of magnitude up (conditions-not-met plus the
curation argument, **not** a measurement — nothing in the record reports either
method's behavior at this size).

**The real gap is cold sources, and it is measurable today.** A paper that was ingested
but never cited in an exchange has no earned contribution — 10 of 37 sources in the
`literature` scope, measured 2026-07-28. Some are legitimately another project's feed;
the thalamus-relevant ones are cold for a reason worth naming, because
`arXiv:2605.17830` is among them despite a readiness run recording that it *changed the
design in three places*. It entered through a briefing aside instead of a consultation
ticket, so it changed the design while leaving no exchange record — the lane violation
the readiness protocol was rewritten to close, visible here as a hole in attribution.
**Cold-source count is therefore a coverage metric, not just a curiosity**: it counts
literature that reached the design through an unaudited channel, alongside literature
nobody has needed yet. The two are distinguishable by whether any decision cites the
paper.

Building anything more than that metric waits on the metric saying so — the same rule
[06](06-ingestion.md) applies to ingestion itself. What the teach workspace's literature
map holds by hand (a per-paper "what it shows / where we stand" position, with
provenance sentences added after the 2026-07-26 audit found five trust-cluster papers
asserting content the graph did not hold) is the same object, maintained manually and
free to drift. Generating it from the traversal above is the natural way to close that
drift class, and is the first thing to build here if anything is.

### Briefs are authored here

A readiness brief (the operator-fluency advisor runs after a design is settled, never
before; it lives at user scope, outside this repo, because it holds personal coursework
state) is written **by the literature expert under a consultation ticket**, from the
anchors' claims, the questions those claims have previously been cited to answer, and
the exchange record that settled the design in hand. It lands as a node in the
expert's own scope and renders to a file in the teach workspace for reading. Nothing
is precomputed for it: the anchor set is 2–4 papers, so the traversal is cheap at
authoring time and reflects the graph as it stands rather than as it stood at ingest.

Its trust tier falls out of an existing rule rather than a new one: derived from
tier-2 content, it stays tier-2 ([05](05-trust-model.md)), so a brief *informs, it
never instructs* — the correct register for a teaching artifact, and the mechanical
reason a brief cannot change a design. The authorship separation is the point. The
session that made the design decision supplies the anchor list and the exchange id;
it does not write the prose, so a brief cannot quietly teach the decision in place of
the literature the decision rests on.

## The quick protocol: a second tier, for the room

`thalamus quick ask <expert> "<question>"` is the whole surface, and
`thalamus quick targets` lists what is forkable and how recent each parent is. A calling
agent reaches it through Bash, not through a tool of its own: the full ticket is an MCP
tool because minting is instant, while a quick call blocks for a minute or more, and the
MCP server is one process serving every session — a blocking subprocess inside it would
stall the memory tools of sessions that are not consulting anyone.

Inside a [room](07-harness-integration.md), the full ticket is the wrong instrument for
a question the caller is *blocked on*. Its cost is not the mint or the brief but the
cold subagent recalling its way to competence: 303 s, 372 s, 383 s, 417 s, 462 s across
five measured consultations ([lab/043](../lab/043-two-forks-and-i-measured-the-wrong-one.md)).
The quick protocol answers from a **fork of the expert's own live session** instead —
`claude -p --resume <sid> --fork-session`, warm, blocking on stdout. The parent is never
signalled and keeps working; **non-interruption is why this forks rather than messaging
the live expert**, and it is the *asynchronous communication* requirement the
inter-agent coordination literature already names (arXiv 2505.02279, feed `thalamus`).

**Warmth is a cache, and a cache's failure mode is staleness, not absence.** The
tempting argument — that the fork's transcript already holds vertex IDs rendered by its
parent's earlier recalls, so warmth *is* retrieval — concedes more than it wins. Those
IDs were retrieved to answer a **different question**, so the citation gate would be
validating resolvability rather than relevance; naive RAG serves the superseded value
15–40% of the time (arXiv 2606.11400) and a fork has no supersession mechanism at all;
and position bias puts the parent's earlier recalls mid-transcript while the question
arrives at the end, degrading use of exactly the region the argument depends on
(arXiv 2307.03172). So the tier is defined by what it **keeps**:

1. **The record, in full.** The mint is still the write — both tiers open their
   exchange through one `open_exchange`, and a `protocol: quick` Exchange is a
   multi-agent collaboration step, which is inside the definition of execution
   provenance (arXiv 2606.04990), not an exception to it. `protocol` is a separate
   field from `kind`, which classifies the *question*: a quick exchange can still
   settle a design, and the readiness check must still fire when it does.
2. **Citation validation, unchanged.** `contract check` constrains Exchange `status`,
   not `protocol`, and its one real invariant — an answered exchange cites something —
   is the write-path defense the memory-poisoning literature puts exactly here
   (arXiv 2606.04329). The lighter tier does not get to bend the audit — but the
   **launcher** is the closer, not the fork: closing *is* acceptance, and acceptance is
   downstream of the ledger check, so an answerer that burns its own ticket through the
   MCP tool closes the exchange before the check that would have gated it can run
   ([lab/050](../lab/050-the-first-live-quick-call.md)). The fork is told its reply is
   the answer; one that closes anyway is recorded as `closed_by: fork` rather than
   fought, because a gate the answerer can step around is a report and the record has to
   say which it was.
3. **At least one fresh in-ticket recall.** One, against the cold path's many. This is
   what converts warmth from retrieval *replacement* into cache *revalidation*: it costs
   about the embedding floor, it re-renders tier labels adjacent to the answer, and it
   puts a citation in the position-favoured region. Without it the tier is a decorated
   snapshot. **Counted, not asserted** — `fresh_recalls` is read off the fork's own
   records, so an answer that merely claims to have recalled reports zero and says so
   in the caller's output.

And by what it **drops**, which is one thing, not three:

- **The brief is dropped**, and its absence is *recorded as a fact* — silence and "no
  brief served" are the same bytes, and only one is auditable. Evidence tracing is the
  projection of execution provenance onto evidence-support relations (arXiv 2606.04990),
  so dropping the `role: brief` half is a lossy but well-defined projection, legitimate
  only while the record says which projection it is.
- **The grant is not dropped — it is degenerate.** A compact assertion that this fork
  inherits parent P's scope S as of fork point F. The delegation literature's own
  tiering (arXiv 2510.19619) splits the credential's *format*, never its *presence*, and
  the same field set satisfies the keyed-answerer minimum that replay consistency
  requires (arXiv 2604.14022). It is also the only way to check the fork actually armed
  the expert's scope, which it does not do by inheritance
  ([lab/049](../lab/049-the-fork-is-the-whole-conversation.md)).

**The tier is chosen by question type, and the discriminating property is prior
commitment — not the grammatical mood of the question.** Lookups into the expert's own
corpus take the quick path, and so does ordinary **cross-role review**: a visual-explainer
expert asking a subject-matter expert whether a representation is faithful is peer review
between different scopes, pins, goals and skills, which is exactly the exchange the room
exists to make cheap. What takes the full ticket is narrower — any question where **the
expert already has a stake in the thing being judged**. The room's public phase makes that
common: if the expert helped shape the plan the caller is now executing, its "review" is
partly self-review, and self-enhancement bias needs precisely that identity between judge
and judged (arXiv 2411.15594). The test is operational: **is the artifact under review
already in the fork's inherited context?** If it is, the expert is not an independent
reader of it and the exchange belongs on the full path.

**The exchange must price itself, and record both cache fields.** The entire
justification is a latency claim, so a quick exchange that does not log its own
wall-clock and tokens makes that claim unfalsifiable — and a cost figure taken without
`cache_read_input_tokens` is how [lab/049](../lab/049-the-fork-is-the-whole-conversation.md)
first got this wrong by 16×. Every closed quick exchange carries `wall_ms`, `cost_usd`,
`num_turns`, both cache fields and the derived `cache_hit`, plus the parent's `status`
and age at fork point — the cost *predictor*, recorded while the descriptor still
exists rather than reconstructed afterwards.

**The answer is accepted only after the fork's own ledger row agrees with the launch.**
`--agent thalamus-<scope>` and `THALAMUS_FORKED_FROM` are launcher obligations
([07](07-harness-integration.md)), and a fork that missed either produces a good-looking
answer in the expert's voice filed under the wrong scope, or a dependent witness filed as
an independent one. Divergence leaves the exchange open with the reason on the record;
the cost is written either way, because it was spent either way.

**Forking is cheap; answering is not. The first live call cost $0.975 at an 82% cache
hit.** A fork of a parent active seconds ago reads that parent's entire prompt-cache
prefix and creates only the new turn — a 100% hit, ~$0.03–0.08 even for a large parent —
but that is the price of *arriving*, measured on a one-word prompt. A real answer
(88.9 s, 8 turns, 4,784 output tokens, three mandated recalls) cost a dollar with the
cache working as designed ([lab/050](../lab/050-the-first-live-quick-call.md)). Price
follows output tokens, the same reduction latency follows.

What recency governs is the *input* side, and there it is bimodal: a cold parent, or a
fork whose `--agent` does not match its parent's, pays $0.55–1.35 to re-create the
prefix, and a **mid-turn** fork pays 13× the post-turn price, because a truncated
conversation lands on no cached block boundary. Warmth decays inside the nominal TTL
(44.8% at 38 minutes).

This is a scheduling property, not a budget line. **The room largely answers it**: a room
is a co-working cluster by construction, so its members are active in the same window and
the warm case is the common one — the "roster is normally idle" figure that first
suggested otherwise was drawn from the *solo* roster, which is the wrong population for a
room in use. What survives is narrower and still unmeasured: how often a room-mate is warm
*enough*, given that warmth decays inside the nominal TTL, and the mid-turn case, where
non-interruption steers `quick` toward a busy expert and a truncated conversation lands on
no cached boundary. Waiting for the current turn to land is the cheapest available
optimisation, and a room-level cache pre-warm would close the rest.

**Availability is a harder constraint than warmth, and the solo roster fails it
outright.** A session is registered in the live roster from the moment it starts but files
no transcript until its first *turn*, so a spawned-and-untouched expert is live and
**unforkable** — `--resume` exits 1. Measured on this roster: of four live pinned expert
sessions, three had never been spoken to and the fourth was mid-turn
([lab/050](../lab/050-the-first-live-quick-call.md)). The launcher checks for the parent's
transcript before minting, so an unforkable parent costs nothing, and `thalamus quick
targets` reports it. The room remains the only argument that this tier has anyone to call,
and it is still the unmeasured one.

### Prior work

The intra-cheap / inter-expensive split is **not ours**: GoAgent makes `Intra-Topology`
a literal field of its group schema and selects groups as atomic units "jointly
capturing intra-group cohesion and inter-group coordination" (arXiv 2603.19677, feed
`thalamus`). Contract Net's focused addressing narrows the *recipient set* while leaving
all four announcement slots intact (Smith 1980) — a task announcement is a brief, so it
supports a fast path and gives no cover for a briefless one; its speed win is early
award, not a thinner message. Hearsay-II indicts the fork directly on its own criterion:
credibility rises with involvement in *mutually supporting clusters* (Erman et al. 1980),
and a fork agreeing with its parent is not an independent supporter. Budget-tiered memory
routing is BudgetMem (arXiv 2602.06025).

What survives is narrow, and phrased as [11](11-related-work.md) requires: answering a
delegation by **forking the answerer's live context instead of briefing a fresh one,
while retaining a citation-validated exchange record**, was not found in the 2026 scan.
Every component has prior art; the composite is the claim.

### What the measurement can and cannot say

Pre-registered before any arm runs, per [04](04-eval-loop.md):

- **Powered: latency — but the endpoint must be re-registered, because the direction is
  not what the design assumed.** Paired, at the *caller's* boundary (mint → answer
  accepted, so queueing is not smuggled out), one-sided sign test; five questions all
  favouring warm is p = 0.031. What a same-instrument matched pair now shows
  ([lab/049](../lab/049-the-fork-is-the-whole-conversation.md)) is that **wall time per
  output token is invariant at 12.4–13.9 ms** across warm and cold alike, so a warm fork
  does not generate faster and "which is faster" reduces to "which emits fewer tokens".
  In the protocol's **own restricted shape** the fork was 1.5× *slower* and 1.6× dearer,
  having written 65% more output; unrestricted, it was 1.9× faster and cheaper, because
  the cold arm spent 21 tool calls rediscovering its subject. **The fork buys skipped
  discovery, not speed** — so the endpoint is directional only against a comparator
  allowed to discover, and a one-sided test would otherwise be registered against the
  wrong tail.
- **Powered: a harm tripwire, not a safety proof.** Plant a premise the record
  contradicts — drawn from *real superseded decisions in the graph*, so difficulty is set
  by the record rather than invented — and score whether the answer contradicts it, with
  the cold arm as floor. Both tiers catching it reads as uninformative, never as safe.
  Both experts proposed this contrast independently.
  **The endpoint is an interaction, not a level, and the test is two-sided.** Sycophancy
  rises with the *epistemic commitment expressed in the prompt* (SWAY, arXiv 2604.02423),
  so the caller asserts each planted premise at graded confidence and the measurement is
  whether warmth **flattens or steepens** that confidence→agreement slope relative to
  cold. Flatter means warmth is protective; steeper means contaminating. Asking only "did
  the warm arm agree?" cannot separate those, and the predicted direction is *protective*
  (below) — so a design that can only detect harm would confirm itself by construction.
  SWAY's metric is unsupervised, needing no ground-truth labels, no judge and no
  multi-turn structure, which is the constraint [04](04-eval-loop.md) works under. It also
  rules out the obvious mitigation: instructing a model to be anti-sycophantic measures
  poorly there, so "tell the fork to push back" is not the fix.
- **Refused: non-inferior answer quality — for a structural reason, not a budgetary one.**
  All three methods for setting a non-inferiority margin — point-estimate, fixed-margin
  (FDA-recommended), synthesis — are anchored on a prior effect estimate for the active
  comparator (PMC5341347). Here the comparator is a cold consultation, and this project
  has no measured quality distribution for it, so none of the three can be executed and
  any margin would be bare expert opinion — the residual category whose under-reporting
  that review's headline finding indicts. The proxy problem compounds it: citation count
  is confounded with the treatment's own mechanism, since warmth makes citing cheap and
  inflates the proxy in precisely the arm under scrutiny. A null would be
  indistinguishable between "warmth did not hurt" and "the proxy cannot see the harm" —
  the confounded zero [04](04-eval-loop.md) declined once already. **Recorded as a
  refusal, not a null**, and lifted the moment the cold path has a quality distribution
  of its own. A load-bearing-citation *ratio* is the candidate proxy replacement, since
  free citing raises both terms.
- Both arms fire in parallel off one frozen brief with **write-back suppressed until both
  close**, or the first answer becomes memory the second recalls.

**The predicted direction is protective, and an earlier reading of it here was
backwards.** Sycophancy is alignment to *the interlocutor's* position. A fork does not
inherit the interlocutor's position — it inherits **its own**: the expert's earlier
reasoning and recalls, with the caller's premise arriving as a new turn at the end, the
same place it arrives in a cold consult. What inherited context predicts is therefore
**self-anchoring** — over-trusting what it already holds, the failure MemSyco-Bench
actually names as failing to *reject memory as factual evidence* (arXiv 2607.01071) — and
against a false premise that makes a warm expert *more* likely to push back, not less.
The caller-agreement risk lives on the **room** axis instead, where shared phase-1 framing
can make a peer's premise the expert's own prior commitment in another voice; `room`
already marks that correlation and `forked_from` marks the fork one
([09](09-schema-and-federation.md)). An earlier draft called a fork "the maximal case" of
conditioning-raises-agreement, conflating the two: **withdrawn**. Neither paper measures
either regime, so the tripwire tests the transfer rather than confirming it — in both
directions.

## Roster discipline

- The roster ([08](08-roster-candidates.md) records each selection) is two
  consultants — **technical-literature**, **evaluation-methodology** — and two
  spines — **homelab**, **teacher**. The second expert was the point: it proved
  the contract. Two proves N — the manifest was the whole rollout, and it stayed
  that way for #3 and #4.
- New experts must justify themselves against the null hypothesis of "just put it in
  an existing expert." The eval loop arbitrates: if a candidate domain's retrievals
  don't cluster, it isn't an expert.
- Experts are cattle behind the contract: creatable, archivable, mergeable. Episodic
  memory archives with the expert — history is never deleted by roster surgery.
- The mechanics of a roster addition — manifest, anchors, the tmux window, and what
  the console does and doesn't need — are the `add-roster-expert` skill,
  jointly held by main and homelab; homelab keeps it current. It lives here, in
  `harness/skills/`, beside the code that declares the agents it governs: the
  manifest, `pin.py`'s window mechanics, and the procedure for adding an expert
  version together, and a skill that names `thalamus-<scope>` belongs with the
  package that defines what a scope is. What does *not* live here is the generic
  hazard write-up it indexes — session ownership, cgroup kills, PATH inheritance in
  tmux panes — which is true of any systemd-owned tmux session driven over HTTP and
  is kept vendor-neutrally in [console-hazards.md](console-hazards.md) for the wider
  audience it has.

## Open questions

- Consultation depth: can a consulted expert consult a third? Start with depth 1;
  let a real failure justify more.
- Auto-pin suggestion from the working directory / recent sessions — nice, but only
  after pin-quality data exists (M4+).
- Whether a session may be re-pinned mid-flight or must spawn a new session. Start
  with immutable pins; simpler episodic semantics.
