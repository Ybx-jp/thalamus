# Related Work — Where Thalamus Sits in the 2026 Literature

**Status:** living document. Last scan 2026-08-01. This doc exists to keep the
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
is assembling in pieces. Most cited work below does one pillar (a defense, or a
benchmark, or a shared-memory scheme); the contribution here is the **union as
working, inspectable software**, plus two narrower ideas that the scan did not
find claimed elsewhere (§4). The exception is §6 — shipped memory systems that
integrate several pillars at once, and are therefore the neighbours against which
duplication has to be admitted rather than the papers against which position is
argued.

## 1. Trust model & memory poisoning

The attack class is fully mapped:

- **MINJA** (Memory INJection Attack) — query-only poisoning of agents with
  persistent memory, reporting injection-success rates above 95% via bridging
  steps and progressive shortening. Establishes that the operator does not need to
  be the attacker; a crafted *query stream* suffices.
- **MemoryGraft: Persistent Compromise of LLM Agents via Poisoned Experience
  Retrieval** (arXiv 2512.16962, in the graph) — poisoned *experiences* create
  persistent behavioral drift by exploiting the agent's **semantic imitation
  heuristic**, its tendency to replicate patterns from retrieved successful tasks.
  The attacker needs only write access to ingestion-level artifacts the agent reads
  during execution (a README, say); union retrieval over lexical (BM25) and embedding
  similarity then surfaces the grafted entries on semantically similar tasks.
  Validated on MetaGPT's DataInterpreter with GPT-4o, where a small number of poisoned
  records account for a large fraction of retrieved experiences on benign workloads.
  Directly motivates why episodic memory (not just knowledge) needs a trust boundary.
  Its own proposed defense is **Cryptographic Provenance Attestation** — the agent
  signs validated experiences with an enclave-held key and retrieval verifies the
  signature — which is the write-path stance again, one notch stronger than a tier
  stamp.
- **From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning
  Attacks in LLM Agents** (arXiv 2606.04329, in the graph) — a six-class taxonomy
  (explicit / conditional command insertion, salience-driven compaction poisoning,
  policy-conformant fact injection, false-precedent insertion, skill-procedure
  insertion) over **four memory write channels** (explicit instruction-executed,
  system-prompt-driven, compaction-driven, experience-to-procedure) and **nine
  structural vulnerabilities** at three levels — model capability (V-M1–2), system
  prompt design (V-P1–2), agent architecture (V-S1–5). The three architecture-level
  ones are the pre-registration spine of [05](05-trust-model.md)'s leak-channel audit.
  Its metric is deliberately two-phase: ASR (did the payload reach persistent storage)
  and RSR, conditioned on ASR (did the stored entry change behaviour on a later
  query) — measured at 50.46% / 41.05% across OpenClaw and HERMES.

The defenses proposed there are, almost line-for-line, Thalamus's design:

> "existing prompt-injection defenses fail to cover memory poisoning… defenses must
> operate at the **write path, not the input boundary**" — proposing **write-path
> provenance tracking**, **source isolation** (untrusted content never reaches
> trusted-equivalence), and **compaction filters distinguishing trusted from
> untrusted sources** (2606.04329).

That first clause is measured, not asserted: four input-boundary detectors (PIGuard,
DataFilter, CommandSans, PromptArmor) are evaluated against memory-poisoning payloads
and none achieves both high true-positive and low false-positive rate; retraining them
on memory-poisoning data does not meaningfully help, which the paper reads as a
structural limit rather than a training-distribution one, and every detector falls off
sharply on weak-signal payloads that carry no syntactic anomaly. That negative is what
makes a write-path floor the load-bearing defense rather than a belt-and-braces one.

That is [05-trust-model.md](05-trust-model.md)'s "gates enforced at the federation
contract," "distillation does not launder," and "orphans/unprovenanced nodes
rejected at write time" — convergence, not origination. "Distillation does not
launder" is enforced, not just stated: the transcript-ingress floor
([05](05-trust-model.md)) down-tiers claims resting on `WebFetch`/`WebSearch`
content to tier 2 at the write path, contract-audited and canary-tested (lab/005) —
the write-path stance instantiated on the *distillation* channel, MINJA (arXiv
2503.03704, in the graph) being the "crafted input stream suffices" motivation.

More that overlaps or exceeds the design:

- **SMSR: Certified Defence Against Runtime Memory Poisoning in Persistent LLM Agent
  Systems** (arXiv 2606.12703, in the graph) — Signed Memory with Smoothed Retrieval:
  **HMAC-SHA256 provenance tagging at write time** plus randomised retrieval-time
  memory ablation with verdict-based voting, against what it names the Multi-Session
  Memory Poisoning threat. Stronger than our tier stamp: it makes provenance
  unforgeable, not merely recorded, and its component-1 result is a drop from 93–100%
  to 0% attack success. The load-bearing part for us is its **impossibility result** —
  no provenance-free retrieval-time filter can achieve a non-trivial worst-case
  certificate against an adaptive adversary — which is the write-path stance stated as
  a bound rather than an observation. A candidate direction for M5 enforcement.
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

  Both of these landed locally as a measurement rather than a citation. lab/018
  held the arm harness completely fixed and varied only the prompt: a
  self-contained bug report produced zero memory calls, a past-work question
  produced three. The battery's original tasks handed retrieval intent over
  explicitly — exactly what MemoryArena declines to do — so the counterfactual
  had no contrast to measure. lab/019 is the instantiation: `under_specification`
  as a declared, mechanically-checked task property. This is a **convergence** on
  both papers, not an extension; what is local is the enforcement (an
  `absence_check` command, a `floor_rung` that keeps the ladder's bottom
  reachable without memory) rather than the idea.
- **AMA-Bench** (arXiv 2602.22769), **Momento** (arXiv 2606.00832) — long-horizon,
  multi-session memory-and-reasoning batteries.
- Counterfactual evaluation exists (e.g., MQUAKE counterfactual edit-pairs used to
  test how systems handle modified stored facts) — so our "memory-degraded" arm is
  a known technique, not a new one.

**What survives as ours.** Every work above is an *offline benchmark*: a fixed
dataset, an external grader, run once. Thalamus's differentiator is the thing none
of them is — an **in-deployment, self-instrumented loop** that traces the operator's
*real* sessions and attributes used-vs-ignored against their *own* retained
transcripts, with the instrument calibrated against a permutation null rather than
asserted (experiments/001). Two parts of that sentence are weaker than they read.
**Per-expert pin quality** is built but its verdict is suspended: the report compares
a within-scope rate to a cross-scope one, which is the axis the judge confounds, so
it renders numbers and declines to interpret them. And the **utility-driven forgetting
policy** is designed, not built — the loop does not close, and until it does this is a
claim about a design. Benchmarks *measure*; this is built to *self-maintain*. The correct framing is therefore
"not a benchmark — a live self-maintenance loop that the offline benchmarks above
complement," and we cite them as the offline half we extend.

### 2a0. Harness installation — latent configuration errors

The harness only produces evidence if it is actually armed, and the ways it fails
to arm are a studied class rather than a local accident.

- **Early Detection of Configuration Errors to Reduce Failure Damage**
  (Xu et al., OSDI 2016, in the graph) — defines a **latent configuration
  error**: a parameter set at startup but not exercised until much later, so the
  failure surfaces far from its cause. The paper measures that latent errors take
  substantially longer to diagnose than non-latent ones, that 14.0%–93.2% of
  critically important RAS parameters across six deployed systems were vulnerable
  to them, and that 12.0%–38.6% of studied RAS parameters were never used at all.
  PCheck's remedy is to *emulate the late usage at initialization* rather than
  check syntax.
- **Rethinking Software Misconfigurations in the Real World** (arXiv 2412.11121,
  in the graph) — an empirical study of 772 real-world misconfiguration issues,
  of which **317 produced silent errors** with no message and no repair guidance.

Every Thalamus harness fault of this shape has been latent in exactly that sense:
a hook `command` that does not resolve is inert until its event fires, and
SessionEnd fires detached, so the first symptom is memory that quietly stopped
accumulating. `thalamus init`'s verification stage is an **instantiation** of
PCheck's early-detection idea, not an extension of it — it spawns the real
interpreter against the real checkout the way SessionEnd will, instead of
asserting that a path exists. What we give up is generality: PCheck derives its
checkers from source automatically, whereas ours are hand-written for one
harness, so they cover the faults we have thought of and no others.

### 2a. Harness validity — is this failure about the candidate?

A counterfactual arm grades a candidate by running commands in a disposable
worktree, so every verdict inherits the harness's own reliability. CI research
has this problem in its mature form and separates a failure the change under
test explains from one it cannot.

- **Discerning Legitimate Failures From False Alerts: A Study of Chromium's
  Continuous Integration** (arXiv 2111.03382, in the graph) — Fair classifies
  test failures into false alerts and legitimate failures from *failure
  symptoms and test artefacts*, explicitly to avoid the industry default of
  re-running failing tests to detect flakiness.
- **Is this Build Failure Related to my Patch? An Empirical Study of Unrelated
  Build Failures in Continuous Integration** (arXiv 2605.05564, in the graph) —
  77,354 CI build failures across seven Apache projects; PU-learning models
  identify failures unlikely to be caused by the developer's patch, with
  *repeated error messages* among the strongest features.

**How the runner instantiates this.** `arms.classify_infra_fault` reads the
failure symptom rather than re-running — a rerun is not even available here,
since the worktree is destroyed after the run, so it would not be the same
experiment. Faulted runs are **flagged, never excluded**: the verdict stands as
measured and an `attributable: false` stamp rides beside it, matching both
papers' attribute-don't-delete stance and docs/04's rule that a measurement the
runner distrusts must be visible rather than absent. The arm-pair sharpens
2605.05564's repeated-error feature: two arms are two different candidate
sessions against the same ref, so a failure reproducing identically in both is
usually the harness — `render_campaign_faults` reports that, hedged, because a
task no candidate can solve looks the same from here.

