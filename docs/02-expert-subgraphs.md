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
  the control plane does and doesn't need — are the `add-roster-expert` skill,
  jointly held by main and homelab; homelab keeps it current. It lives here, in
  `harness/skills/`, beside the code that declares the agents it governs: the
  manifest, `pin.py`'s window mechanics, and the procedure for adding an expert
  version together, and a skill that names `thalamus-<scope>` belongs with the
  package that defines what a scope is. What does *not* live here is the generic
  hazard write-up it indexes — session ownership, cgroup kills, PATH inheritance in
  tmux panes — which is true of any systemd-owned tmux session driven over HTTP and
  is maintained in the control-plane repo for the wider audience it has.

## Open questions

- Consultation depth: can a consulted expert consult a third? Start with depth 1;
  let a real failure justify more.
- Auto-pin suggestion from the working directory / recent sessions — nice, but only
  after pin-quality data exists (M4+).
- Whether a session may be re-pinned mid-flight or must spawn a new session. Start
  with immutable pins; simpler episodic semantics.
