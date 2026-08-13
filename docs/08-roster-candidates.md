# Roster Candidates — Granularity, Kinds, and the Parked List

**Status:** design. Candidate experts and the rule that decides how finely to cut
them. This doc parks a backlog; it does not commit the roster. Roster discipline
lives in [02-expert-subgraphs.md](02-expert-subgraphs.md) ("two proves N", null
hypothesis, cattle-behind-the-contract) — this is the shortlist that discipline
gets applied to.

## The granularity rule: one litmus, then measurement

"Many narrow experts vs. few broad" is not a taste question; the pinning
architecture ([02-expert-subgraphs.md](02-expert-subgraphs.md)) resolves it. An
expert is a **retrieval scope**, and the scope that governs granularity is *the
dominant domain of a session* — the thing you pin. So the litmus for any candidate
is:

> Is this the dominant domain of real sessions — sessions you would actually launch
> pinned to it?

Yes and it is an expert; no and it is a feed, a skill, or nothing. Every expert is
pinnable and every expert is consultable: the two are properties of the roster, not
kinds of member. Nothing in the contract distinguishes them — a manifest declares
`scope`, `name`, `domain`, `tier`, `claim_kinds`, `allowlist`, and optionally a
`write_boundary` or a `capability_boundary`, and never how often the scope expects
to be pinned.

**The collaboration graph audits the rest.** How broad a scope should be, and
whether it earned its partition at all, are questions with data behind them: a scope
nobody consults and nobody pins → archive it (cattle); a scope that consults the
same neighbour every session → they are one expert, merge. Granularity is not
decided up front; it is instrumented.

### Default move: split top-down, don't merge bottom-up

