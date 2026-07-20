# Related Work — Where Thalamus Sits in the 2026 Literature

**Status:** living document. Last scan 2026-07-15. This doc exists to keep the
project honest: it states, per pillar, what the published literature already
establishes, and it reduces Thalamus's claim from *novelty* to a defensible,
cited *position*. The rule (from [00-mission.md](00-mission.md)): **never design
from vibes when established research can give us a boost, and never claim novelty
where prior work exists.**

Everything below is drawn from a web scan and read against the design. Citations
are arXiv IDs / venues; a claim attributed to a paper is that paper's claim, not
ours. Where the design predates the scan and lands on the same idea, that is
**convergence, not priority** — and we say so.

## The one-paragraph honest position

By mid-2026 the research frontier has independently converged on all three of
Thalamus's pillars: write-path provenance and trust-tiered memory as the poisoning
defense, downstream/action-coupled evaluation as the successor to retrieval-QA
metrics, and access-governed shared graph memory with provenance-linked traces for
multi-agent systems. Thalamus is therefore **not staking out empty ground** — it is
an *integrated, local-first, single-operator instantiation* of a design the field
is assembling in pieces. Every cited work below does one pillar (a defense, or a
benchmark, or a shared-memory scheme); the contribution here is the **union as
working, inspectable software**, plus two narrower ideas that the scan did not
find claimed elsewhere (§4).

## 1. Trust model & memory poisoning

The attack class is fully mapped:

- **MINJA** (Memory INJection Attack) — query-only poisoning of agents with
  persistent memory, reporting injection-success rates above 95% via bridging
  steps and progressive shortening. Establishes that the operator does not need to
  be the attacker; a crafted *query stream* suffices.
- **MemoryGraft: Persistent Memory Poisoning in LLM Agents** (arXiv 2512.16962) —
  poisoned *experiences* create persistent behavioral drift by exploiting an
  agent's tendency to imitate prior successful trajectories. Directly motivates
  why episodic memory (not just knowledge) needs a trust boundary.
- **From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning
  Attacks in LLM Agents** (arXiv 2606.04329) — a six-class taxonomy (explicit /
  conditional command insertion, salience-driven compaction poisoning, policy-
  conformant fact injection, false-precedent insertion, skill-procedure insertion).

The defenses proposed there are, almost line-for-line, Thalamus's design:

> "existing prompt-injection defenses fail to cover memory poisoning… defenses must
> operate at the **write path, not the input boundary**" — proposing **write-path
> provenance tracking**, **source isolation** (untrusted content never reaches
> trusted-equivalence), and **compaction filters distinguishing trusted from
> untrusted sources** (2606.04329).

That is [05-trust-model.md](05-trust-model.md)'s "gates enforced at the federation
contract," "distillation does not launder," and "orphans/unprovenanced nodes
rejected at write time" — convergence, not origination. "Distillation does not
launder" is enforced, not just stated: the transcript-ingress floor
([05](05-trust-model.md)) down-tiers claims resting on `WebFetch`/`WebSearch`
content to tier 2 at the write path, contract-audited and canary-tested (lab/005) —
the write-path stance instantiated on the *distillation* channel, MINJA (arXiv
2503.03704, in the graph) being the "crafted input stream suffices" motivation.

More that overlaps or exceeds the design:

- **SMSR: Certified Defence Against Runtime Memory Poisoning** (arXiv 2606.12703) —
  a *certified* runtime defense using **Cryptographic Provenance Attestation**.
  Stronger than our tier stamp: it makes provenance unforgeable, not merely
  recorded. A candidate direction for M5 enforcement.
- **MemAudit: Post-hoc Auditing of Poisoned Agent Memory via Causal Attribution
  and Structural Anomaly Detection** (arXiv 2605.23723) — automates exactly our
  "the post-mortem is a graph traversal, not archaeology" audit story, and adds
  structural anomaly detection we do not have.
- **SuperLocalMemory: Privacy-Preserving Multi-Agent Memory with Bayesian Trust
  Defense Against Memory Poisoning** (arXiv 2603.02240) — a **learned, probabilistic
  Bayesian trust** score. This is strictly more sophisticated than our static
  four-tier ladder, and is the sharpest challenge to our design (see §5).
