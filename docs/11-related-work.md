# Related Work — Where Thalamus Sits in the 2026 Literature

**Status:** living document. Last scan 2026-07-29. This doc exists to keep the
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
*real* sessions, attributes used-vs-ignored against their *own* retained transcripts,
grades **per-expert pin quality**, and **feeds a utility-driven forgetting policy**.
Benchmarks *measure*; they do not *self-maintain*. The correct framing is therefore
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
over a ~59pp permuted floor (lab/032). Two anchors procured under feed
`attribution-eval`: **ContextCite** (arXiv 2409.00729) and **TRUE:
Re-evaluating Factual Consistency Evaluation** (arXiv 2204.04991). Still
unprocured and named by the consult: ALCE, AIS, RAGAS, ARES, FActScore,
AttributedQA; and for the causal arm, influence functions (Koh & Liang) and
datamodels. **Supply-blocked:** Ojala & Garriga, *Permutation Tests for Studying
Classifier Performance* (JMLR 2010) — the canonical methods citation for the
permutation null itself, no arXiv version.

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
   2606.04329 — but the scan did not find the coupling used as a *memory-formation*
   mechanism between agent scopes. Provisional, like everything on this list.
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

## Maintenance

This doc is regenerated by the `ground-in-literature` skill
([src/thalamus/harness/skills/ground-in-literature](../src/thalamus/harness/skills/ground-in-literature/SKILL.md)):
before any new feature or component is designed, the literature expert is consulted
and any missing foundational source is ingested (`thalamus ingest`) so it becomes a
tier-2 node with a citation. New findings land here and in the graph, so the doc and
the memory stay in step. **A design that cites nothing has not been grounded — it has
been guessed.**
