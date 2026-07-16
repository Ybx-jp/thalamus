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

**Claim we retired:** "almost no memory system in the wild has a trust model." True
circa 2024; false now. Retained only as historical framing, never as a live claim.

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
rejected at write time." We converged; we did not originate.

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
write-path-provenance consensus*, not a first. The design choice to defend it is
vindicated by this literature; the claim to have discovered the need is not
available to us.

## 2. Evaluation

**Claim we retired:** "the industry answers 'does memory help?' with vibes." Also
now false. The field has explicitly shifted from retrieval-QA proxies to
downstream, action-coupled evaluation.

- **Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging
  Frontiers** (survey, arXiv 2603.07670) — names the shift: retrieval precision is
  the wrong test; downstream agent performance is the ultimate one. This is
  [04-eval-loop.md](04-eval-loop.md)'s opening argument, published as survey
  consensus.
- **Mem2ActBench: Evaluating Long-Term Memory Utilization in Task-Oriented
  Autonomous Agents** (arXiv 2601.19935) — inference-driven memory grounded into
  *executable tool calls*: does the agent infer task-critical constraints from
  history and act on them.
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

## 4. What the scan did *not* find claimed elsewhere

Stated narrowly and provisionally — absence in one scan is weak evidence, and this
list is the first thing to re-check on every future scan:

1. **The utility→decay loop closing on live deployment traces of a single
   operator's real coding sessions**, feeding an archival (never deletion)
   forgetting policy graded per-expert. The benchmarks measure; none self-maintain
   on the operator's own stream.
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