**Named divergence.** Both papers *learn* a classifier (Fair's ML model; PU
learning) because CI-scale symptoms are ambiguous and plentiful. A campaign is
n=4 with a handful of hand-root-caused signatures and no rerun budget to save,
so this is deterministic symptom matching — the same distinction at a different
scale, deliberately conservative: an unrecognized failure stays a candidate
defect, because falsely calling one "infra" would excuse a real regression.

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

### 2d. Oracle adequacy — who grades the grader

A graded oracle is an instrument, and an unvalidated instrument reports its own
construction. Software testing has the mature form of this question.

- **A Brief Survey on Oracle-based Test Adequacy Metrics** (arXiv 2212.06118, in
  the graph) — different oracle-based adequacy metrics operate on different
  coverage domains; and the general finding the ladder leans on, that *code
  coverage is a poor adequacy metric and should not be used as an indicator of
  fault-detection effectiveness*. This is why the ladder is ordinal and why the
  mutant verdict is a gate rather than a kill-rate: both would be coverage-family
  ratios.
- **Test Adequacy for Metamorphic Testing: Criteria, Measurement, and
  Implication** (arXiv 2412.20692, in the graph) — adequacy criteria specified
  from the *necessary properties the software satisfies* rather than traditional
  criteria misaligned with metamorphic testing, measured over both the relations
  and the source inputs, with higher adequacy tracking higher fault-detection
  effectiveness. The direct warrant for L3–L5 being nested relations.
- **Does mutation testing improve testing practices?** (arXiv 2103.07189, in the
  graph) — ~15M mutants in industrial use; the load-bearing claim is that
  analysis of past fixes of *real high-priority faults* gives evidence mutants
  are coupled to them, which is what licenses mutants as fault proxies at all.
- **An Empirical Study of the Realism of Mutants in Deep Learning** (arXiv
  2512.16741, in the graph) — the two foundational hypotheses named explicitly
  (competent programmer, coupling effect) and, more usefully, a statistical
  framework that makes *coupling strength* a measured quantity rather than an
  assumption, finding it varies with how the mutant was produced.

**Named divergence.** Both mutation papers describe faults made by *human*
programmers — small syntactic deviations from nearly-correct code, which is
exactly what the competent programmer hypothesis asserts and what makes classical
operators realistic. The candidates graded here are LLM agents under counterfactual
arms, and their failures are a different distribution: plausible wholesale
rewrites, over-fixes that change behavior the bug report never mentioned, fixes
correct at one call site and absent at the others. So the mutants are derived from
*observed arm behavior* rather than from operators, and each one declares the
behavior it mimics ([04-eval-loop.md](04-eval-loop.md)). What this trades away is
the generative scale mutation tooling gets for free: a hand-authored set is 4–6
per task, not thousands, so it is a discrimination *gate* and could never be a
kill-rate even if a kill-rate were wanted. Whether these mutants are in fact
coupled to observed arm failures is asserted from the campaign record, not
measured the way 2512.16741 measures it — the honest gap, and that paper is the
cited method for closing it.

### 2e. Recurrence — deciding "same failure" without an identity

Layer 2b's rake registry ([04-eval-loop.md](04-eval-loop.md)) has to decide
whether a later session met a problem already solved. Content-addressed claim
identity was the obvious answer and it fires 4 times in 504: two sessions never
phrase a problem the same way. "Same failure, different text" is a mature
software-engineering problem with two literatures, both now held.

- **Duplicate Bug Report Detection: How Far Are We?** (arXiv 2212.00548, in the
  graph — `eval-methodology`, feed `rake-recurrence`) — the field's own
  reassessment, and the anchor. Two findings are load-bearing here. First, **the
  age of the data and the choice of issue-tracking system cause a significant
  difference in measured accuracy**: a detector validated on one slice of history
  does not transfer to another, which bears directly on a corpus that grew to
  4,700 vertices in six weeks. Second, on a debiased benchmark **a simpler
  technique outperforms recently proposed sophisticated ones on most projects**,
  and a technique already in industry practice matches a research system.
- **Aggregation of Stack Trace Similarities for Crash Report Deduplication**
  (arXiv 2205.00212, in the graph — same feed) — the crash-dedup half. Rather
  than assigning a report to a group by its single most similar member, it
  aggregates similarities **to the group as a whole, plus timestamp information**,
  and reports large Recall Rate Top-1 gains on real industrial crash data. It
  also reports that a simpler k-nearest-neighbours aggregation is competitive
  with the fuller method.

Positioning: an **instantiation**, not an extension. A rake is a group (problem
text, solution text, the artifacts it names) and candidates arrive with
timestamps, so the aggregation frame transfers directly, and both papers point
the stage-2 adjudicator at the simple end of the design space rather than at a
judge. What the transfer trades away is these fields' evaluation apparatus:
duplicate detection is graded against human-labelled duplicate links in an issue
tracker, and no such ground truth exists for rakes — the nearest equivalent is
Mem2ActBench's hand-confirmation sample (arXiv 2601.19935), which is why a
hand-audited precision estimate has to precede any adjudicator, not follow it.
Data-age bias also forbids validating a detector once and trusting it: it is a
rolling check, the same posture `thalamus eval recipes` takes to recipe freshness.

### 2f. Auditing an unlabelled queue — sampling and the annotator

Building that hand audit (`thalamus eval rake-audit`, stage 0.5) is itself a
measurement design, and both halves have settled answers.

- **Active Sampling for Large-scale Information Retrieval Evaluation** (arXiv
  1709.01709, in the graph — `eval-methodology`, feed `queue-precision-audit`) —
  the anchor for the draw. It separates two failure modes when judgments are
  expensive: fixing a sampling distribution up front carries high **variance**,
  while **active selection** — judging what the system ranks highest — carries a
  **bias toward the systems that contributed to the pool**. Its own contribution
  is a distribution over systems that moves as judgments arrive.
- **Who Annotates in NLP?** (arXiv 2606.02255, same feed) — the anchor for the
  labelling. A task-level audit of 2,667 annotation tasks finds that papers report
  operational detail (recruitment, expertise, volume) but **omit what is needed to
  assess validity** — training, adjudication, and agreement values — worst of all
  in model-evaluation studies, and proposes bare-minimum reporting instead.

Positioning: a **convergence** on the sampling half and an **instantiation** of
the reporting half. The draw is uniform over the specific-key stratum with the
seed fixed before any pair is read, and the worksheet withholds the shared
artifact key — the proximity rule's own evidence — because showing it recreates
active selection inside the annotator rather than inside the sampler. What we do
**not** take is 1709.01709's adaptive half: it varies a distribution over
competing systems and there is exactly one system here, stage 0's proximity rule,
so there is nothing to vary over. On the labelling side a single annotator means
no inter-annotator agreement exists to report at all, which is precisely the
under-documented case 2606.02255 identifies; the substitutes are the rubric
shipping inline with the items, the `unclear` bucket reported in neither
numerator nor denominator (arXiv 2111.03382), and indistinguishable decoy pairs
that bound annotator laxity from above — a decoy can be a genuine recurrence the
artifact key missed, so its hit rate is a ceiling on laxity, never a false-positive
rate. The cost is honesty about resolution: 40 hand judgments separate "mostly
noise" from "mostly real" and cannot rank two detectors.

### 2g. Reproducing a measurement over a corpus that moves

A published number names the graph snapshot it came from (`experiments/snapshots.jsonl`).
It did not name the *trajectory* corpus, and that corpus moves two ways: campaigns
append to `runs.jsonl`, and re-scoring passes rewrote it in place. Measured
2026-08-01: 23 records changed under their own identity on four fields, keeping only a
`restamped_by` marker, and 88 contamination judgements were overwritten and survive in
neither hand-made backup. The pin closing this is lab/038; the literature it rests on:

- **Append-only, hash-chained ledgers.** AuditWeave (arXiv 2607.09682) records
  workflow steps into "a single append-only, hash-chained ledger" in which "any
  modification, reordering, insertion, or deletion of events is detectable through
  chain verification", and **measured** that chain verification flagged every injected
  mutation across four mutation classes over 2,000 randomized trials, at tens of
  microseconds per event. This is the strongest held evidence for the append-plus-
  digest shape.
- **Supersession over in-place update.** ESAA (arXiv 2602.23193) **specifies** a
  deterministic orchestrator that persists events in an append-only log and projects a
  verifiable materialized view, with replay verification by hashing. Cited for its
  specification only: its evidence is two small case studies (9 tasks/49 events; 50
  tasks/86 events) with **no comparison arm against in-place update**, so it is not
  evidence that event sourcing outperforms mutation.
- **The pinning boundary.** Croissant Tasks (arXiv 2605.29786) specifies six
  components — `cr:input`, `cr:output`, `cr:implementation`, `cr:execution`,
  `cr:evaluation`, `cr:subTask` — and shifts the goalpost "from technical replication
  ... to conceptual reproducibility". That licence is what lets implementation detail
  go unpinned; it does not reach a verdict whose *inputs* move, which is why the
  fix-touched path set is pinned rather than re-derived. Its "checklists ... fail to
  scale" line is the argument for a command over a README paragraph, and bounds
  Pineau et al. (JMLR 22(164), 2021), which `experiments/` already renders.
- **Why not a Merkle tree.** Its payoff is logarithmic inclusion and consistency
  proofs to a verifier who does not trust the log operator (RFC 6962 — named as design
  vocabulary from general knowledge, not retrieved in this scan). One operator, no
  adversary, 140 records — and a root hash destroys the per-record diff that separates
  a legitimate append from a rewrite. Revisit if the corpus is ever published or a
  second writer appears.

