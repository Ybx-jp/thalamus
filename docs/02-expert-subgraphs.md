# Expert Subgraphs — the Specialist Roster

**Status:** built — the consultation-ticket protocol (see "The ticket protocol"
below), expert #2 (evaluation-methodology, [08](08-roster-candidates.md)), and
session pinning are all live. Pinning inverted the lab/001 limit into the
mechanism: one process = one pin ("the process is the pin",
[07](07-harness-integration.md), lab/003).

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

Pinning mechanics (as built — process-level detail in
[07-harness-integration.md](07-harness-integration.md)): the pin is decided at
*launch* (`thalamus pin <scope>` / `thalamus roster`), carried by the process
environment, enforced server-side by the MCP server that read it at startup, and
recorded tier-0 in the pin ledger. The eval loop's per-expert utility signal
([04-eval-loop.md](04-eval-loop.md)) later grades pin quality — sustained
low-utility retrievals in pinned sessions means either the pin or the expert needs
work, and the data says which.

## Inter-expert exchange: the subagent protocol

Sessions cross domains anyway — mid-session, the pinned expert will face a question
outside its scope. The answer is not to re-route the session; it's **consultation**:
the pinned expert consults another expert through the harness's own subagent
protocol (a subagent invoked with the consulted expert's scope), and the exchange is
preserved as episodic memory **on both sides**.

- The **consulting** expert records: what it asked, what came back, whether the
  answer was used, outcome attribution.
- The **consulted** expert records: what it was asked, what it served — its episodic
  memory grows even in sessions it wasn't pinned to.
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

## The ticket protocol (as built, 2026-07-16)

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
   produce a citable answer.
2. **Scoped retrieval** — the consulting session spawns a subagent voicing the expert;
   the recall tools accept the ticket and resolve the granted scope **from the
   exchange record server-side**. An invented or burned ticket grants nothing and
   fails closed. Grants are per-exchange and non-transitive (depth 1, as designed).
3. **Close** — the validated answer lands on the Exchange with `role: citation`
   REFERENCES edges: the answer's evidence-support record. The ticket is burned;
   answered exchanges refuse further answers and grant no further retrieval.
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
written, not where the answer is read. Both are *instantiations* of published
consensus, and claimed as nothing more. What the 2026 scan did not surface is the
coupling itself — a server-minted, single-use ticket where record-creation and
authority-grant are the same act ("not found in the 2026 scan", provisional; see
[11-related-work.md](11-related-work.md) §4).

## Roster discipline

- **M1 ships one expert** (the technical-literature graph). **M3 ships the second**
  — evaluation-methodology, decided and shipped 2026-07-16
  ([08](08-roster-candidates.md) records the selection; an earlier draft guessed
  "per-project code-context" here) — and the second one is the point: it proves
  the contract. Two proves N: the manifest was the whole rollout.
- New experts must justify themselves against the null hypothesis of "just put it in
  an existing expert." The eval loop arbitrates: if a candidate domain's retrievals
  don't cluster, it isn't an expert.
- Experts are cattle behind the contract: creatable, archivable, mergeable. Episodic
  memory archives with the expert — history is never deleted by roster surgery.

## Open questions

- Consultation depth: can a consulted expert consult a third? Start with depth 1;
  let a real failure justify more.
- Auto-pin suggestion from the working directory / recent sessions — nice, but only
  after pin-quality data exists (M4+).
- Whether a session may be re-pinned mid-flight or must spawn a new session. Start
  with immutable pins; simpler episodic semantics.