- **Trustworthy Agentic AI Requires Deterministic Architectural Boundaries**
  (arXiv 2602.09947) — the data/control-separation argument (the lineage of
  DeepMind's CaMeL) as an *architecture* mandate. This is our "informs, never
  instructs," and it predates and outframes our version.

**Position:** Thalamus's trust model is a *rigorous instantiation of the emerging
write-path-provenance consensus*, not a first.

## 2. Evaluation

The field has explicitly shifted from retrieval-QA proxies to downstream,
action-coupled evaluation.

- **Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging
  Frontiers** (survey, arXiv 2603.07670) — names the shift: retrieval precision is
  the wrong test; downstream agent performance is the ultimate one. This is
  [04-eval-loop.md](04-eval-loop.md)'s opening argument, published as survey
  consensus.
- **Mem2ActBench: Evaluating Long-Term Memory Utilization in Task-Oriented
  Autonomous Agents** (arXiv 2601.19935, in the graph) — inference-driven memory
  grounded into *executable tool calls*: does the agent infer task-critical
  constraints from history and act on them. Its finding — seven memory
  frameworks remain inadequate at exactly this — is the field-level version of
  the used-vs-ignored gap the traces measure locally.
- **Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks**
  / MemoryArena (arXiv 2602.16313) — sequential subtasks with **causal
  dependencies across sessions**; retrieval intent must be inferred, not handed
  over as an explicit query.
- **AMA-Bench** (arXiv 2602.22769), **Momento** (arXiv 2606.00832) — long-horizon,
  multi-session memory-and-reasoning batteries.
- Counterfactual evaluation exists (e.g., MQUAKE counterfactual edit-pairs used to
  test how systems handle modified stored facts) — so our "memory-degraded" arm is
  a known technique, not a new one.

**What survives as ours.** Every work above is an *offline benchmark*: a fixed
dataset, an external grader, run once. Thalamus's differentiator is the thing none
of them is — an **in-deployment, self-instrumented loop** that traces the operator's
*real* sessions, attributes used-vs-ignored against their *own* retained transcripts,
grades **per-expert pin quality**, and **feeds a utility-driven forgetting policy**.
Benchmarks *measure*; they do not *self-maintain*. The correct framing is therefore
"not a benchmark — a live self-maintenance loop that the offline benchmarks above
complement," and we cite them as the offline half we extend.

### 2b. Cost — the denominator

Grading memory on utility alone is half a fraction; the field already grades the
whole one.

- **Learning Query-Aware Budget-Tier Routing for Runtime Agent Memory** /
  BudgetMem (arXiv 2602.06025) — evaluates memory on explicit
  **performance–cost frontiers**, aggregating input/output token usage per query
  and converting to monetary cost via service pricing. Cost-utility grading of
  memory is established, not ours.
- **AgentOps: Enabling Observability of LLM Agents** (arXiv 2411.05285) —
  taxonomy of agent observability artifacts; **token cost is a session-level
  metric**, analyzable at session/trace/span granularity. Our cost buckets
  (interactive / extract / expert / other) are an instantiation of its
  session-level layer over records the harness already keeps.
- **From Agent Traces to Trust** (arXiv 2606.04990) — execution provenance as
  the *typed graph* of an agent run, including retrieval and memory-access
  steps. Thalamus's Trace substrate is already that shape, so cost lands as
  properties of existing trace records, not a parallel telemetry stack.

Positioning: `thalamus eval cost` ([04-eval-loop.md](04-eval-loop.md)) is a
*convergence* on BudgetMem's cost half and an *instantiation* of the AgentOps
session-level taxonomy — the live-loop framing above is what it adds. BudgetMem
also warns what we trade away by reporting instead of routing: it makes cost an
*optimized control input* (a trained budget-tier router), where we stop at
attribution. If per-expert cost-utility ratios ever drive retrieval decisions,
BudgetMem is the anchor to revisit.

### 2c. Forgetting

- **MemoryBank: Enhancing Large Language Models with Long-Term Memory** (arXiv
  2305.10250, in the graph) — the canonical forgetting policy for LLM agent
  memory: an Ebbinghaus-forgetting-curve update rule in which each memory
  carries a strength, being recalled reinforces it and postpones its decay, and
  unrecalled memories fade with elapsed time until discarded. Decay in agent
  memory is established prior work, not ours.

Positioning of layer 3 ([04-eval-loop.md](04-eval-loop.md)): a *divergence*,
argued not assumed. MemoryBank's forgetting signal is retrieval *occurrence*
(recency and recall count); layer 3's is retrieval *outcome* (used-vs-ignored
attribution against the retained transcript) — a node retrieved often but never
used accelerates toward archive exactly where recall-count reinforcement would
strengthen it. What the divergence trades away: MemoryBank's signal exists for
every node, while utility verdicts exist only for retrieved ones, so
MemoryBank-style time decay is retained as the fallback prior for
never-retrieved nodes. The utility-keyed half is the §4 item 1 claim.

## 3. Federation, experts, and inter-expert exchange

Most crowded pillar as of the scan.