**This does not transfer from the claim layer.** The 2026-07-31 refusal of bi-temporal
claim identity — `written_at` plus `text_digest` on the four mutable node types — holds
because a Claim is *re-derivable* from its retained Source, so detection suffices where
reconstruction is possible. A trajectory arm is an unrepeatable observation at the
measured $2.25 and 447 s with no upstream to re-derive from, and the proof is local:
`rescored_at` and `restamped_by` stamps *were* present on all 88 and told nobody what
had been overwritten. Detection without retention is not enough where the thing
detected cannot be rebuilt. TOKI's audit-erasure argument (arXiv 2606.06240) is about
LLM-agent persistent memory rather than run corpora, and its verdict matrix ranks the
design it proposes — the transfer to `runs.jsonl` is this project's argument, not
TOKI's finding.

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
- **Proactive memory for long-horizon agents** (arXiv 2607.08716) — the direct
  agent-side ablation of our throttle: selective reminder injection against
  passive bank exposure, **always-on injection**, advisor-only, and general
  retrieval, on Terminal-Bench 2.0 and τ²-Bench. Selective wins, and this is a
  closer citation for the conditioning tier than Self-RAG, which decides
  *retrieval*, not injection. Read honestly, though: the margins over always-on
  are small (τ²-Bench macro-avg 64.3 vs 63.5, always-on better in two of three
  domains) and no token or latency comparison is reported — so the cost half of
  our throttle argument is currently **uncited**.
- **Depth-dependent indirect prompt injection** (arXiv 2605.30686) — the only
  positional measurement of instruction efficacy from the *tool-result* slot:
  60% at depth 1 falling to 0% by depth 4, because models are trained to
  discount instructions arriving in tool output. Adversarial, so the sign is
  inverted for our use, and that is exactly the problem — see §4.
- **STALE** (arXiv 2605.06527) — agents act on superseded memory even when the
  update is retrievable; dominant failure is *implicit conflict*, best frontier
  accuracy 55.2%. The measured reason the Cursor spool prunes an undelivered
  classification rather than carrying it into the next turn ([07](07-harness-integration.md)).
- **Harness-Bench** (arXiv 2605.27922) — harness configuration is a first-order
  effect; capability "should be reported at the model-harness configuration
  level rather than attributed to the base model alone" (106 tasks, 5,194
  trajectories). With **measurement invariance** (Vandenberg & Lance,
  *Organizational Research Methods* 2000) this is why the `harness` split in
  `eval conditioning` prevents pooling but does not license a cross-harness
  comparison: the arms differ *configurally* — indicators missing outright, not
  merely scaled.
- **The Saturation Trap** (arXiv 2606.04296) — intervention timing has no stable
  ground truth: absolute-state triggers fire on 39–83% of actions, LLM judges
  reach F1 0.17–0.40, and three trained annotators agreed on *where* to
  intervene barely above chance (Krippendorff's α = +0.047). Conclusion: build
  for recoverability, not precision timing — which puts Cursor's one-tool-call
  delivery offset inside the construct's noise floor.

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

### 3e. Precomputed summaries — local vs global retrieval over a scope

- **From Local to Global: A Graph RAG Approach to Query-Focused Summarization**
  (arXiv 2404.16130) — questions aimed at *an entire corpus* are query-focused
  summarization tasks, not retrieval tasks, and conventional RAG fails on them.
  The answer is a two-stage offline index: derive an entity knowledge graph, then
  **pregenerate summaries for communities of closely related entities**; at query
  time each relevant community summary yields a partial response and the partials
  are reduced into a final answer. Reported gains are for corpora **in the 1
  million token range**, and the paper's case against prior QFS methods is
  explicitly that they don't scale to that size.
- **RAPTOR** (arXiv 2401.18059) — the same complaint (retrieving short contiguous
  chunks limits holistic understanding) answered by recursively embedding,
  clustering and summarizing text bottom-up into a tree of differing abstraction
  levels, retrieved across levels at inference time. Clusters *text by embedding*
  where GraphRAG clusters *entities by graph structure*.

- **BudgetMem** (arXiv 2602.06025) — the standing objection, and it lands on this
  design directly. It characterizes most existing agent memory systems as relying
  on **offline, query-agnostic memory construction**, which it calls inefficient
  and prone to *discarding query-critical information*, and positions runtime
  utilization as the alternative — while conceding that runtime approaches incur
  substantial overhead and give limited control over the cost trade-off. Its own
  answer is budget-tiered memory modules (Low/Mid/High) behind a router.

- **Sleep-time Compute** (arXiv 2504.13171, in the graph — feed
  `agent-memory-systems`) — the counterweight, and it splits BudgetMem's
  dichotomy. A model processes a context offline *by anticipating likely queries*
  and precomputing against them: roughly **5× less test-time compute for equal
  accuracy** on Stateful GSM-Symbolic and Stateful AIME, up to **13% / 18%**
  accuracy gained when the offline budget is scaled, and **2.5× lower average
  cost per query** when the offline work is amortized across related queries about
  one context (Multi-Query GSM-Symbolic). The load-bearing claim for this section
  is the conditional one: **the predictability of the user query is well
  correlated with the efficacy of sleep-time compute.** The paper also runs a case
  study on a realistic agentic software-engineering task, so the setting is not
  purely mathematical.

**Position: Thalamus takes the local/global *question* and rejects the offline
answer.** The distinction that survives is GraphRAG's opening one — asking how a
whole corpus bears on something is query-focused summarization, not retrieval, and
better matching will not answer it. What Thalamus does not adopt is precomputation,
because BudgetMem's critique applies squarely and the alternative is already built:
an `Exchange` records the question asked and its citation edges record which claims
the answer rested on, so a document's contribution is recoverable at runtime *in
earned terms* — the questions it was actually cited to answer — with no summarization
step and no declared concern vocabulary. That is **query-aware utilization, a
convergence on BudgetMem's stance**, not an instantiation of GraphRAG's index. The
per-document contribution summary considered here is withdrawn: it was the offline,
query-agnostic construction BudgetMem names, and its failure mode (discarded
query-critical material) is silent by construction, which is the worst property a
memory design can have.

**The rejection is conditional, and 2504.13171 states the condition.** Offline and
runtime is not the real axis — *query-agnostic* and *query-anticipating* is.
BudgetMem's critique bites on construction that does not know what will be asked;
sleep-time compute precomputes against anticipated queries and buys 5× on
test-time compute for it, with efficacy tracking **query predictability**. So the
withdrawn contribution layer was rejected for being query-agnostic, not for being
offline, and the door it leaves open is narrow and testable: if a scope's incoming
questions turn out to be predictable — measurable directly from the `Exchange`
records the consultation protocol already writes, since each one stores the
question asked — then precomputation against *those* questions is the cited
design, and its amortization argument (2.5× across related queries about one
context) is exactly the shape of repeated consultations against one scope. Nothing
here is measured locally: no predictability estimate over the exchange corpus
exists yet, and until one does this is a named condition rather than a plan.

**Why the community layer is not taken, stated at the strength the record
supports.** GraphRAG's gains are reported for global sensemaking over corpora in
the **1 million token range**, and its case against prior QFS is that those methods
don't scale that high — so a curated scope of tens of documents does not meet the
condition under which the benefit was demonstrated. That much is cited. The further
step — that a hierarchy therefore buys *less* at this size, because GraphRAG's
justification is itself a scaling argument — is an **inference from the cited
claim's logic, not a measured result**. The `literature` scope holds no node
reporting either method's behavior on small corpora, and no ablation of hierarchy
depth against corpus size. The choice is defensible on conditions-not-met plus the
curation argument; it is not backed by a measurement, and must not be written as
though it were.

**RAPTOR is excluded on a different axis, and more weakly.** Its condition is depth
*within* documents — the headline result is QuALITY, a long-document comprehension
benchmark — not corpus size, so the 1M-token argument does not reach it. A corpus of
tens of substantive papers may satisfy "lengthy documents" better than it satisfies
GraphRAG's scale. The reason to prefer entity structure over embedding clusters is
that curation already encodes the former; that is an argument from what we have, not
a result. Treat RAPTOR as a reason to look again if the contribution layer
underperforms, not as a settled exclusion.

**What of BudgetMem transfers.** The critique does, and it decided the design. The
budget-tiering shape transfers as an idea (tiered depth behind a hand-written policy,
should retrieval cost ever demand it); its measured accuracy-cost frontier does not,
being a property of an RL-trained router on LoCoMo/LongMemEval/HotpotQA. Note the
limit of the convergence: BudgetMem's runtime alternative is a trained routing policy,
where Thalamus's is a graph traversal over records the consultation protocol already
writes. Same stance on *when* to do the work, different mechanism entirely — and ours
is cheap only because the exchange record exists for independent reasons.

**Staleness is the ungrounded half, and it is a coverage gap rather than a demonstrated
absence.** The scope holds nothing on incremental update of a summary hierarchy;
targeted recalls returned no matches. That is a gap in what has been procured, not
proof the field is silent — if the question becomes load-bearing it is a procurement
target under [06](06-ingestion.md), not something more recall can fix. Two adjacent
framings the scope does hold: MemoryBank (arXiv 2305.10250) establishes
significance-and-recency-weighted incremental update in the *memory* literature (a
loose analogy — it says nothing about rebuilding a summary hierarchy), and
Always-OnAgents (arXiv 2606.30306) models persistent state as including provenance and
audit records, which makes a durable brief's staleness a correctness property rather
than merely a freshness one. That survey also documents why the gap exists: the
literature concentrates far more heavily on accumulating and retrieving state than on
governing, recovering or relinquishing it.

**No novelty claim is made here** — the design reduced to using records the system
already writes, which is the opposite of new. Worth noting only because the discarded
alternative (summarizing a document against a *standing* set of concerns) was not
found in the 2026 scan, and being unclaimed is not the same as being right: it was
withdrawn on a cited objection, not on priority. KnowU-Bench (arXiv 2604.08455) is the
nearest neighbor the scope holds, and it points the same way as the decision — a
standing profile is something to *infer* from behavioral logs rather than look up as
static context.

One method-level note for brief authoring: Self-RAG (arXiv 2310.11511) reports
significant gains in **factuality and citation accuracy for long-form generations**
from critique-and-reflect over retrieved passages. A readiness brief is a long-form
generation that must carry citations, so that is the cited precedent for a reflection
pass over a drafted brief.

## 4. What the scan did *not* find claimed elsewhere

Stated narrowly and provisionally — absence in one scan is weak evidence, and this
list is the first thing to re-check on every future scan:

**Contamination and specification gaming: held, and the claim is settled
against us (lab/021–022).** The eval loop measured candidates recovering the
answer from the evaluation environment, by filesystem and by git object store.
The prior art exists, so **arm confinement and leak-channel auditing are not
novel** — they are a local instance of a documented failure mode. SWE-Bench+
(arXiv 2410.06992) finds 32.67% of successful SWE-bench patches carry solution
leakage and 31.08% pass only because their tests are too weak, with the
resolution rate dropping once both are filtered; the SWE-Bench Illusion (arXiv
2506.12286) separates memorised from reasoned fixes, reporting up to 76% accuracy
at naming buggy file paths from the issue text alone; and specification gaming in
reasoning models (arXiv 2502.13295) supplies the vocabulary for an agent that
satisfies a scored objective by hacking its environment rather than solving the
task. Held in `eval-methodology` under feed `eval-leakage`.

**In-deployment measurement: the scan found the field avoiding it.** Consulted
2026-07-27 (exchange `scope:main:exchange:777773c9b77e478d`). Four areas came
back empty and are recorded here as provisional absences: **online/in-deployment
evaluation** of memory or agent systems (no interleaved evaluation, no
off-policy/counterfactual estimation from logged feedback, no production LLM
monitoring); **single-unit experiment designs** (switchback, interrupted time
series, N-of-1, sequential/anytime-valid inference); **reverse-generation of
tasks over real logged history** (all held generation-from-history work runs over
synthesized or simulated material); and **circularity/answer-leakage arising from
shared provenance between task generator and grader**, as distinct from
pretraining contamination or environment leakage. What the corpus *does* show is
an asymmetry worth naming: MemoryBank (arXiv 2305.10250) took its qualitative
claims from real user dialogs and its quantitative ones from LLM-simulated
dialogs, and Mem2ActBench (arXiv 2601.19935) "*simulates* persistent assistant
usage" — **no held work derives a quantitative utility estimate from live
traffic.** Unlike the supply-blocked items below, the single-unit statistics
literature is largely on arXiv and inside the existing allowlist, so this absence
is procurable rather than structural, **and it has now been procured** — five
anchors ingested 2026-07-27 (`campaign-statistics` and `eval-leakage` feeds in
`eval-methodology`, `thalamus` feed in `literature`); the queue is in
[lab/024](../lab/024-the-endpoint-was-in-the-wrong-place.md) §2.6.

Two results from that batch bear on this section directly. **The absence claim
survived contact.** KnowU-Bench (arXiv 2604.08455) describes itself as an
*online* benchmark, which looked like a counterexample — but it instantiates an
LLM-driven user simulator grounded in structured profiles, so it is simulated
interaction, not live traffic. Its transferable contribution is a design
principle rather than a deployment: it hides the user profile and exposes only
behavioral logs, forcing preference *inference* instead of context lookup, and
reports that the bottleneck is preference acquisition rather than task execution.
**And the counter-signal is real and stronger than the scan summary suggested.**
Remembering More, Risking More (arXiv 2605.17830, now held) reports memory-
enabled agents consistently exceeding a NullMemory baseline in violation rate,
with a robust upward trend as accumulated exposure grows, via a trigger-probe
protocol; its order-randomization experiments make this a design constraint for
this project's own campaigns rather than a distant finding. It argues against the
project's prior, it is cited as such, and §5 is where its challenge belongs.

**Attribution evaluation: a structural absence, and the eval loop's layer 1 sits
on top of it.** Consulted 2026-07-29 (exchange
`scope:main:exchange:2e350ddd553a4e04`). The scope held no attribution-evaluation
work at all — no faithfulness/groundedness metrics, no citation or
answer-attribution evaluation, no NLI-based entailment scoring, no
context-attribution methods. That is the literature directly under
`eval/attribution.py`, whose lexical judge was measured at ~4pp of discrimination
over a ~59pp permuted floor (lab/032). **The gap is now closed**, 13 sources
across two feeds, every arXiv ID title-checked by dry run before writing (six
were flagged uncertain by the consult; all six resolved):

- `attribution-eval` (9): ContextCite (2409.00729), TRUE (2204.04991), ALCE
  (2305.14627), AIS (2112.12870), RAGAS (2309.15217), ARES (2311.09476),
  FActScore (2305.14251), AttributedQA (2212.08037), and Lost in the Middle
  (2307.03172) for the position confound in any output-window measurement.
- `causal-attribution` (4): influence functions (Koh & Liang, 1703.04730),
  Datamodels (2202.00622), Doubly Robust Policy Evaluation (1103.4601), and
  Unbiased Offline Evaluation of Contextual-bandit Recommendation (1003.5956) —
  the logged-feedback arm that makes counterfactual estimation possible without
  re-running anything.

**Supply-blocked:** Ojala & Garriga, *Permutation Tests for Studying Classifier
Performance* (JMLR 2010) — the canonical methods citation for the permutation
null itself, no arXiv version.

What the held corpus does establish, and it cuts against the local design: the
two nearest benchmarks both deliberately avoid output-text matching. τ-bench
grades end-state against goal-state, and Mem2ActBench grounds "use" in tool
selection and parameter grounding rather than in what the text echoes. STALE
names the gap being measured here outright — *"a pervasive gap between retrieving
updated evidence and acting on it."* And the causal half is **not** as closed as
it looks: Joachims' propensity-weighted estimation (arXiv 1608.04468, already
held under `recall-ranking`) recovers counterfactual estimates from logs without
re-running anything, explicitly including settings where queries never repeat —
conditional on a *stochastic* logging policy, which retrieval here is not.

