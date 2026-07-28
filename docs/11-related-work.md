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