- **Multi-Agent Shared Graph Memory** (Neo4j, NODES AI 2026; William Lyon,
  "When Your Agents Share a Brain," Neo4j Developer Blog, Apr 2026) — shared graph
  memory with **conflict resolution, versioning, provenance**, and **ReasoningTrace
  chains with provenance links back to the entities and messages that informed each
  decision**. That is our exchange edges + contradiction queue, in production
  tooling.
- **Access-governed shared memory** enforcing explicit authority and scope on
  multi-agent reads/writes (surveyed in *Infrastructure for the Agentic Web*, arXiv
  2606.20570) — our federation contract as a permission system, named as a
  first-class design concern.
- **From Agent Traces to Trust: A Survey of Evidence Tracing and Execution
  Provenance in LLM Agents** (arXiv 2606.04990) — a whole survey on the
  provenance-of-reasoning problem we treat as our audit story.
- **Always-On Agents: A Survey of Persistent Memory, State, and Governance in LLM
  Agents** (arXiv 2606.30306) — governance of persistent memory as its own subfield.

**Position:** our single most novel-seeming sub-piece — inter-expert consultation
recorded as first-class, bidirectional, provenance-tracked episodic memory forming
a collaboration graph — now has direct analogues (Neo4j's ReasoningTrace chains).
It remains a good design; it is no longer unclaimed.

### 3b. LLM-written graph queries

- **Multi-Agent GraphRAG: A Text-to-Cypher Framework for Labeled Property
  Graphs** (arXiv 2511.08274) — modular agentic text-to-Cypher over LPGs with
  schema-compliant generation and iterative content-aware correction. The
  free-form query surface as such is established practice.
- **DAIL-SQL** (arXiv 2308.15363) — the benchmark study of prompt engineering
  for LLM query generation; its measured win is few-shot example selection by
  similarity of *both* the question and the query, and it names token
  efficiency as a first-class metric. Grounds the recipe store
  (`gremlin-python` skill, RECIPES.md): each stored query carries the question
  it answered so future sessions match by use case, and reuse is cheaper than
  regeneration.
- **Self-Debugging** (arXiv 2304.05128) — LLMs correct their own generated
  queries from execution feedback and error messages, with the largest gains
  where feedback is informative. Grounds the guard pair: deterministic,
  instructive rejection *before* execution (the `gremlin-guard.sh` hook for
  lazy un-terminated gremlin-python; the `substrate/query.py` dialect check for
  python spellings on the gremlin-lang surface) is the cheap half of that
  loop — the doomed query is caught where feedback would otherwise be silence
  or a token-recognition error.

Positioning of `memory_query` ([03-master-plane.md](03-master-plane.md)): an
*instantiation* — single-shot rather than multi-agent-iterative, Gremlin rather
than Cypher, schema shipped in the tool description rather than negotiated per
query. What the cited work does not address and we add: the query surface living
*inside* the trust and eval perimeter — pin-gated to the master plane, lexically
read-only atop a gremlin-lang (no-code) server grammar, and rendering vertex IDs
the trace tap prices like any recall. What we trade away: their feedback loop's
correction of failed queries; ours fails fast and lets the agent rewrite.

### 3c. Adaptive retrieval & in-context conditioning

- **Self-RAG** (arXiv 2310.11511) — a single LM adaptively retrieves *on
  demand* via reflection tokens and critiques what came back; indiscriminate
  always-retrieve is the ad-hoc baseline it beats on factuality and citation
  accuracy. The when-to-retrieve decision is a first-class design object.
- **Reflexion** (arXiv 2303.11366) — agents improve without weight updates
  through *linguistic* feedback: reflective text in an episodic buffer,
  re-injected as context, conditions later attempts (91% pass@1 HumanEval).
  Context injection is a working behavior-change channel.

Positioning of the conditioning hooks ([07](07-harness-integration.md)): an
*instantiation* of both — harness-event-triggered, operator-authored lexical
classes instead of Self-RAG's learned reflection tokens, and one-shot throttled
reminders instead of Reflexion's accumulated self-reflections. What we trade
away: the learned per-step retrieval decision (our triggers are regexes an
operator maintains) and self-generated reflection content. What we add from our
own perimeter: every firing is logged and graded by a per-firing behavioral
join (`eval conditioning`) — the conditioning layer is born inside the eval
loop, so an ineffective reminder class is measurable wallpaper, not folklore.

### 3d. Learner modeling & pedagogy (the teacher expert)

- **Deep Knowledge Tracing** (arXiv 1506.05908, NeurIPS 2015) — learner modeling
  as prediction over the raw interaction history: an RNN traces student knowledge
  from exercise streams without hand-authored domain encodings, and the paper
  names intelligent curriculum design as an application of the learned model. The
  premise that matters here: the interaction history *is* the student model.
- **A Trainable Spaced Repetition Model for Language Learning** (Settles &
  Meeder, ACL 2016, P16-1174) — half-life regression makes the forgetting curve
  trainable from large-scale practice-history traces. Grounds "what stuck" as a
  measurable, history-derived quantity; the teach workspace's SR deck instantiates
  the heuristic side of the same idea.
- **LearnLM: Improving Gemini for Learning** (arXiv 2412.16429) — reframes
  injecting pedagogy into an LLM as *pedagogical instruction following*: pedagogy
  specified at the instruction/system level rather than committed to weights,
  deliberately avoiding a single baked-in theory of pedagogy.

**Position:** the teacher expert ([08](08-roster-candidates.md)) is an
*instantiation* of the classic ITS decomposition (domain model / student model /
tutoring model) on Thalamus's own substrate — knowledge subgraph as domain model,
episodic subgraph as student model, manifest-derived context as the tutoring
layer, the last convergent with LearnLM's instruction-level framing and with
[02](02-expert-subgraphs.md)'s "specialization lives in memory, in context." What
the cited work has that we do not: population-scale learning traces (DKT and HLR
both train on massive cohorts). A single-operator learner model accumulates n=1
evidence, so its claims stay observational.

## 4. What the scan did *not* find claimed elsewhere

Stated narrowly and provisionally — absence in one scan is weak evidence, and this
list is the first thing to re-check on every future scan:

1. **The utility→decay loop closing on live deployment traces of a single
   operator's real coding sessions**, feeding an archival (never deletion)
   forgetting policy graded per-expert. The benchmarks measure; none self-maintain
   on the operator's own stream. Nearest prior found: MemoryBank's
   forgetting-curve decay (arXiv 2305.10250, §2c) — but its signal is retrieval
   occurrence, not measured downstream utility; a decay policy keyed on
   used-vs-ignored outcomes was not found in the scan.
2. **The evidence archive as a materialized view over an immutable, content-
   addressed transcript log** — "re-extract, not migrate" (event-sourcing applied to
   memory provenance; [10-evidence-archive.md](10-evidence-archive.md)). Provenance
   *tracking* is everywhere in the cited work; provenance whose **floor is retained
   primary evidence you can re-derive the whole graph from** was not found.
3. **The integration itself** — one local-first system unifying trust tiers +
   federation contract + measured utility loop + human-auditable master plane. Each
   pillar is published separately; the union as working software is the
   engineering contribution, and we should call it an engineering contribution, not
   a research one.
4. **"The mint is the write"** — a server-minted, single-use consultation ticket in
   which creating the exchange record and granting cross-scope authority are the
   same act, so an unrecorded consultation is impossible by construction
   ([02-expert-subgraphs.md](02-expert-subgraphs.md)). The components are all
   published — capability tokens are classical systems security, execution
   provenance and evidence tracing are surveyed in 2606.04990, write-path gating in
   2606.04329 — but the scan did not find the coupling used as a *memory-formation*
   mechanism between agent scopes. Provisional, like everything on this list.

## 5. Open challenges this literature puts to the design

- **Static tiers vs. Bayesian trust** (SuperLocalMemory, 2603.02240). Our four-tier
  ladder is simpler and more legible; is legibility worth giving up learned trust?
  The single-operator scope is the defensible answer — but it must be *argued*, in
  [05-trust-model.md](05-trust-model.md), not assumed.
- **Certified vs. recorded provenance** (SMSR, 2606.12703). Should M5 enforcement
  aim for cryptographic attestation, or is a tier stamp on a local-only graph
  enough? Probably enough for the threat model, but name the gap.
- **Structural anomaly detection** (MemAudit, 2605.23723) is a capability our audit
  story lacks. Candidate backlog item once the graph is large enough for anomalies
  to mean something.
- **Attribution beyond lexical** — the survey (2603.07670) and the benchmarks make
  the case that inferred-intent retrieval is the hard part; our used-vs-ignored
  attribution is lexical (lab/002). This is the honest weak point of the eval loop.

## Maintenance

This doc is regenerated by the `ground-in-literature` skill
([src/thalamus/harness/skills/ground-in-literature](../src/thalamus/harness/skills/ground-in-literature/SKILL.md)):
before any new feature or component is designed, the literature expert is consulted
and any missing foundational source is ingested (`thalamus ingest`) so it becomes a
tier-2 node with a citation. New findings land here and in the graph, so the doc and
the memory stay in step. **A design that cites nothing has not been grounded — it has
been guessed.**