**Classical IR ranking: a structural absence, and it recurs on every ranking
change.** Consulted 2026-07-29 (exchange `scope:main:exchange:837783bc60cb467b`)
on whether lexical `recall()` should carry a project-match prior. The scope held
nothing on learning-to-rank, query-independent static rank features,
personalized or contextual search, click-model and presentation bias, or result
diversification — the corpus holds agent-memory and RAG work, but not the IR
ranking literature those systems sit on top of. The nearest held precedent for a
query-independent prior modulating a memory score is MemoryBank's Ebbinghaus
time-elapsed × significance term (arXiv 2305.10250), which is a mechanism
description, not an ablation: no held work reports a precision delta for a prior
against no-prior. Two anchors are now procured under feed `recall-ranking`:
**Unbiased Learning-to-Rank with Biased Feedback** (arXiv 1608.04468), which
supplies propensity-weighted estimation and the reason a ranker cannot be fit to
logs it generated itself; and **Degenerate Feedback Loops in Recommender
Systems** (arXiv 1902.10730), which separates echo-chamber from filter-bubble
degeneration and is the direct hazard for a single-operator system with no
control population. The rest is supply-blocked in the same way as Wohlin below —
MMR (SIGIR 1998), IA-Select (WSDM 2009), α-nDCG (SIGIR 2008), Richardson's
*Beyond PageRank* (WWW 2006), Teevan's *Potential for Personalization* (TOCHI
2010) — so diversification sizing in particular remains ungrounded.

**Multi-agent coordination: four absences, now procured, and the corpus argues
against the local instinct.** Consulted 2026-08-07 (exchanges
`scope:main:exchange:a42d7d6316f54be4`, 47 citations, and
`scope:main:exchange:fca6fdf82b0d42f0`, 57). The scope held no classical DAI, no
multi-agent failure taxonomy, no agent-messaging protocol specifications, and
nothing on iterated-summarization degradation — so item 4's novelty position rested
on shelves nobody had read. Twelve sources procured under feed `thalamus`: Contract
Net (Smith 1980), Hearsay-II (Erman et al. 1980) and BB1 (Hayes-Roth 1984)
hand-fed; MAST (2503.13657), AgentCollabBench (2605.08647), GoAgent (2603.19677),
the equal-token-budget single-agent result (2604.02460), small-agents-collaborate
(2601.11327), *Broken Telephone* (ACL 2025, 2502.20258), *Faithful, Not Corrective*
(2607.09678), the MCP-vs-A2A comparative study (2607.23884) and AIP (2603.24775)
on-allowlist.

Three findings bear on this project's own design rather than on the question that
procured them, and each is better-provenanced than the position it challenges.
**(a) Multi-agent gains may be a compute artifact**: single-agent matches or beats
multi-agent on multi-hop reasoning at equal thinking-token budgets, with a Data
Processing Inequality argument that a single agent is strictly more
information-efficient under a fixed budget, and MAS becoming competitive only when
single-agent context utilisation degrades *or more compute is spent* — so any
multi-agent win here is unattributable until the single-agent control is run at the
multi-agent total budget. That control has never been run. **(b) Restricted
communication is the winning configuration**: an orchestrator plus specialised
sub-agents under *limited* communication wins, orchestrator reasoning carries
nearly all the gain, and sub-agent reasoning is limited or negative. **(c) High
relay fidelity is not a safety property**: a strong relay is reported near-lossless
over six hops, which weakens the *fidelity* case for receiver-assembled briefs at
frontier capability — but the same testbed reports an injected wrong value
persisting to the final hop in 83–100% of chains in every message format, matching
the true value's retention. Structure buys a faithful, error-*localizing* channel,
not an error-correcting one, and localizing needs a record to localize in. Two
provenance cautions: (c)'s source is a single-author unvenued preprint, while the
peer-reviewed result in the same area (ACL 2025) finds distortion accumulating with
chain complexity — the stratification runs the wrong way for optimism; and the
durable-record argument is unsupported in *both* directions, since nothing held
identifies unrecorded communication as a leading failure driver either.