Start broad. Let the eval loop **split** a scope only when its retrievals bifurcate
into two non-overlapping clusters. Splitting is the safer default than starting
narrow and merging: splitting preserves clean episodic narratives ("this session was
about X"), whereas merging two histories destroys the per-session coherence
[02](02-expert-subgraphs.md) explicitly protects. This is also the honest position
for a project whose identity is measuring hard-to-measure quality — "if retrievals
don't cluster, it isn't an expert" is a *measurement* claim, so measurement makes
the cut.

### Why partition at all — the objection that governs the answer

The case for a roster is **not** that role specialization makes the system smarter.
Measured at equal reasoning-token budget, single-agent systems match or outperform
multi-agent ones across three model families, with a Data Processing Inequality
argument behind the result (`scope:literature:claim:414011b1207b38ef`). The same
work names the condition under which multi-agent becomes competitive: **when
single-agent context utilization is degraded**
(`scope:literature:claim:24bd7f990bd37f8a`).

That is the citable justification, and it is a claim about *corpora*, not roles. A
scope earns its partition when it carries a standing body — a regression corpus, a
token system, a structural map of a codebase — that one session's context cannot
hold. A candidate that would fit comfortably inside the asking session is not an
expert however cleanly it names a job. (The bridge from that measurement, taken on
multi-hop reasoning, to persistent-corpus partitioning is inference, not a result
anyone has measured; flagged by the literature expert as the weakest joint in its
own answer, ticket `scope:main:exchange:7f953992f0c347e7`.)

Role specialization does have direct support — removing role assignments from every
agent's system prompt was the single largest ablation drop measured in ChatDev
(`scope:literature:claim:dc0520a3b45fda00`) — but that is evidence about prompting a
fixed pipeline, not about how to cut a memory roster.

### Role drift is the documented failure mode, so boundaries are structural

MAST, the empirically grounded taxonomy of multi-agent failures (14 modes over 150
traces, κ = 0.88, `scope:literature:claim:11750ab72cf137b8`), names **FM 1.2
"Disobey Role Specification"** as a mode in its own right. The instance it records
is exact: ChatDev's CPO terminated without CEO consensus, and the repair that worked
was **structural authority — giving the CEO final say, worth 9.4% task success — not
a better prompt** (`scope:literature:claim:db0928fe2cfd3616`).

The consequence for this roster: a scope boundary that exists only as a paragraph in
`domain` is the configuration that was measured failing. Where a scope is defined by
what it must *not* produce, the manifest declares that boundary and the `role-guard`
PreToolUse hook enforces it. There are two, and their defaults deliberately run
opposite ways.

**`write_boundary` bounds paths** (`contract/manifest.WriteBoundary`) and defaults
open: a scope that declares nothing is unbounded, which is the honest default for a
scope whose charter *is* to write code, and such a scope says so.

**`capability_boundary` bounds tools and named skills**
(`contract/manifest.CapabilityBoundary`) and defaults *closed*: a scope that declares
nothing inherits `ROSTER_CAPABILITY_DEFAULT`, which denies the design skills and the
`Artifact` tool. `designer` is the one scope that opts out, with an explicit empty
block, because those are its charter. The defaults differ because the decisions did —
path bounds were drawn per scope, and this one was drawn once for the whole roster, so
storing it six times would be a normalization error rather than a redundancy. Omission
therefore has a written meaning rather than an unspecified one, which is LSP's rule
for capability properties (`scope:architect:claim:5d76e83a27802b2f`). Because the
policy is inherited rather than restated, `thalamus contract check --roster` prints
what is actually in force per scope; a single-source default that no one can read back
would be worse than the copies it replaced.

The guard binds the file-editing tools, `Skill` and `Artifact`. It misses Bash, an
unconventional repository layout, a `Read` of a `SKILL.md` (which reaches the
procedure without a `Skill` call), a skill name the deny globs have never seen, and
the Cursor harness, which has no role guard at all. Those are misses, and lab/008's
standing trade applies — a false positive teaches route-around, which costs more than
a gap.

Scope is resolved from the tool payload's `agent_type` first and the environment only
as a fallback, because a subagent inherits its launcher's environment wholesale. Both
boundaries are unenforceable without that: measured over 1132 subagent tool calls,
env-only resolution named the right scope 6.4% of the time and a *different* expert's
scope 17.8%, applying the wrong boundary rather than none.

## Skill vs. expert — the boundary that keeps the roster honest

Not everything worth an agent's attention is an expert. Several operator workflows
already exist as **skills** (procedures) and must not be rebuilt as experts.

- A **skill** is a *procedure* — "do X the right way." Stateless; correct on first
  run.
- An **expert** is a *retrieval scope that learns* — "know about X and remember what
  happened the last fifty times." It earns a roster slot only if **episodic
  accumulation** adds value the procedure cannot.

**Candidate test:** would this expert be materially better after 50 sessions than
its curated knowledge subgraph alone? If no, it is a skill or an ingestion feed, not
an expert. (Applies the "materially better than its knowledge graph alone" claim
from [02](02-expert-subgraphs.md).)

## Parked candidates

Shortlist only. Each must still clear the null hypothesis ("just put it in an
existing expert") before it ships.

The `Kind` column is gone with the typology that produced it. What replaces it is
the standing corpus — the thing a session's context cannot hold, which is what the
partition is actually for.

| Candidate | Standing corpus | Serves | Status / note |
|---|---|---|---|
| Technical-literature | the ingested paper graph | everything | **Live** (`config/experts/literature.yaml`). GraphRAG/retrieval papers are a *feed into this*, not a separate expert. |
| Evaluation-methodology | metric designs, campaign verdicts, instrument defects | all projects + career | **Live** (`config/experts/eval-methodology.yaml`) — see below. Metrics design, LLM-as-judge, ablation/counterfactual design, calibration. The through-line made a node; the eval loop dogfooded. |
| Homelab / self-hosting | what happened on this machine the last N times | media server + machine + console surfaces | **Live** (`config/experts/homelab.yaml`) — see below. First distillation-fed expert, empty feed surface. |
| Teacher | the learner model — what stuck, which framings landed | every learning initiative + career narrative | **Live** (`config/experts/teacher.yaml`) — see below. Curriculum design over a persistent learner model; first dual-fed. |
| Quality engineer | the regression corpus of every bug that shipped | all projects | **Live** (`config/experts/qe.yaml`) — see below. Holds the oracle; carries a `write_boundary`. |
| Visual designer | the design system, tokens, and prior comps | all projects | **Live** (`config/experts/designer.yaml`) — see below. Shipped with an empty scope and no tooling, both deliberately. The only scope that opts out of the roster capability deny. |
| Code advisor | the structural map — seams, leaked abstractions, rejected refactors | all projects | **Live** (`config/experts/architect.yaml`) — see below. The one live expert with no `write_boundary`, by charter; it carries the inherited `capability_boundary` like every other scope. |
| DL / training | training-run history | StepMania | PyTorch, autoregressive decoding, KV-cache, CFG, sampling. Compounds via "what training run did what." |
| Agent-systems | harness decisions and their outcomes | Thalamus, Nodeglass | Harness design, MCP, tool-use, context mgmt, subagent orchestration. |
| Structural-safety / trust | attack surface and what was tried against it | Nodeglass, Thalamus | Provenance, gating, poisoning, policy engines, red-teaming. Second pillar. Overlaps `qe` and eval's canary work — check both before minting. |
| Retrieval / memory-architecture | retrieval-design tradeoffs and their measurements | Thalamus | Vector vs. graph memory, chunking, reranking, RAG eval. Self-referential dogfooding; where the "graphrag expert" instinct actually belongs. |
| Rhythm-game / music-domain | chart-taste judgements over time | StepMania | Chart conventions, biomechanics, groove radar, onset/music-theory. The *taste* side; pairs with DL expert. |
| Career-narrative / interview | — | job hunt | **Absorbed into `teacher`** — which framings landed is a learning record; the experience library rides in the teacher's manifest. |

## The second expert: evaluation-methodology (two proves N)

[02](02-expert-subgraphs.md) reserves the second roster slot for the expert that
proves the contract. It is **evaluation-methodology**, shipped as
`config/experts/eval-methodology.yaml` — the zero-glue test held: a new manifest
and *nothing else*. Two facts settled the choice:

1. **Consultants are exercised by consultation, which is live.** Eval-methodology
   is consultable the day its manifest exists, and the tap instruments it from its
   first retrieval.
2. **The spine alternative (homelab) has no corpus**: the media-server sessions
   are deliberately outside the bootstrap allowlist (VPN credentials), so a
   homelab expert would sit inert and unmeasured.

The null hypothesis ("a feed into literature") stays open on purpose: the split
stands until retrieval clustering says merge — this doc's own discipline;
measurement makes the cut.

**Prior work.** A second access-governed scope instantiates published consensus,
not new ground: explicit authority and scope on multi-agent memory reads/writes
is a named first-class concern of the agentic-web infrastructure survey (arXiv
2606.20570), and shared graph memory with provenance-linked traces is production
tooling (Neo4j, NODES AI 2026) — see [11](11-related-work.md) §3. The domain
choice *converges* on the field's own turn from retrieval-QA proxies to
downstream-utility evaluation (survey arXiv 2603.07670; Mem2ActBench arXiv
2601.19935). The expert's anchor knowledge is the judge/meta-evaluation
literature (A Survey on LLM-as-a-Judge, arXiv 2411.15594) and counterfactual
consequence-level evaluation (MQuAKE, arXiv 2305.14795), procured against
recorded demands: the eval loop's lexical-only attribution ([11](11-related-work.md)
§5) and the M4 counterfactual harness. The roster mechanics
(split-until-measurement-says-merge) are this project's own discipline.

## The third expert: homelab (the first spine)

Shipped as `config/experts/homelab.yaml` — zero-glue held again. Both facts that
deferred it at the expert-#2 decision have since flipped:

1. **Pinning is live** (M3, "the process is the pin"), so a spine expert is
   exercisable: sessions whose dominant domain is the box — tailnet serving, the
   console and course PWAs, systemd units, the media stack — get pinned to
   `homelab` and distill there instead of diluting `main`.
2. **The corpus objection was about bootstrap, not accumulation.** The media-server
   transcripts stay outside the archive allowlist (VPN credentials), but the expert
   feeds forward from pinned sessions; the 2026-07-17 console sessions alone
   minted reusable ops claims (WebAPKs ignore ports; `tailscale serve` strips the
   mount path; ttyd base-path targets).

What distinguishes it structurally: the two consultants are web-ingestion-fed,
this expert is **distillation-fed** first — tier-1 first-party episodic memory —
plus operator-hand-fed local files (first feed 2026-07-18: the roster/console ops
notes, making the console seam hazards citable in consultations), so the
manifest declares the kinds that feed writes while the allowlist stays empty
(web ingestion blocked; local files bypass the list as the curation decision
itself). It passes the skill-vs-expert test precisely where the
`home-media-server` *skill* stops: the skill is the procedure, the expert is what
happened on this machine the last N times.

## The fourth expert: teacher (the second spine)

Shipped as `config/experts/teacher.yaml` — zero-glue held a third time. The parked
career-narrative/interview candidate ships *inside* it rather than beside it: the
operator's learning and the operator's story are one learner model (below).

**Granularity.** Teaching sessions are bonafide sessions — curriculum building in
`~/code/thalamus-teach`, drills, mock interviews, resume and narrative work — with
teaching as the dominant domain, so the litmus says spine. Until this expert, those
sessions distilled into `main`, where lesson state and mock grades dilute the
implementation memory `main` exists to hold (the operator-reported friction that
prompted the roster act); the pin moves them where they compound.

**Null hypothesis** ("pedagogy papers as a `--feed` into literature, teach sessions
keep distilling to `main`") fails on both halves: a consultant is never pinned, so
the thing that makes a teacher worth having — the accumulated learner model — could
never land anywhere. And the scope is cross-project by construction: quantitative
analysis, ML, statistics, and experimental design recur from StepMania training
work to Thalamus eval methodology; per-project placement would shatter the one
learner those initiatives share.

**Skill-vs-expert** passes exactly where the `thalamus-design-readiness` skill
stops (the same boundary as homelab vs. `home-media-server`): the skill is the
check procedure, the expert is what has been taught, what stuck, and which
framings landed the last N times. Its entire value is longitudinal — the
50-session test *is* the design.

**Structure.** A **dual-fed** expert: pinned-session distillation (tier-1
learner episodic, the homelab pattern) *plus* a live ingestion feed
(`--feed thalamus-teach`), so unlike homelab the manifest declares the literature
claim kinds and the academic allowlist. Anchors were procured into its own scope
at roster time ([06](06-ingestion.md) rule 1's scope note — a scope with nothing
to cite refuses the consultation mint): learner modeling as prediction over the
interaction history (Deep Knowledge Tracing, arXiv 1506.05908), trainable
retention from practice history (half-life regression, Settles & Meeder, ACL
P16-1174), and pedagogy specified at the instruction level rather than in weights
(LearnLM, arXiv 2412.16429).

**Prior work.** The classic ITS decomposition — domain model / student model /
tutoring model — instantiated on Thalamus's own substrate: knowledge subgraph as
domain model, episodic subgraph as student model (DKT's premise is that the
interaction history *is* the model, and it names curriculum design as what the
learned model is for), manifest-derived context as the tutoring layer (LearnLM's
pedagogical-instruction-following, convergent with [02](02-expert-subgraphs.md)'s
"specialization lives in memory, in context"). See
[11 §3d](11-related-work.md). The cited work trains on population-scale learning
traces; this learner model is n=1, so its claims stay observational — the
project-wide honesty rule, applied to its own teacher.

**The career-narrative absorption.** Interview positioning is the learner model
read outward — "which framings landed" is a learning record like any drill
result. The manifest's `domain` names the `personalized-resume` skill's
experience library as standing learner context, which is how a *derived* agent
definition (no hand-written persona, [07](07-harness-integration.md)) still
knows who it teaches: the pointer is tier-0 manifest content; the skill remains
the procedure it complements.

## Experts five, six, and seven: qe, designer, architect

Shipped together as `config/experts/{qe,designer,architect}.yaml`. Zero-glue held a
fourth, fifth and sixth time for the manifests themselves; the `write_boundary`
field and its guard are a genuine contract addition, and the first since v0 —
justified above by MAST's role-drift finding, not by these three scopes needing
somewhere to put a preference.

**Rollout, and what it costs.** All three at once forecloses a signal: treating a
role set as a search space, each addition has a cost and the cheapest configuration
is learnable only if additions are separable (`scope:literature:claim:75001312d7b6e351`).
Shipping three simultaneously means no scope gets a clean before-and-after. That was
the operator's call, made with the objection in view, and the compensation is that
the audit is pre-registered here rather than reconstructed later:

> A scope has failed its partition if, after fifty sessions in which it could have
> been pinned or consulted, its episodic subgraph holds nothing a session could not
> have derived in context — no accumulated corpus, no retrieval another scope's
> recall would not have served. For `qe` the corpus is regression cases and their
> findings; for `designer`, the design system and prior comps; for `architect`, the
> structural map and the rejected-refactor record. A scope with a `write_boundary`
> that never once fired is also suspect — not proof of failure, but evidence its
> boundary was never load-bearing. The `capability_boundary` does not carry the same
> inference: it is inherited rather than chosen per scope, so a scope that never hit
> it was never claimed to need it.

**Prior work.** The role set is not new and is not claimed as such: MetaGPT
assigns five roles including **Architect and QA Engineer** in a sequential workflow
(`scope:literature:claim:6fde48b087433b6c`), encoding SOPs as prompt sequences so
agents can verify intermediate results (`scope:literature:claim:a7ffc88b00c4fa58`).
The unit-test division adopted here is prior art in the same system: MetaGPT's
Engineer runs its own unit tests through executable feedback *while a separate QA
Engineer exists* (`scope:literature:claim:c01ad32f66dcc9fd`). What Thalamus does
with it is an **instantiation**, on two axes the cited work does not have: the roles
are retrieval scopes with their own episodic memory rather than prompt personas in
one pipeline, and the boundary between them is enforced by a hook over tier-0
configuration rather than by the system prompt whose disobedience MAST measured.

### `qe` — quality engineer

**Charter.** Adversarial quality of running applications: hostile and malformed
inputs against real surfaces, invariant and metamorphic suites over write paths, and
a regression corpus where every shipped bug becomes a permanent case. Unit tests are
out of scope by construction — they belong to whoever writes the code.

**The eval-methodology boundary is the consulted one, not the one first drawn.** The
operator's line was "experiment or invariant." Consulted under ticket
`scope:main:exchange:019917aadba24811`, that expert disagreed usefully: the oracle
line is **graded, not a partition**. Metamorphic testing exists precisely to
*alleviate* the oracle problem (`scope:eval-methodology:claim:3ade7ca7aeeaeca2`), and
a family of adequacy metrics scores how much oracle a suite has
(`scope:eval-methodology:claim:fc692333943d493a`) — a field does not build metrics
for how much of a thing you have if having it is a boolean. Its counterexample:
SWE-bench+ found that filtering solution leakage and weak test cases dropped
SWE-Agent+GPT-4 from 12.47% to 3.97% (`scope:eval-methodology:claim:992313bd47b27dad`)
— a hard pass/fail oracle that was *wrong*, established by measurement. The
first-party version is this project's own: 9 of 88 counterfactual arms read their
pre-registered answer key through the git object store
(`scope:eval-methodology:claim:30663540dd870284`).

The adopted line is that expert's repair: **qe owns the oracle; eval-methodology
owns the oracle's warrant.** A qe finding indicts the system under test; an eval
finding indicts the instrument.

**Anchors are not duplicated.** The metamorphic and mutation anchors stay in
eval-methodology as single copies, split by use rather than by topic — the precedent
that scope splits follow use (`scope:eval-methodology:claim:716fccb5dedc0e12`), and
the recorded cost of ambiguity: a session already misread a correct use-split as
doc/graph drift and had to retract (`scope:eval-methodology:claim:0c62f6e184504755`).
The seam runs *inside* the papers — qe's interest is metamorphic-relation
identification and input generation, eval's is adequacy measurement
(`scope:eval-methodology:claim:d0805f6911a167af`) — which is the strongest argument
that topic-level duplication is the wrong unit. qe reaches them by consultation.

**The M5 canary splits rather than routes.** To qe: the missing regression tests
(`tests/` contains no occurrence of curl, wget, mailbox or SendMessage —
`scope:eval-methodology:claim:f1919fb9d5e81d68`) and the detectors with their unit
tests (`scope:eval-methodology:claim:fcf77e1039c7583c`). Staying with eval: the
defense-off control arm and contrast estimand
(`scope:eval-methodology:claim:86155d50448b73b6`), the confound that makes a 0%
reading uninterpretable (`scope:eval-methodology:claim:38628d1a8e7167b3`), the
pre-registration spine, and endpoint placement — where this class of design fails
silently, 1/10 vs 0/9 at rung ≥ 4 against 7/10 vs 2/9 at rung ≥ 3
(`scope:eval-methodology:claim:ee6fd5ddd9972b17`). A green qe suite will not catch a
misplaced ASR endpoint.

**Green rule.** Adversarial campaigns are allowed to fail; a confirmed finding
graduates into the green pytest suite as a permanent regression test. This is why
the `write_boundary` denies `*/src/*` and leaves `tests/` and `lab/` open.

**Null hypothesis** ("adversarial cases are just tests `main` should write, and the
oracle work belongs to eval") fails on the corpus: the value is a growing body of
real failures and the conditions that produced them, which is longitudinal by
construction — and safety is a longitudinal property rather than a snapshot
(`scope:literature:claim:623a8c4eaa444be8`). It also fails on independence: a scope
that repairs what it asserts against has no assertion worth anything, which is the
`write_boundary`'s whole content.

### `designer` — visual designer

**Charter.** Visual and interaction design whose deliverables are design artifacts
and never software: mockups, wireframes, comps, design systems and tokens, handoff
specs, diagrams, and visual critique of built surfaces against design intent.

**It shipped empty, twice over, and that is the notable fact.** The literature
consultation reported the `literature` scope holds *nothing* on visual or
interaction design — two recalls returned only token-level false positives — so
unlike every prior expert this one had no carry-over to inherit, and every citable
claim in it arrives by procurement — Nielsen's heuristics, Atomic Design, and the
W3C accessibility principles. A scope with nothing to cite refuses the consultation
mint ([02](02-expert-subgraphs.md)), so anchoring was a precondition of shipping,
not a follow-up.

**The tool is self-hosted Penpot, and the deciding fact is authoring.** Figma's REST
API cannot create design content — its write endpoints are comments, variables,
webhooks and dev resources — so a `designer` on Figma could read, export, critique
and spec, but never produce the mockup its charter is named for. Penpot's plugin and
RPC surface creates shapes, frames, text and components, and its files are an open
format, which makes design artifacts inspectable and versionable the way every other
artifact here is. It also sits better against the `write_boundary`: an MCP that
writes *into* a design tool is boundary-compatible, whereas Figma's MCP is oriented
toward emitting code from designs, which the deny list blocks. Deployment is gated
on four conditions the homelab expert measured on the box (ticket
`scope:main:exchange:432ff6f9cd6f43ba`) — the system Docker engine rather than the
GNOME-session-bound Desktop VM, its own tailnet hostname (Penpot is a root-scoped
SPA and Android WebAPKs are port-blind, so neither a subpath nor a port works), an
explicit `mem_limit` on every container, and NVENC confirmed for Jellyfin. Two of
those fix standing fragilities that predate Penpot.

**Skill-vs-expert** passes where the `frontend-design` and `dataviz` skills stop —
the same boundary as homelab vs. `home-media-server`, and teacher vs.
`thalamus-design-readiness`. Those skills are how to design well on first contact;
the expert is the design system this project has actually converged on and what was
tried on these surfaces before.

**The boundary is structural because prose could not hold this one.** The operator's
definition is explicit that this is "not a front end developer in dressy language,"
and the shortest path from a mockup to a demo is always to write the component. The
`write_boundary` denies executable source and leaves markup, markdown, SVG,
diagrams, and token files open.

**It is also the one scope that holds design capability, and the only one that opts
out of the roster capability deny.** The design skills and the `Artifact` tool are
denied to every other pinned expert, because a scope that spends a design budget
trades its own charter for presentation; here they are the charter. `designer` is
therefore the only manifest carrying an explicit empty `capability_boundary` — and
that opt-out is what earns the inherited default its place, since without a scope
that needs the exemption the policy could simply have been hard-coded in the guard.

**The qe seam.** Accessibility conformance is where this scope's judgement becomes
machine-checkable, which makes WCAG the natural hand-off from `designer` to `qe` —
the one part of the design canon with pass/fail semantics.

**Null hypothesis** ("design is a skill, not a scope; hand-feed a style guide")
fails on accumulation: a design system *is* the standing corpus, and which comps
were rejected and why is exactly the episodic record a stateless procedure cannot
carry.

### `architect` — code advisor

**Charter.** Organizational and architectural health plus performance and
reliability: where the seams are, which abstractions leaked, which refactors were
tried and rejected and why; hot paths, unbounded growth, retry and timeout behavior,
with before-and-after numbers rather than assertions of improvement.

**Structurally the odd one: no `write_boundary` at all.** Writing the changes it
proposes is its charter, so a path deny would block the work rather than bound the
role. Its boundary is a **pin trigger** instead — campaign sessions only, where the
session's goal is reorganization, a measured performance fix, or a reliability
hardening pass, while feature work stays with `main` and consults it. That is
enforced by operator intent at launch and audited afterwards by what its pinned
sessions actually did, which is a materially weaker guarantee than the guard. Named
here rather than papered over: it makes `architect` the roster's test of whether a
when-you-pin boundary holds as well as a what-you-may-write one.

**Its instrument.** `thalamus arch` (`scan`, `show`, `diff`, `rules`) walks the
repo's Python imports under a **declared** extractor policy and lands the result two
places: `arch/model.yaml` in git, and one tier-1 `Source` per scan in the graph. The
policy is declared because it is load-bearing — propagation cost over `src/thalamus/`
reads 7.53% counting every import and 5.75% counting only module-level ones, so a
number without its rules attached is not a measurement. The policy digest therefore
rides in the scan id (`arch:scan:<repo>:<sha7>:<policy-digest7>`), and supersession
runs per `(repo, policy)`: two scans under different rules are incomparable, not two
readings of one lineage.

The model file has an authored half (layer partition, permitted-dependency rules,
seams, rejected refactors pointing at the graph node holding the rationale) and a
derived half regenerated per scan. Both are committed, because the diff is the
artifact. Only **findings** reach the graph — a cycle, a violated rule, an unplaced
module — never metrics: those are recomputable from the retained model file, and a
scanner writing a claim per measurement would make its own scope unrecallable.

Half the charter has no instrument. Performance and reliability — profiling, hot
paths, before-and-after numbers — is served by nothing here, and the scope holds no
profiling literature either (its SRE material is risk-tolerance and SLO-setting,
which is a different question). Recorded as a known gap rather than an assumed win.

**Boundaries against the neighbours.** A structural property that should hold
permanently and be checked is an invariant, and belongs to `qe` — which is where the
extractor's own acceptance test lives, as a hand-counted edge list over a five-module
fixture (`tests/qe/cases/arch_extractor.py`). A performance claim
that needs a control or a statistic to mean anything belongs to eval-methodology.
What is left — the judgement about whether a shape is right, and the memory of every
shape this codebase has been — is this scope.

**Null hypothesis** ("`/code-review` and `/simplify` already do this; `main` can
refactor") fails on the 50-session test more clearly than any other candidate here:
a review skill sees one diff, and the entire value of this scope is the standing
structural map plus the record of rejected refactors, which is precisely what a
per-diff procedure cannot accumulate. Conway's law also cuts here, and against us —
a codebase grows seams matching the organization that builds it, so a roster with an
architect scope should expect its own structure to start showing up in the tree
whether or not that was intended.

## Parked: project attribution as leaf, compression as the connective core

Raised by the operator while defining the three experts above, and parked rather
than built — the manifests do not depend on it.

The proposal: an expert should hold **deep episodic knowledge per project** and, over
that, **compressed representations of those experiences as generic insights**, so
that the compressions and the ingested knowledge are the connective core of an
expert and the projects hang off it as leaves. Every scope on the roster is now
cross-project, which makes this the natural next question about what a scope *is*.

Half of it already exists: episodic nodes carry a project and `memory_recall_by_project`
resolves on it. The unbuilt half is the compression — distilling per-project episodes
upward into scope-level insights that apply where no project matches.

It is a memory mechanism, not a manifest field, and it needs its own grounding pass
before design. The prior work to start from: cross-task insight extraction from an
experience pool (ExpeL), reflection over an episodic stream (Generative Agents), and
reusable routines induced from past trajectories (Agent Workflow Memory). None of
these is held in the graph yet; the design is not started until they are.

The falsification risk to carry in: the project's own record of a precomputed
summary layer that was cited, consulted on, committed and documented before anyone
asked whether the graph already answered the question at runtime — it did, and the
layer was withdrawn (lab/025, `scope:main:claim:bb647ce95f0ff23a`). A compression
layer is the same shape of design. Step A0 of `ground-in-literature` is not optional
for it.

## Anti-candidate (recorded so it stays dead)

- **A broad "AI engineer" expert.** Worst of both kinds: too coarse for sharp
  retrievals, too broad for episodic coherence. Correct decomposition is DL /
  agent-systems / eval-methodology / structural-safety — which is the operator's own
  four pillars. That the partition matches the pillars is the point, not a
  coincidence.