What the corpus does support is group-as-atomic-unit topology with a compressed
inter-group channel (GoAgent measures ~17% fewer tokens at 93.84% average accuracy,
warranted on redundancy and noise, **not** on safety), and topology explaining
7–40% of variance in whether constraints survive multi-hop transfer
(AgentCollabBench). Pinned scopes plus the ticket already instantiate that shape.
**Genuinely unaddressed in the held corpus: provenance across a *group* answer** —
what a citation means when the answering unit spans scopes. Adjacent work
(PROV-AGENT, the evidence-tracing survey, AIP's per-delegation completion records)
treats provenance per agent or per delegation, never per group. If any part of this
line is pursued, that is where the research question is.

**Still open, and blocked on supply rather than on scanning.** Wohlin's
threats-to-validity taxonomy, whose construct / internal / external vocabulary
§2a and §2d improvise; and, load-bearing for the campaign statistics,
ordinal-as-interval by name (Liddell & Kruschke 2018), intention-to-treat vs
per-protocol (Hernán & Robins 2017 / ICH E9(R1)), and sample-size methods for
ordered categorical outcomes (Whitehead 1993). None has an arXiv version — they
sit on SSRN, NEJM, Statistics in Medicine and in a Springer volume, all outside
the ingest allowlist — so procuring them is an allowlist or local-file decision,
not a scan.

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
   2606.04329. **The claim narrows now that the classical DAI shelf is held**
   (feed `thalamus`, ingested 2026-08-07). Contract Net (Smith 1980) already couples
   the two halves this claim rests on: an award both records the manager–contractor
   agreement and confers the task, and its announcement / bid / award cycle is the
   delegation shape a consultation ticket instantiates. What it does not do is make
   the record *memory* — the contract coordinates execution, is not retained as
   citable knowledge, and has no analogue of a citation-validated close. Hearsay-II
   (Erman et al. 1980) is the opposite pole and equally prior: knowledge sources
   communicate solely through a shared blackboard, with no per-exchange record at
   all. So what survives is narrow — the coupling used as a *memory-formation*
   mechanism between agent scopes — and it now rests on a shelf that has been read
   rather than one that was never scanned. Adjudicating the remainder properly wants
   a consultation against the newly held sources, not this paragraph. Provisional,
   like everything on this list.
   The blackboard *control* layer is held through Hayes-Roth's BB1 technical report
   (Stanford CS-TR-84-1034, hand-fed), which bears on the recording question
   directly and against the unrecorded-deliberation instinct: BB1 makes control
   decisions themselves entries on a control blackboard, and what that buys is
   explanation (an action is explained by the rules, ratings and competing actions
   that produced it) and learning (control heuristics generated in-session become
   knowledge sources for the next). **Supply-blocked:** the same author's *A
   Blackboard Architecture for Control* (AIJ 1985) — closed access, confirmed
   against Unpaywall, OpenAlex and Semantic Scholar, and absent from the Stanford
   CS technical-report series, so no institutional copy exists to find. It appears
   in BB1's own bibliography as reference [6]; that line is the one conflation
   vector in the hand-fed file and the two must not be merged.
5. **Refuted, and recorded as such: a normalized agent-trace intermediate is
   published prior work.** The Cursor transcript adapter (lab/028) would have been
   a natural place to claim novelty for "one intermediate, many harness dialects".
   It is not novel. HarnessFix's harness-aware Trace Intermediate Representation
   normalizes trajectory evidence across harnesses (arXiv 2606.06324, in the graph
   under feed `thalamus`), and the Agent Data Protocol is explicitly an interlingua
   over thirteen agent datasets in incompatible formats (arXiv 2510.24702, same
   feed). Both measure gains on their own downstream tasks (HarnessFix +6.3–18.4%
   across four benchmarks; ADP ~+20% average SFT gain) and **neither measures IR
   fidelity**, so they are cited for the pattern, never for the schema. Thalamus's
   adapter is an instantiation. Recorded here because this list is only worth
   keeping if entries can leave it.
6. **Harness-instrumentation gaps** (2026-07-29 scan, for the Cursor port —
   [07](07-harness-integration.md), lab/027). These are **engineering gaps, not
   research novelty**: the mechanisms are visible in shipped products (LangChain
   middleware, Claude Code system reminders), just unstudied.
   - No paper, survey or taxonomy distinguishes a context's **computation point**
     from its **delivery point** within an agent loop. Every candidate term
     collides with an occupied one: "out-of-band context" belongs to prompt-
     injection security, "delayed feedback" to RL credit assignment. Nearest
     ancestors: *asynchronous reflection* (arXiv 2502.11882) and *anticipating*
     as a context primitive (arXiv 2607.21503, single-author preprint).
   - **No measured comparison of *benign* instruction uptake by injection slot**
     (system prompt vs user turn vs tool-result slot). All positional evidence is
     adversarial (2605.30686), where resistance is the desired outcome and the
     sign flips for this use. This is the gap that most directly limits what the
     Cursor arm can claim, and it is measurable in-house.
   - No formalization or evaluation of **agent middleware / interceptors** as a
     construct; it exists only in framework documentation.
   - No empirical study of **instrumentation portability across agent harnesses
     with unequal event surfaces**, nor of cross-framework agent-trace
     comparability. Nearest analogue is the Manifest V2→V3 developer study (arXiv
     2507.13926), where reduced scope was sometimes the honest outcome — which is
     what lab/010 concluded for distillation.
   - **Measurement invariance has never been ported from psychometrics to
     software instrumentation.** Importing it (§3c) is defensible and not found.
   - OpenTelemetry's GenAI semantic conventions define **no conditional or
     degraded conformance**: a span a harness cannot emit is simply absent, with
     nothing marking the absence as structural rather than incidental.
7. **Cross-format transcript gaps** (2026-07-29 scan, for the Cursor transcript
   adapter — [05](05-trust-model.md), [07](07-harness-integration.md), lab/028):
   - **A per-record manifest of what a source format could not carry.** The theory
     exists (information-capacity dominance, Miller, Ioannidis & Ramakrishnan,
     VLDB 1993; recovery/quasi-inverse, Fagin 2007) and argues for a *static
     per-format capability table* over a per-record one, which is what
     `ingress_verifiable` is. The in-band mechanism exists only in the mirror
     direction — declaring what a *consumer* may ignore (ISO/IEC 29500-3 MCE,
     SOAP `mustUnderstand`) — and the reason vocabulary exists without the
     manifest (FHIR `dataAbsentReason`). The synthesis was not found. Worth
     knowing before building one: HL7 defined a serialization-scoped null flavor
     (`NP`) and retired it.
   - **A named discipline for shipping a parser against documentation alone**, with
     no sample and no live system to test against. LangSec names the *hazard* —
     antipattern (e), "Incomplete Protocol Specification", including specs that may
     not exist — but names no survival practice. Every technique that sounds
     applicable requires something we lack: grammar inference (Mimid, ESEC/FSE
     2020; AUTOGRAM, ASE 2016) needs the implementation; schema inference (Baazizi
     et al., EDBT 2017) needs a document corpus; differential testing needs two
     systems. Consumer-driven contract testing scopes itself to providers you can
     influence. Nearest fit is bi-directional contract testing, a vendor pattern
     whose own stated objection is that it verifies you against the documentation —
     the thing already not trusted.
   - **Any measurement of extraction quality as a function of *which trace fields*
     are present.** Every held ablation varies observation modality, token volume
     or storage representation, never field structure: verbatim beats extracted
     artifacts by 15.9–22.0 pp (arXiv 2601.00821, *single-author unrefereed
     preprint* — cite with that caveat), observation masking matches LLM
     summarization at half the cost (arXiv 2508.21433), judge quality is
     *non-monotonic* in fidelity (arXiv 2504.08942), and structure beats volume
     (arXiv 2510.02837). This one is cheap to close in-house and is now an open
     thread: re-run the existing extractor over archived Claude Code transcripts
     with `tool_use_id` linkage stripped, and diff the claims. We hold the corpus.

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
- **No ground truth for rake recurrence** (§2e). The duplicate-detection
  literature is held, but its evaluation apparatus does not transfer: those fields
  grade against human-labelled duplicate links, and nothing labels a rake
  encounter. A hand-audited precision estimate on the candidate queue is the
  substitute; the instrument now exists and is grounded (§2f), but the sample is
  **drawn and unlabelled**. Until it is labelled the queue's precision is unknown
  and no adjudicator should be built on it. Recall stays unknown even afterwards —
  the audit prices the pairs the rule emits, never the encounters it never keyed.
- **Observational causal inference is anchored but not applied.** lab/024 §2.4
  procured the randomized anchors (switchback 2009.00148, anytime-valid N-of-1
  2309.07353) and DDD-ITSA (arXiv 2603.17281, in the graph — `eval-methodology`,
  feed `campaign-statistics`) now anchors the quasi-experimental half: interrupted
  time series with a **second control group**, because two-group comparisons stay
  confounded by concurrent interventions. Layer 2b has no control series at all —
  every real session ran with memory on — so its recurrence trend is descriptive
  until one is constructed. A recurrence dashboard without that is an unlabelled
  causal claim.
- **Attribution beyond lexical** — the survey (2603.07670) and the benchmarks make
  the case that inferred-intent retrieval is the hard part; our used-vs-ignored
  attribution is lexical (lab/002). This is the honest weak point of the eval loop.
- **Invalidation semantics are undecided, and one neighbour decided them
  differently** (§6). Claim identity is latest-wins: a revised claim updates the
  node (decision log 2026-07-15), so a superseded belief leaves no trace except on
  the `Source` lineage. Zep's Graphiti keeps historical relationships instead. The
  corpus now holds the mechanics (§6) and the accuracy case for the change is
  **thin**: TOKI's audit-row defence moves LoCoMo accuracy by 0.86 points and its
  cross-system comparison is self-reported as underpowered (arXiv 2606.06240).
  What is not thin is the *detection* argument — retention without stored
  supersession collapses 0.99 → 0.33, indistinguishable from naive RAG
  (2606.26511) — and that lands on the queryability side of the line, where §6's
  Mem0 entry already concedes benchmark accuracy is the wrong yardstick. The
  remaining unknown is as-of-time query utility on a real operator workload,
  which no held source measures.
- **No abstention rung.** LongMemEval (arXiv 2410.10813) counts **abstention**
  among the five core long-term-memory abilities it evaluates — knowing that the
  history does not contain the answer. The graded ladder has no equivalent: every
  rung grades what a candidate *did*, and a task whose correct outcome is "the
  memory does not support this" is not in the battery. Cheap to add and currently
  absent.

## 6. The deployed neighbours — systems, not papers

§1–§3 argue position against *papers*, each doing one pillar. This section is the
other comparison: four shipped or productized memory systems that integrate
several pillars at once. The point of the section is admission — where Thalamus
duplicates a system that already exists, it says so, and the deviation has to be
argued rather than assumed. Held under feed `agent-memory-systems`.

### Zep / Graphiti (arXiv 2501.13956)

**What it solves.** A memory-layer *service* built on Graphiti, a
temporally-aware knowledge graph engine that synthesizes unstructured
conversational data together with structured business data while maintaining
historical relationships. Its case against the RAG baseline is that existing
retrieval-augmented frameworks for LLM agents are limited to **static document
retrieval**, where the applications it targets need dynamic knowledge integration
from ongoing conversations and business data. Reported: **94.8% vs MemGPT's 93.4%**
on Deep Memory Retrieval, up to **18.5%** accuracy improvement with **90%** lower
response latency on LongMemEval, gains most pronounced on cross-session
information synthesis and long-term context maintenance.

**What Thalamus duplicates.** Close to the whole architectural shape: an
entity-linked, temporally-ordered graph over agent conversation, queried at
runtime, replacing chunk retrieval. Graph-structured agent memory is a shipped
product, and nothing in this repo may be described as if it were first at it.

**Where the deviation is defensible.** Zep's held claims are entirely about
retrieval accuracy and latency for a hosted service. They say nothing about a
trust boundary on the write path, about tiering by origin, or about measuring
whether retrieved memory changed what an agent did — which is where every pillar
of this project lives (§1, §2). The deviation is not "a better graph"; it is a
perimeter around one, for a single operator, on local hardware.

**Where it is not defensible yet.** Invalidation. Thalamus's claim identity is
latest-wins; Graphiti carries a **bi-temporal** model over two timelines — `T`,
chronological event ordering, and `T'`, the transactional order of ingestion —
with four timestamps per edge (`t'_created`/`t'_expired` on `T'`,
`t_valid`/`t_invalid` on `T`). Invalidation is LLM-driven: new edges are compared
against semantically related existing ones for contradictions, and an invalidated
edge's `t_invalid` is set to the `t_valid` of the edge that displaced it, new
information always winning. Two consequences for this repo. First, the two
timelines are **separate axes**, so a "when did this text last change" stamp and
edge invalidation are complementary rather than competing designs — TSM recovers
12.2 accuracy points on LongMemEval/LoCoMo purely by not collapsing them
(2606.06240). Second, Graphiti's LLM-per-edge mechanism is not the only option
and is measurably not the best one: MemStrata's deterministic
`(subject, relation, object)` supersession uses no similarity threshold and no
LLM call, while similarity-plus-judge gating leaks stale facts 25–60% of the time,
worse than naive RAG in the abstention regime (2606.26511). Anything built here
should copy the bi-temporal *shape*, not the adjudication mechanism.

### Mem0 (arXiv 2504.19413)

**What it solves.** A memory-centric architecture that dynamically extracts,
consolidates and retrieves salient information from ongoing multi-session
conversations against the fixed context window; `Mem0g` adds graph-based memory
representations for relational structure. Reported on LOCOMO against six baseline
categories: consistent wins across single-hop, temporal, multi-hop and open-domain
questions, **26%** relative improvement in LLM-as-a-Judge over OpenAI's memory
system, and against full-context processing **91% lower p95 latency** with **over
90%** token-cost saving.

**What Thalamus duplicates.** Extraction-and-consolidation on the write path
(`thalamus extract`) and the cost argument for not carrying whole histories.

**The datum that cuts against the graph-first bet.** `Mem0g` scores about **2%**
above flat `Mem0` overall. Graph structure is nearly free of benefit on that
benchmark's terms, and docs/06's "graph-first is the point" cannot be defended by
conversational-QA accuracy — it has to be defended by the questions LOCOMO does
not ask: provenance walks, consultation audits, per-feed attribution, contradiction
queues. Those are traversals, and a flat store answers none of them. That is the
honest form of the argument; "graphs retrieve better" is not available.

**Where the deviation is defensible.** Mem0's numbers are efficiency claims
against a full-context baseline. `thalamus eval cost` (§2b) does not compete
there — it attributes cost per session and per expert rather than reducing it, and
the project makes no accuracy-per-token claim at all.

### Letta / MemGPT (arXiv 2310.08560)

**What it solves.** Virtual context management: hierarchical memory tiers borrowed
from operating systems, paging data between fast and slow tiers so a limited
context window presents as a large one, with interrupts managing control flow.
Evaluated on document analysis far beyond the underlying context window and on
multi-session chat where agents remember and evolve across long interactions.

**What Thalamus duplicates — and a naming collision worth stating.** Both systems
say "tiers" and mean unrelated things. MemGPT's tiers are **capacity** tiers (what
fits in context now); docs/05's are **trust** tiers (what a node's origin
licenses). Nothing transfers between them.

**Where the deviation is defensible, and this is the sharpest one.** MemGPT's
memory is **self-edited**: the agent decides what to page in and what to write
back. That is precisely the write path docs/05 gates, and the poisoning literature
in §1 is the attack surface it opens — 2606.04329's finding that defenses must
operate at the write path rather than the input boundary is a statement about
architectures of exactly this shape. So docs/05's write-path argument now argues
against a named, widely-deployed system instead of against nobody. Stated
precisely: **no held claim about MemGPT describes any provenance, origin tier or
trust boundary on its self-edited memory** — that is an absence in what the paper
claims, not a demonstrated vulnerability in the product.

**Supply note.** The corpus holds **no** source on Letta, MemGPT's productization.
Anything said here is about the paper; product-level claims about Letta are
ungrounded and are not made.

### LangMem — not held

The scope holds nothing on LangMem. It has no paper; it is framework
documentation, which makes this a **supply gap, not a scan gap** — and a closable
one, since `github.com` is on the literature manifest's allowlist, so its
repository and docs are fetchable under [06](06-ingestion.md) whenever a question
actually turns on it. Until then this doc makes no claim about it, including no
claim that Thalamus differs from it.

### The shared yardstick: LongMemEval (arXiv 2410.10813)

Both Zep and the systems it benchmarks against report here, which is why it is
held alongside them. It is 500 curated questions embedded in scalable
user-assistant chat histories, evaluating five abilities — information extraction,
multi-session reasoning, temporal reasoning, knowledge updates, and **abstention**
— and it measures a **30% accuracy drop** for commercial chat assistants and
long-context LLMs asked to retain information across sustained interaction. Its
other contribution is a decomposition of long-term memory design into **indexing,
retrieval and reading**, with optimizations at each: session decomposition for
value granularity, fact-augmented key expansion for indexing, time-aware query
expansion for retrieval, together substantially improving both recall and
downstream QA.

**Why it is not adopted as a target.** It grades chat assistants on curated
questions over synthesized histories; §2's whole position is that the live loop
measures the operator's real sessions instead. What it does supply is two things
the local design lacks: the abstention ability (§5) and a stage vocabulary —
indexing / retrieval / reading — that names where the graded ladder's instruments
sit, since `eval/attribution.py` grades *reading* while lexical `recall()` is
*retrieval*, and lab/032's measured floor is a reading-stage result.

### What none of them does

**The §4 in-deployment absence survives contact with this batch.** All four
systems are graded on offline benchmarks — DMR, LOCOMO, LongMemEval — against
curated or synthesized histories. No held claim from any of them derives a
utility estimate from live traffic, including Mem0's, whose latency and cost
figures are measured on the LOCOMO comparison despite the paper's
production-readiness framing. §4's provisional absence is therefore unchanged by
the arrival of the systems most likely to have refuted it.

## 7. Activation-level harness instrumentation

A harness that runs its own local model can read the model's internal state, not
just its tokens. This section holds that literature because it bears on the eval
loop directly: the best-evidenced use of activation access is **predicting that a
trajectory is going badly, early enough to stop paying for it** — which is the
same quantity §2b prices and §2 grades after the fact. Held under feed
`activation-instrumentation`.

The section exists mostly to say what *not* to build. Three of the five families
below are negative results.

### 7a. The access mechanism — the serving stack is the decision

The primitive is `nn.Module.register_forward_hook` / `register_forward_pre_hook`.
On a HF decoder model a pre-hook on `model.model.layers[i]` yields the residual
stream in; the forward hook's `output[0]` (a tuple, not a tensor) yields it out;
`resid_mid` is reachable only as the input to `post_attention_layernorm`. Wrappers
exist and are maintained — **TransformerLens 3.x** (v3.6.0, 2026-07-28; v3
deprecates `HookedTransformer.from_pretrained` for `TransformerBridge`, which
matches HF numerics where legacy `HookedTransformer` never did), **nnsight 0.6**
(2026-02-26; the only option with a real gradient story), **baukit `TraceDict`**
(unmaintained, ~30 lines of dependency, still correct).

Access and optimized serving are in direct tension, and the choice of serving
stack determines what is possible:

| Stack | Access | Cost |
| --- | --- | --- |
| HF `transformers` + hooks | anything at a module boundary | ~1/8–1/24 vLLM throughput |
| vLLM + `vllm-lens` (UK AISI, MIT, 2026-04-23) | residual stream + steering, per-request via `SamplingParams.extra_args` | ~20% slower than bare vLLM; forces `enforce_eager=True` |
| vLLM native `extract_hidden_states` | chosen layers → safetensors on disk | offline collection only |
| llama.cpp `cb_eval` | every ggml graph node — the most complete access of any serving stack | C-side filtering mandatory |
| SGLang | last layer only (#8069 closed inactive) | — |
| MLX | no hook API; monkeypatch `model.layers` | — |
| Ollama | **none** | — |

Implementation facts that decide designs rather than decorate them:

- **Hooks fire once per token during decode.** Prefill gives `(b, n_prompt, d)`,
  each decode step `(b, 1, d)`. A `.cpu()` sync inside the hook serializes the
  decode loop.
- **`torch.compile` and CUDA graphs silently drop hooks.** Hooks registered after
  first compilation never run (pytorch#117758); a replayed CUDA graph does not
  re-enter Python. Every serving-side solution either forces eager mode or does
  something exotic (DMI-Lib, arXiv 2605.11093, claims hooks surviving CUDA graphs
  at 0.4–6.8% overhead — research preview, unreplicated).
- **Attention patterns require `attn_implementation="eager"`.** SDPA and
  FlashAttention never materialize the matrix. A memory cliff, not a flag flip.
- **Continuous batching scrambles positions** — the tensor at a hook is a
  flattened concat over in-flight sequences (vllm#36998, still open, no
  implementation; its own estimate for observing *decode* is ~25% throughput loss).
- **`vllm-lens` ships hooks as cloudpickle over HTTP** — remote code execution by
  design. Localhost or tailnet only.
- **Numerics do not match across stacks.** A probe trained on `transformers`
  activations may not transfer to vLLM's kernels. Train on the stack you deploy on.

Remote access: **NDIF** (nnsight `remote=True`, NSF-funded, Llama-3.1-8B/70B/405B)
is the only real public option. **Goodfire Ember's public API was deprecated in
February 2026**; Ember now names a partner-only platform. No frontier-lab API
exposes activations, which is why this section is scoped to open weights.

### 7b. Attention maps and saliency — do not build on these

The intuitive mechanism is the discredited one.

- **Attention as explanation** is a settled negative: Jain & Wallace (1902.10186,
  NAACL 2019) show attention uncorrelated with leave-one-out importance and
  adversarial attention distributions yielding equivalent predictions; Serrano &
  Smith (1906.03731) find it a noisy predictor even of intermediate-component
  importance; Wiegreffe & Pinter (1908.04626) narrow rather than overturn this.
  Bastings & Filippova (2010.05607) reframe: the unstated goal is input-token
  relevance and attention is used only because it is a ready-made per-token weight.
- **The saliency alternative is worse.** Adebayo et al. (1810.03292, NeurIPS 2018)
  show Guided BackProp and Guided GradCAM produce visually unchanged maps as the
  network's weights are randomized. ROAR (1806.10758, NeurIPS 2019) finds base
  saliency estimators rank features **worse than random** under retrain-and-remove.
  Kindermans et al. (1711.00867) trace failures to arbitrary reference points.
  Gradient saliency also needs a backward pass, which no fast serving stack exposes.
- **Scope caveat, stated honestly:** nearly all of this is encoder LSTMs and BERT
  doing classification. Decoder-only re-derivations are 2026 preprints, and the
  old erasure protocol does not port cleanly (Kamahi & Yaghoobzadeh, 2408.11252 —
  erasure creates OOD inputs for next-token-trained models).

Two survivable uses remain, both distinct from explanation: attention patterns as
a *detector* inside causal circuit work (Olsson et al. 2209.11895 uses them for
prefix-matching, with the copying half an OV/weights claim; the modern pipeline is
activation patching — ACDC 2304.14997, AtP\* 2403.00745), and attention as a
*feature for a trained classifier* (Attention Tracker, NAACL Findings 2025, +10.0
AUROC on prompt-injection detection). The distinction between "attention as
signal" and "attention as explanation" is the whole content of this subsection.

### 7c. Linear probes on the residual stream — where the evidence is

Foundation: Alain & Bengio (1610.01644, 2016). The agentic results are recent and
directly on the eval loop's questions:

- **Trajectory abort.** Probes predict agent task failure from the first
  interaction round; a recall-controlled abort cascade saves **60.2% of tokens on
  TextCraft and 54.9% on WebShop at 90% recall** (2607.06503, 3 models × 2 envs ×
  4 variants). Behaviour-only monitoring is consistently weaker, and adding
  behavioural features to hidden-state probes gives **no further gain**.
- **Tool gating.** Tool *necessity* is linearly decodable from the pre-generation
  representation at **AUROC 0.89–0.96** across six models; 48% fewer tool calls at
  1.7% accuracy loss, and the hidden-state signal substantially outperforms the
  model's own verbalized reasoning about whether it needs the tool (2605.09252).
- **Coding agents.** Logistic probes on the residual stream decode whether current
  code parses and passes tests at **AUC up to 0.83**, predicting the outcome of
  edits **~25 steps before they are written**, transferring SWE-bench Verified →
  Pro without retraining (2607.05188).
- **Hallucination pre-emission.** DRIFT reads inter-layer hidden-state transitions
  at <0.1% overhead, fully parallel with generation, SOTA AUROC on 10/12 settings
  (2601.14210).
- **Production cost.** The user-facing Gemini misuse monitor is a probe: 2.64%
  weighted test error vs Gemini 2.5 Flash's 2.04% at **>10,000× lower cost**,
  trained on **3,175 samples** (2601.11516). Probe latency is <1% overhead — the
  forward pass is already paid for.

The constraints are as important as the results, and they are the reason this
section is not a green light:

- **Probes read the situation, not the action.** A direction separating fine-tuned
  from base at **AUC 1.000** fired on **0 of 143** audited pre-assistant-turn
  contexts and 0 of 342 prefill rows (2606.30449), while decoding *prompt domain*
  at 0.999. "Is this trajectory in a region where the model tends to fail" works;
  "is the model about to take this specific bad action" has no evidence.
- **In-distribution AUROC is nearly worthless as evidence.** Filtering surface
  textual cues drops probe AUROC 10–30 points — sandbagging **0.94 → 0.57**, which
  is chance (2509.21344). PARALLAX (2605.17028) evaluated 22 hallucination
  detectors across 12 models and found four of six standard corpora embed the
  ground-truth answer in the prompt; under controlled conditions most established
  baselines perform near chance, and only two supervised hidden-state probes
  survived. This is §2's answer-key-leak problem in a new venue, and it lands on a
  scope that has already found one such leak by hand (the git-object-store channel,
  9/88 arms).
- **Truthfulness is not universal.** Orgad et al. (2410.02707, ICLR 2025) — the
  paper that establishes exact-answer-token concentration — also finds detectors
  fail to generalize across datasets, and off-skill are **no better than
  logit-based uncertainty**. Cheang et al. (2510.09033) argue hidden states encode
  *recall status* rather than truth.
- **Probes are adversarially fragile.** Obfuscated activations drop harmfulness
  probe recall **100% → 0%** at a retained 90% jailbreak rate (2412.09565).
  RL-Obfuscation (2506.14261) evades token-level monitors but finds **max-pooling
  and attention-based probes remain robust** — which is a concrete architecture
  constraint: pool, do not read the last token.
- **CCS is refuted.** Burns et al.'s unsupervised knowledge discovery
  (2212.03827) is proven to find whatever feature is most prominent, not knowledge
  (2312.10029). Do not build on it.

### 7d. The logits-only baseline that must be beaten first

- **G-NLL** — negative log-likelihood of the single greedy sequence, one forward
  pass, no hooks — wins or ties on 9 of 10 BFCL splits and beats 10-sample
  semantic entropy everywhere on function-calling (2604.22985, AUROC 0.76–0.78 vs
  0.72–0.74). **Semantic entropy does not replicate on structured output**: the
  distribution is so peaked that meaningful uncertainty lives in fewer than 5
  tokens and the runner-up is usually syntactically equivalent (`=["` vs `=['`),
  so all samples land in one cluster and SE reads ~0 on wrong calls. Restricting
  G-NLL to semantically meaningful tokens takes it to 0.78 and cuts smoothECE
  0.147 → 0.091.
- **Semantic entropy** (Farquhar et al., Nature 630:625–630, 2024) is validated on
  free-form factual assertions, averaging 0.790 AUROC vs naive entropy's 0.691 —
  but the underlying ICLR paper's margins are much smaller (0.828 vs 0.802 on
  TriviaQA; 0.675 vs 0.673 under exact match), and it targets *confabulations*,
  not systematic wrongness. A model that consistently misunderstands an API is
  confidently, repeatably, undetectably wrong by this instrument.
- **Aggregated trajectory logprobs do not work.** τ²-bench trajectory uncertainty
  predicting task failure: AUROC 0.597 / 0.624 / 0.469 / 0.645 across four
  model×domain cells, at or below chance (2602.05073, ACL 2026). This is the
  cleanest argument for activations over logits at the trajectory level — the same
  task where probes deliver 60% token savings.
- **Per-token entropy localizes decision points.** CoT entropy is bimodal; a
  high-entropy minority of "forking tokens" decides the trajectory, and the effect
  is causal (2506.01939, NeurIPS 2025). Gate there, not uniformly.
- **Calibration.** RLHF degrades ECE 0.007 → 0.074 (GPT-4 tech report Fig. 8), and
  a single fitted global temperature largely recovers it (2207.05221 §3.3).
  Verbalized confidence clusters at 80–100% in multiples of 5 — a rank signal,
  never a probability (2306.13063).
- **A methodological landmine that applies to our own eval loop.** The approximate
  correctness function used to label answers right/wrong changes the *ranking* of
  UQ methods (2510.02279). No AUROC in this literature is readable without it, and
  the same hazard applies to the judge in §2d.
- **Proxy logprobs are closed.** LLaMA-30B judging GPT-3 gives passage-level
  Pearson **−22.83** — anticorrelated (SelfCheckGPT, 2303.08896). If the acting
  model's logprobs are unavailable, use consistency sampling or a judge, never a
  proxy's probabilities.

### 7e. Sparse autoencoders and steering — held, and declined

Both families are procured so the decision is cited rather than assumed.

**SAEs: the 2024 optimism did not survive 2025–26.** Bricken et al. (Transformer
Circuits, Oct 2023, never peer-reviewed), Templeton et al. (Scaling
Monosemanticity, 2024), Gao et al. (2406.04093), Gemma Scope (BlackboxNLP 2024,
400+ SAEs, >20% of GPT-3's training compute). Against them: SAE probes
**underperform logistic regression on average** across data scarcity, class
imbalance, label noise, and covariate shift (2502.16681, ICML 2025); SAEBench
(2503.09532, 200+ SAEs, 8 architectures) finds gains on sparsity/reconstruction
proxies **do not translate downstream** — the entire 2024 architecture race
optimized a metric that does not predict utility; feature absorption is a
structural consequence of the sparsity objective, not a tuning bug (2409.14507);
SAEs do not find canonical units (2502.04878 — an "Einstein" latent decomposes
into "scientist" + "Germany" + "famous person"). Revealed preference is the
cleanest evidence: the team that built Gemma Scope shipped the production Gemini
monitor on activation probes.

Numbers in this literature need checking before they are quoted. A citation audit
run for this section found: Templeton's "34M features" SAE has **~12M alive** (65%
dead, in the paper); Gated SAEs' "half as many firing features" appears **only in
the abstract**, against a compute-matched baseline with 50% more latents, with the
interpretability study at **p = .060** — parity, not superiority; Gao et al.
explicitly **repudiate** the "% of loss recovered" metric others report as theirs;
and Cunningham et al. is ICLR 2024 with **Huben listed first**. The narrow honest
counterexamples are Goodfire/Rakuten's production PII detection under
synthetic→real shift (vendor blog, unreplicated) and OpenAI's 2504.20271, which
recommends prompted probing and finds SAEs ahead only in the compute-constrained
corner.

**Steering is a control tool, not a sensing tool**, so it gates nothing: ActAdd
(2308.10248), CAA (ACL 2024, 2312.06681), RepE (2310.01405), ITI (2306.03341,
Alpaca TruthfulQA 32.5% → 65.1%), function/task vectors (2310.15213, 2310.15916).
The disqualifying measurement is that **~1/3 of samples move the wrong way**
(2505.22637; see also 2407.12404 — steerability is largely a *dataset* property,
not a model property, and a significant fraction of inputs are anti-steerable),
plus non-identifiability: orthogonal steering vectors achieve comparable effects,
so steering working does not license the claim that you found "the" direction
(2602.06801). On stronger models it no longer beats multi-shot prompting. The one
shape with a real cost argument is amortizing the vector into weights (CASAL,
2510.02324 — 30–40% hallucination reduction, 30× more compute-efficient than LoRA
SFT/DPO), and that is training-time, not a harness mechanism.

### 7f. What this puts to the Thalamus design

- **The abort signal is the overlap.** §2b prices cost as the denominator and
  lab/023's campaign spent $54.11 across 24 arms. A trajectory-abort probe is the
  only instrument in this scan that attacks that denominator directly, and it is
  the same construct the graded ladder scores after the fact.
- **Labels are the binding constraint, and the corpus is the wrong kind.** The
  counterfactual corpus holds 140 trajectory records, of which 83 carry a graded
  rung ladder and 77 sit on a single task; **every one was generated by a cloud
  model with no activation access**, so the existing corpus contributes zero probe
  training rows. At 77 labelled trajectories an AUROC of 0.85 carries a clustered
  95% interval of roughly [0.67, 1.00] at the measured 3.5× session-clustering
  design effect. Beating a G-NLL baseline by Δ=0.10 needs ~300 trajectories;
  Δ=0.03 needs ~3,000, which at the measured $2.25 and 447 s per arm is ~$7,150
  and ~394 hours serial. The published effect sizes in §7c are therefore not
  reachable on this apparatus without generating a local-model corpus first.
- **The endpoint problem recurs here.** Across all 140 records exactly one
  trajectory ever scored rung 4 — lab/024's endpoint-placement finding visible in
  the raw counts — so rung≥3 (28/77) is the only threshold with usable class
  balance. A probe predicting a label that never fires is unfalsifiable by
  construction.
- **The leakage hazard is one we have already been bitten by.** PARALLAX's finding
  — that most published detectors score near chance once the answer is removed
  from the prompt — is structurally the same failure as the git-object-store
  answer-key channel found at 9/88 arms. Any probe AUROC computed over arm
  transcripts inherits every leak channel the standing audit thread has not yet
  closed, and a probe is a *better* leak reader than a language model is.
- **Situation-not-action bounds the ambition.** A probe may be able to say "this
  arm is going badly." Nothing in the literature supports "this tool call is about
  to be wrong," and the 0/143 result is the reason to write that constraint down
  before a design assumes otherwise.
- **Beat the free baseline first.** G-NLL needs no hooks, no serving-stack
  migration, and no training set. Any activation-based instrument that does not
  beat it is not worth its infrastructure.
- **Pinning the corpus does not make the number valid.** The trajectory corpus is now
  sealable by name with a per-record manifest (§2g, lab/038), which is a precondition
  for a probe study citing the state it trained and scored on — and nothing more than
  that. A pinned corpus with an unablated leak channel yields a *reproducibly wrong*
  AUROC, which is arguably worse than an unpinned one because it recruits the pin as
  evidence of rigour. The instrument that catches the git-object-store answer key is
  the **leak-ablation control** — run the probe with the channel removed and see
  whether AUROC survives — not the audit trail. PARALLAX already measured that a
  naïve text-similarity baseline exploits answer leakage to near-perfect detection
  with no access to internals, and the temporal-validity work measured that deleting a
  surface marker moved a baseline by up to 14 points (arXiv 2606.26511). These are
  orthogonal obligations and the corpus-pinning work discharges only one.
- **The contamination denominator is itself a detector-dependent quantity.** The 8-of-88
  git-reach figure is a joint property of (corpus, detector, threshold), and the
  standing audit thread has never scored it under a second detector configuration. A
  controlled audit of pretraining contamination in medical vision-language benchmarks
  (arXiv 2606.10066) measured the same benchmark at **19.8% under SigLIP-B-16 and 4.2%
  under SigLIP-SO400M**, with 0/2000 flags on out-of-domain controls — one measured
  instance of a 4.7× swing from the detector alone. That paper is medical VLM work and
  the transfer to agent transcripts is an argument, not a result. Its subtler half
  transfers more directly: manual adjudication reinterpreted the verdict *without
  changing a single flag*, so pinning the detector is necessary and not sufficient —
  the rubric and the adjudicator need versions too, and the 8-of-88 has a human
  judgement in it. **Cheap falsifier, not yet run:** re-score that finding under a
  second detector configuration. If the count is stable, the pinning obligation here
  is weaker than argued.
- **Not found in this scan:** no held source applies activation probes to *memory
  retrieval* decisions — whether to recall, whether a recalled item was used, or
  whether a trajectory is about to re-encounter a known rake. The probe literature
  gates tools and aborts trajectories; the memory-systems literature (§6) is graded
  on offline benchmarks and reads no internal state at all. This is an absence in
  the 2026 scan, recorded as such and not as a claim.

## 8. Schema-gap literature: belief revision, linkage, and claim resolution

Ingested for the 2026-08-07 design pass on four structural gaps (lab/041, exchanges
`ee3dd5908a994139` and `99068bee1ef649a5`). All three proposals it grounded were
declined, deferred or falsified — the citations stand regardless of that outcome.

### 8a. Belief revision — invalidate and retain, deterministically

The field converged on **invalidate-and-retain rather than retraction**. Zep/Graphiti
(arXiv 2501.13956, §6) runs bi-temporal `T`/`T'` with LLM-detected edge invalidation;
**MemStrata reaches the same result with a deterministic (s,r,o) supersession rule,
no similarity threshold and no LLM call**, and the LLM route is priced at ~8× retrieval
latency for no temporal benefit (MEASURED). Leaving revision to the model fails
outright — BeliefShift leaves **up to 42% of cross-session contradictions unresolved**
(MEASURED). Toki names latest-write-wins over a provenance store as its **audit
erasure** anomaly.

No measured evidence supports a JTMS/ATMS-style truth-maintenance system here. That is
an absence in this scan, recorded as such — but an informative one, since three
independent systems had the option and all declined it.

**What this puts to the design.** Thalamus is already append-only and content-hashed,
so it never actually overwrites: both claims sit in the graph and what is missing is an
*ordering signal at read time*. That makes the reachable form a read-time validity
filter — extending the existing `SUPERSEDES` edge to `Claim→Claim` — rather than a
belief-revision subsystem, and rules out an `INFLUENCES` edge as unfalsifiable.

### 8b. Observation↔workitem linkage — the artifact join is the measured mechanism

KGCompass (arXiv 2503.21710) measures that **89.7% of successfully localized bugs carry
no explicit location hint in the issue and are found only through multi-hop graph
traversal** (MEASURED, held as `scope:literature:claim` under that source). Note the
denominator: that is a share *of successes*, not of all bugs, and the marginal
contribution of the added graph structure is single-digit percentage points — the
argument turns on the gap between the headline and the margin. The exact ablation figures
are **not currently held as claims in the graph** and so are not quoted here; quoting
them anywhere requires a targeted re-ingest of that paper's ablation table first.
No paper in this scan ablates a *direct typed edge* against a shared-artifact
join, so the comparison Thalamus needs is unmeasured externally and belongs to our own
data (lab/041 measures it: 43% of Problems reach no Thread through the join at all).

Retrieval drift from imperfect graphs: arXiv 2603.14828.

### 8c. Claim resolution beyond exact match — the ordering is inverted

The decisive measurement against similarity merging: cosine separates contradictions
from duplicates at **AUROC 0.59** (near chance), and **contradictions are *more*
embedding-similar (0.812) than genuine duplicates (0.800)**, capping precision at 0.667
(MEASURED). No threshold rescues this — a merge rule would preferentially merge
contradictions, which is why §8a and a similarity-merge proposal are mutually
destructive: belief revision requires the contradictory pairs that merging deletes first.

### 8d. Relation-type count — no external number exists

**No measured guidance was found** on how many relation types a graph memory should
carry. Stating one would be an invention, so none is stated. The governing evidence is
first-party: `SUPERSEDES` has existed since M1 and carries **5 edges**, which is the
standing demonstration that an edge type does not populate itself. The test for any new
edge type is therefore to name the default-path writer that emits it.

## Maintenance

This doc is regenerated by the `ground-in-literature` skill
([src/thalamus/harness/skills/ground-in-literature](../src/thalamus/harness/skills/ground-in-literature/SKILL.md)):
before any new feature or component is designed, the literature expert is consulted
and any missing foundational source is ingested (`thalamus ingest`) so it becomes a
tier-2 node with a citation. New findings land here and in the graph, so the doc and
the memory stay in step. **A design that cites nothing has not been grounded — it has
been guessed.**
