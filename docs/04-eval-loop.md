# Eval Loop — Measuring Memory Utility

**Status:** layers 1/1b built (`src/thalamus/eval/`); layer 2's task battery
(`config/tasks/` + `thalamus eval tasks`) and arm runner (`thalamus eval run`:
memory-on / memory-off / scoping-degraded) built — snapshot pinning, campaign
analysis, the judge, and layer 3 remain. This is the
differentiating component: the project's central
claim is not "I built agent memory" but "I built agent memory **and the evaluation
loop that proves what it's worth**."

## The question

Does this memory system actually make the agent better — and how would you know?

Retrieval precision/recall is a garbage proxy: it grades whether retrieval matched a
query, not whether it changed anything. The metric that matters is **downstream
utility**: did the retrieved memory alter the agent's behavior, and for the better?
Memory quality is a hard-to-measure quality, so we build the missing metric — same
discipline as the taste critic, pointed at memory instead of music.

This is now the field's consensus, not a lone position: the memory survey (arXiv
2603.07670) names the same shift, and a wave of benchmarks — Mem2ActBench (arXiv
2601.19935), MemoryArena (arXiv 2602.16313), AMA-Bench, Momento — measure memory by
downstream, action-coupled outcomes ([11-related-work.md](11-related-work.md) §2).
Those are all **offline benchmarks**: fixed dataset, external grader, run once.
Thalamus's differentiator is the part none of them is — a **live, in-deployment,
self-maintaining loop** over the operator's own sessions. We cite the benchmarks as
the offline half we extend, not a void we fill.

## Layer 1 — Retrieval traces (M2)

Every graph query the agent makes is instrumented via harness hooks
([07-harness-integration.md](07-harness-integration.md)). Per retrieval event:

- session, pinned expert, consulted expert (if an exchange), query, returned nodes;
- **used vs. ignored** — was the retrieved content reflected in what the agent
  actually did (cited in the answer, visible in the diff, referenced in a
  subsequent tool call), or was it dead weight in context?

Used-vs-ignored attribution starts crude: lexical/structural matching between
retrieved content and the session's outputs, judged post-hoc. **A crude measure is
not automatically better than no measure, and this project has the counterexample.**
For as long as the floor was unknown, the shipped target "used% above ~50" sat
*below* permuted chance, so an agent hitting it was performing worse than random and
the number read as evidence. A crude measure earns its keep only once it is reported
beside its null; refining it is lab-notebook material, calibrating it is not
optional. Traces land as episodic memory (the trace store **is** a property graph),
so the eval loop needs no side database: it reads the same substrate it grades.

**How crude is now measured, and it bounds every number below.** Under permutation
— judging a retrieval's nodes against an *uncorrelated same-project session's*
output window, meaning a different session that shared neither a room nor a fork
parent with it (docs/09 §Scope), since room-mates and forks share the conversation
itself and would price topic overlap as chance — used% reads 58–61% against 62.9%
for the real window. Across projects the
same test reads 5%. So the instrument is a **topic detector**: nearly perfect at
"is this node from this body of work", and carrying roughly **4 points of
discrimination on a 59-point floor** at the question actually being asked, "did
this retrieval get used". It also rises with output length (51.7% at 20–100k chars
vs 69.7% at 100k+), which means it partly re-measures the session-length effect
that already dominates cost. Read every used% in this document as ~59 points of
vocabulary overlap plus ~4 of utility (lab/032). The fix is to report the permuted
baseline beside the rate — computable from retained data, and gated on the
grounding/consultation path because it changes a metric of record.

**As built:** retrieval results render their vertex IDs inline, so the verbatim
PostToolUse tap *is* the node-level trace — no side schema (docs/09). `thalamus
eval sync` lands tap lines as `Trace` nodes (`Session -[QUERIES]-> Trace -[RETURNS]->
result`), attributing each returned node against the session's retained transcript:
cited-by-ID and thread-slug mentions are strong signals, then lexical term overlap
(≥2 terms and ≥30% — arbitrary dials, here to be pressure-tested). Verdicts live on
the RETURNS edge as `used`/`evidence`. `thalamus eval report` renders per-scope
totals, per-tool counts, miss rate, and the most retrieved-but-ignored nodes — the
layer-3 decay candidates. A trace can only land after its session distills (the
QUERIES edge and the transcript both need it); until then it stays in the tap,
reported as pending. Attribution findings: lab/002.

The priced surface covers every way a session reads the graph: the recall
tools, `memory_query` (rejections and server failures are their own event
class, priced for injection cost like any response), and ad-hoc gremlin-python
through Bash — a PostToolUse tap (`gremlin-tap.sh`) records gremlin-marker
commands as `bash_gremlin` trace lines in the same JSONL, stdout chars as the
injected_chars analog, attribution unchanged. One priced surface, no parallel
metric (eval-methodology consultation, lab/008). The fluency layer's own
metrics — guard rescue rate from the block/pass event log
(`~/.thalamus/guards/`), rejection classes, recipe-derived vs from-scratch by
traversal-shape fingerprint — render via `thalamus eval gremlin`; `thalamus
eval recipes` smoke-runs the stored recipes read-only as a rolling freshness
signal (eviction candidates: zero reuse and failing smoke, archival never
deletion). Known residual: script files are invisible to the Bash marker
heuristic.

## Layer 1b — Cost, the denominator

Utility alone is half a fraction. The field grades memory on **performance–cost
frontiers** (BudgetMem, arXiv 2602.06025 — token usage aggregated per query,
converted to cost), and token cost is a session-level metric in the AgentOps
observability taxonomy (arXiv 2411.05285). `thalamus eval cost` is the live-loop
instantiation of both — a *convergence* on prior work, not an extension (see
[11-related-work.md](11-related-work.md) §2b): no new telemetry, every number read
from records the system already keeps.

- **Harness transcripts** (per-API-call usage) bucketed by an operation ontology:
  `interactive`, `extract` (headless distillation/ingest), `expert:<scope>` (via
  the pin ledger — the pin is also the cost attribution), `other` (the
  denominator). The ontology-with-weights pattern is borrowed from the operation
  registry in the operator's own workflow-eval project (nodeglass); its DAG
  topology scorers are **not** adopted — they grade structural action risk, and
  retrieval traces are shallow star graphs where topology says nothing.
- **The trace tap** gives each retrieval's injection cost — the rendered response
  *is* the cost, and it recurs in every later call of the session.
- The weighted-token proxy (cache reads ~0.1x, cache writes ~1.25x, output ~5x)
  is a dial, not a truth — same discipline as the attribution thresholds above.

Standing finding: session length, not retrieval or consultation, dominates token
burn — thalamus's steady-state marginal cost is one extract run per session end.

**The cost-utility join:** Trace nodes carry `injected_chars` at sync (the
rendered response is the injection cost), and `eval report` prices every layer-1
verdict at an even per-node share — so the layer-3 decay ranking orders by
**wasted tokens**, not ignore-counts. The waste ranking surfaces cross-project
bleed that count ranking buries (measured: lab/006–007). This is the first
implemented piece of the per-expert routing signal: scope-level cost-utility is
one report away from grading pin quality.

**Which ranker produced the row.** Trace nodes also carry `ranker_config`, and
`eval report` takes `--since/--until`, because a retrieval-utility number is only
comparable across a window if the ranking dials held across it. The fingerprint
cannot be stamped at sync time — sync runs days after the retrieval, on a
checkout whose ranker may have moved, so reading the installed dials then would
attribute old traces to a ranker that never served them. It is written by the
process that does the ranking (`eval/rankers.py`, the pin ledger's idiom) and
joined by timestamp; traces older than the ledger read `unknown`, never a
borrowed fingerprint, and a window spanning two rankers says so rather than
averaging across the change. Without this, turning a second dial converts an
unverified prediction into an unauditable one — which is how lab/007's fan-out
prediction sat twenty-two entries unchecked with all its evidence already in the
graph (lab/029, where the audit finally ran and the prediction held).

## Layer 1c — Randomized withholding, the counterfactual inside real work

Layer 1 grades a set the ranker chose, which makes every used-rate a correlation. A
permutation null bounds the *judge* (experiments/001) and can say nothing about the
*retrieval*. The intervention that can is one line of policy: with a pre-registered
probability, drop a node the ranker would have rendered, and record the draw.

`eval/policy.py`, off unless `THALAMUS_WITHHOLD` carries a rate — withholding costs
the operator real retrieval quality, so turning it on is a deliberate act with a
number attached, and a campaign that forgets to set it produces no records rather
than silently unrandomized ones. The draw is seeded from the retrieval's own identity
and the seed is stored, so an analysis months later re-derives the exact draw from
the record with no live state.

One mechanism, two estimators:

- **A switchback inside the operator's own sessions.** Within-unit randomization with
  carryover (injected tokens ride along in every later call of the session),
  analysable by exact randomization inference — the in-deployment pivot lab/024 argued
  for, without a container campaign.
- **A stochastic logging policy.** Recording the propensity is the standing
  precondition for replay and doubly-robust estimation off the trace log, which
  [11](11-related-work.md) §4 records as unavailable precisely because retrieval here
  was deterministic. It no longer has to be.

Two things the design refuses. A retrieval is never *fully* withheld, because an
empty render is a miss and the tap cannot tell a miss from a fully-withheld
retrieval. And a withheld node gets **no verdict at all** — it never reached the
agent, so folding it into "ignored" would put the intervention's own effect into the
outcome it is measuring.

The record joins to its trace by the sha256 of the rendered response, which the tap
stores verbatim: content matches content, so a busy session cannot pair a draw with
the wrong retrieval, and an unmatched record stays visibly unmatched.

## Layer 2 — Counterfactuals (M4)

**The ceiling arm, and what it settled.** `ceiling` is memory-off's stripped harness
plus the task's withheld fact injected as recall — a candidate handed exactly the right
memory with no retrieval to get wrong. It bounds what any retrieval could be worth, and
a task with nothing withheld is refused because there it is memory-off under another
name.

Measured 2026-07-30, 12 arms (experiments/004, lab/036): **neither arm reached the
pre-registered rung 4**, so a perfect memory cannot clear the battery's one
strongly-gated task, and the battery — not the memory — is the binding constraint. The
container campaign and the consequence-probe work are **cancelled**, not rescheduled:
more arms against a battery that cannot register a perfect memory buy noise. The
exploratory direction ran *against* the ceiling (0/6 at rung 3 vs 5/6), on a sign test
of p = 0.219 that is reported as the modest thing it is.

An exploratory follow-up at double the turn budget, worktree retained, rules out
censoring and names the mechanism: the arm finished in 36 of 80 turns and still lost
**L2 and L3**, the foundation rungs every memory-off arm passed, while its diff
implements the memo's conclusion in the candidate's own words. (L5 does not
discriminate — it is an absence check every arm passes.) A conclusion handed over
without its path replaced the path, which is a finding about what distillation should
extract, not only about this battery.



Traces show usage; they can't show *value*. For that, matched tasks run under
arms, and the arms are scored on **downstream consequences** — never on whether
memory was surfaced or quoted. The grounding is MQuAKE's finding (arXiv
2305.14795, in the graph): systems that recall a stored fact accurately still
fail catastrophically on questions whose answers are *entailed consequences* of
that fact. A memory-on arm that cites the claim and still steps on the
memorized rake scores the same as memory-off. This is the difference between
"I built memory" and "I measured what memory is worth."

**Arms.** `memory-on` (full Thalamus) is the common control; `memory-off` (no
memory surface) gives the headline contrast. Degradation is **one factor at a
time**, each contrast sharing the memory-on runs — a single "degraded" arm
would confound exactly the three properties it exists to separate:

- **scoping-degraded** — wrong expert pinned, serving another scope's memory of
  comparable size and age. Isolates routing/pin value; joins the `eval pins`
  signal.
- **freshness-degraded** — a snapshot from N sessions back, same scope, same k.
  A stale memory is an unpropagated edit in MQuAKE's sense: recall of the stale
  fact stays healthy while its entailed consequences fail, so this arm's probes
  target facts whose implications changed since the snapshot.
- **volume-degraded** — same scope and freshness, top-k truncated (k=1) and,
  separately, inflated with retrieved-but-ignored padding: both directions of
  the volume dial.

A factorial is unaffordable at this n; each contrast supports only "removing
property P cost X on these paired tasks," never an interaction model, and the
report says so.

**The battery — counted before judged.** Cheap enough to run routinely means
mostly mechanical: (1) binary task success against a mechanically checkable
acceptance test, pre-registered at task-authoring time before any arm runs;
(2) iterations-to-done / turns to first passing state, counted from the
transcript; (3) operator interventions, counted; (4) wrong-path detours — tool
calls on files irrelevant to the oracle solution, reverted-then-redone edits;
(5) token cost per arm, which layer 1b already prices, reported as the
utility-per-token frontier (BudgetMem, arXiv 2602.06025); (6) **consequence
probes** — 1–3 pre-written per-task checks that are true only if the memory's
*implications* were acted on, the live analog of Mem2ActBench's
memory-grounded-into-tool-calls tasks (arXiv 2601.19935, in the graph) and the
multi-hop half of MQuAKE. Where a probe is mechanically checkable ("did the
known-bad command appear in the transcript?"), no judge runs.

**The judge, guarded.** An LLM judge scores only the residual that can't be
mechanical (solution shape beyond the acceptance test), under the reliability
posture of the judge survey (arXiv 2411.15594): reference-guided grading
against a per-task rubric written at authoring time; **pairwise between arms
with position swap**, cancelling the position bias absolute scoring can't;
**arm-blinding** — retrieval output and any mention of memory stripped from
transcripts before judging, so verbosity and self-reference can't leak arm
identity; operator spot-grading of 10–20% of judgments, with the judge trusted
only on metrics where judge–human agreement is measured; judge model + prompt
frozen per campaign, a small anchor set re-run on any change so drift is
detectable rather than silent. Temperature-0 on a cheap model prices this at
cents per task; the real cost is the rubric, paid once at authoring.

**Task corpus.** Real sessions replayed where practical; a small fixed battery
of representative coding tasks where replay isn't. One declared validity
threat: a replayed session's own solution can sit in memory-on's graph, so
tasks are tagged by memory overlap (memorization vs. transferable claims) —
disclosed stratification, not a hidden confound. Paired designs (same task,
arms permuted, order randomized against learning effects), sign/permutation
tests over t-tests, and the floor-gate discipline: below the floor the report
prints "insufficient data," never a verdict. Small and honest beats large and
confounded.

Design consultation: eval-methodology, exchange
`scope:main:exchange:8644614d1b1242a4`.

**As built — the task battery.** Tasks are tier-0 operator files under
`config/tasks/<id>.yaml`, the manifest pattern extended to eval: what counts
as success is a curation decision, so it lives in git where no feed or model
can write, and the file's git history *is* the pre-registration timestamp — an
oracle edited after a campaign is a visible diff, not a silent regrade. Each
task carries the prompt, `source` (replayed with a mandatory evidence pointer,
or authored; plus the git ref the arm's worktree starts from), 1+ mechanical
`acceptance` commands, 1–3 `probes` (`transcript_regex` / `diff_regex` /
`command`, each with a mandatory `meaning` — an uninterpretable probe is
decoration), an optional judge `rubric`, and the `overlap` stratum
(`memorization` | `transferable`). `thalamus eval tasks` validates the battery
and renders it with strata counts; violations exit nonzero — the battery does
not arm until clean, and a memorization-only battery is flagged so campaign
claims stay scoped to that stratum. Seeds: two replayed memorization-stratum
tasks from the 2026-07-19 session (the reader case-sensitivity bug, the
consultation refusal conflation), their behavioral oracles validated against
the live graph before registration.

**As built — the arm runner.** `thalamus eval run <task> --arm …` executes one
battery task per arm, in the order given (the operator is the permutation):
a disposable git worktree at the task's ref; the arm realized by editing the
*worktree's* harness files — per-process arming (lab/001) works in the
runner's favor, each headless session arms from whatever its worktree
declares; a headless `claude -p` session (model / turn-cap / timeout dials;
`--full-auto` for real campaigns, since the default acceptEdits mode
auto-denies Bash and the candidate couldn't run tests); then the task's own
oracles — acceptance commands in the worktree, probes against the captured
harness transcript and the diff. One JSONL record per run appends to
`~/.thalamus/counterfactuals/runs.jsonl` (tap-then-report, like every other
instrument), carrying the applied arm verbatim — stripped hooks, MCP removal —
so the record shows the arm was real. Hygiene, both directions: **no arm
keeps a memory write-back path** (SessionEnd distillation and the trace taps
are stripped in every arm, memory-on included — an arm session distilling
would let later arms recall earlier arms' work, and never-distilled tap lines
would sit in `eval report` as pending forever), and **neutral discipline
stays on everywhere** (timestamp, gremlin-guard) so contrasts don't confound.
Built arms: `memory-on`, `memory-off`, `scoping-degraded:<scope>`;
`freshness-degraded` and `volume-degraded` are *refused*, not approximated,
until graph-snapshot pinning exists. The first live smoke run (2-turn,
memory-off) validated the plumbing and caught a probe the task's own prompt
pre-satisfied — now a mechanical battery check: a `transcript_regex` matching
the task's prompt refuses to arm. Residual, named: a memory-on arm reads the
*live* graph. It cannot write one — the MCP surface carries no live write tool,
so "no arm writes memory" holds structurally and not by convention.

**The run log is pinned by name, and re-scoring appends.** `thalamus eval corpus
--name <id>` seals `runs.jsonl` under a name that is immutable once cited: a
read-only copy beside the live log, a **manifest** of one line per run
(`run_id`, `body_sha256`, `revision`) committed to `experiments/corpora/`, and a
registry row in `experiments/corpora.jsonl` — the same split as the graph snapshot
registry, and for the same reason. `--diff <id>` reads the difference back and
separates the two things a whole-file digest reports as one bit: **appends and
supersessions are legitimate; a record that changed under its own identity is not.**
`--list` verifies the sealed copy and its manifest as *two* states, so a corpus that
still hashes to its citation with a manifest that no longer matches it cannot read as
"ok".

Identity is derived, never assigned. `run_id` digests the fields fixed when an arm is
born — `ts`, `task`, `arm`, `scope`, `ref`, `model`, `worktree`, `order_index` — so
the 140 records written before any of this existed acquire a stable identity without
the file being rewritten to add one, which would be the very mutation being ended.
Unique across the corpus as found. A Merkle tree is deliberately not used: its payoff
is proofs to a verifier who distrusts the log operator (RFC 6962), and a root hash
destroys exactly the per-record diff that makes the manifest worth keeping.

**A re-derived verdict supersedes; it never overwrites.** `thalamus eval rescore
--write` appends a record carrying the same `run_id`, one higher `revision`, and
`supersedes` holding the digest of the body it replaces, stamped with the detector or
judge fingerprint that produced it. Readers take the head revision per run
(`corpora.head_revisions`), which is why every existing analysis reads the numbers it
read before. This is not a preference: the void fix moved four fields on 23 records
and kept only a `restamped_by` marker, and the contamination pass overwrote 88
judgements that survive in neither hand-made backup (lab/038). A marker that records
*that* something changed and not *what* is not provenance.

**Every campaign record carries what its verdict was computed against.** `derivation`
stamps `task_digest` (over the YAML **bytes** — the 2026-07-29 ref remapping lives in
a comment block), `fix_ref`, the resolved `fix_paths` and their digest, and
`detector_config`. This closes lab/037 finding #5: the record used to store `ref`
alone while `contaminated` was computed from a git diff over the operator's *live*
repo, so editing a task YAML afterwards silently re-scoped every prior contamination
verdict. The boundary is that config may be re-derived only if it is a pure function
of pinned inputs **and every input to that derivation is itself pinned** — the path
set fails the second clause, which is not hypothetical: the 2026-07-29 history
rewrite changed every SHA and left both task refs dangling, remapped by hand.

**Named residual: `derivation` versions the detector and not the adjudicator.** The
contamination audit measured the half that is missing — manual adjudication
reinterpreted a verdict *without changing a single flag* (arXiv 2606.10066) — and the
8-of-88 git-reach figure has a human judgement in it. `detector_config` pins the
mechanical half only; no field carries the rubric or the adjudicator. Recorded as an
absence rather than closed.

**Pinning is not validity, and must not be read as it.** A pinned corpus with an
unablated leak channel yields a reproducibly wrong number, which is worse than an
unpinned one because it recruits the pin as evidence of rigour. The instrument that
catches an answer-key channel in a downstream probe is the **leak-ablation control**,
not the audit trail; see [11](11-related-work.md) §7f.

**Probe authoring rule** (lab/011, the first campaign's sharper finding —
every probe hit in every arm, memory-off included): a probe must target
knowledge unreachable from the prompt *plus general model competence* —
session UUIDs, lab-entry numbers, dial values, named thread slugs. The
validator mechanically refuses prompt echo; only authorship can refuse
competence echo. **First positive firing, lab/014:** `memo-surfaced` hit on
consultation/memory-on, the authoring session's UUID rendered into context by
`memory_open_threads`. Read narrowly — it surfaced as another thread's
provenance line, not as the memorized diagnosis, so the probes are now
validated as **surfacing** detectors and remain unvalidated as use signals.

**The graded oracle — an ordinal ladder, built before the harder tasks.**
Acceptance saturated at 18/18, so pass/fail cannot say whether a new task is
*harder* or merely differently broken; the instrument has to come first, and
"harder" is then a score drop it can show. Each `acceptance` check declares a
`level`, and a run's **rung** is the highest level whose checks — and every
lower level's — all pass:

- **L1** no-regression gate (the pre-existing suite stays green)
- **L2** targeted behavioral oracle for this bug
- **L3/L4/L5** nested metamorphic relations R1 ⊂ R2 ⊂ R3, each strictly stronger
  than the one below, so a further relation can only extend the top of the ladder
- **L6** reserved for the judge, deliberately unbuilt

Ordinal, not a weighted sum: there are no weights to tune after seeing results,
and adding a cheap check to a rung cannot raise the score — the cardinality bias
a weighted sum imports (arXiv 2601.03525). Test-pass *ratio* is rejected for a
more general reason than its saturation here: coverage-family metrics say
nothing about oracle quality (arXiv 2212.06118). Resolution inside a rung comes
from **nesting relations by strictness, never counting them**, which would
reimport the same bias; relations are behavioral rather than diff patterns, so
they survive refactoring and cannot reward imitating the historical fix's names.

**The circularity guard — rungs must be arm-independently reachable.** This
battery's `probes` are *manipulation checks*: they measure whether the
intervention was **delivered**, not whether it worked. `memo-surfaced` fires iff
the arm called a thalamus tool (lab/016: 0 mismatches at n=18, 0/9 on
memory-off controls) — an excellent delivery detector, and disqualifying as a
rung for exactly that reason, since a memory-off arm cannot emit a UUID it never
saw. Scoring it would make memory-on > memory-off true by construction. So
probes stay outside the score (where `accepted` already kept them), and
`Task.check()` refuses any rung whose command references the memory surface.
The general failure it guards: *an oracle rung only the treatment arm can reach
turns the experiment into a detector for its own intervention* — invisible under
a binary verdict, which is why it appears only once a graded instrument is
layered over measurements built for another purpose. `fix-name-convergence` is
out of the ladder too, on separate grounds: scoring name convergence rewards
imitation over correctness, so a better fix under a different name would score
lower.

**Anchors and mutants — validating the instrument before trusting it.** Every
replayed task names `source.fix_ref`, the commit that actually fixed the bug, so
the ladder can be graded against ground truth with no model in the loop: the
**negative anchor** is the untouched worktree at `source.ref`, the **positive
anchor** is the fix commit. The anchor pair is necessary but *not sufficient* —
the saturated binary oracle already passes it, and a test the status quo passes
cannot justify replacing the status quo; it establishes range coverage, not
adequacy in the interior where real arms live — and they do live there:
**3 of 6 graded arms landed at rung 2 or 4** (lab/018). The discrimination bar
is instead a **mutant set** (4–6 per task) derived by degrading the known-good
fix, with expected rungs committed in advance; the ladder must reproduce that
ordering. `thalamus eval oracle <task>` grades anchors and mutants together, at
zero inference cost — every candidate's quality is known by construction.

Mutants are a **gate, never a graded kill-rate**. A rate is the pass ratio under
a new name: its denominator is a set the author chose, so adding easy mutants
moves the number. Its denominator is not even well defined — **equivalent
mutants** are semantically identical to the original and unkillable by any test,
and detecting them is undecidable, so every rate carries an unknown bias. A
pre-registered rung per candidate is strictly stronger regardless: "5 of 6
killed" cannot say *which* survived, and the survivor's identity is the whole
signal. This is oracle-based test adequacy applied, not a new technique (arXiv
2212.06118, studied since 2007).

**Why these mutants and not classical operators.** The licence for treating
mutants as fault proxies is the competent programmer hypothesis plus the
**coupling effect**: mutants are coupled to real high-priority faults, measured
across ~15M of them (arXiv 2103.07189), and coupling is a quantity that can be
measured rather than assumed (arXiv 2512.16741). Both hypotheses describe *human*
programmers making small syntactic slips — and these candidates are LLM agents,
which fail differently: plausible wholesale rewrites, over-fixes touching behavior
the report never mentioned, fixes correct at one call site and absent at four. A
mutant set built from classical operators would be coupled to the wrong fault
distribution, so each mutant declares `mimics`, the observed arm behavior it
stands in for, and the declaration is enforced rather than attested. The
**equivalent mutant is a deliberate instrument** here, not a nuisance: one mutant
is a *correct* fix written differently, expected at the top rung, because a ladder
that scores it lower is rewarding imitation of the historical fix rather than
grading behavior. Undecidability does not bite — equivalence is authored, not
inferred.

**Every candidate is graded against the pre-existing suite.** L1 asks whether the
suite an arm *inherits* stays green, so `tests/` is pinned to `source.ref` for
anchors and mutants alike. Grading at `fix_ref` instead runs the tests the fix
shipped with itself, which collapses every degradation to rung 0 — L1 falls before
the ladder can say how degraded a candidate was — and, worse, fails a correct fix
that structures its helper differently, because the fix's own unit test imports
that helper by name. That is precisely the imitation reward the relations are
behavioral to avoid, arriving through the gate instead.

Anchors carry a second value
beyond validation: a probe that fires against the *negative* anchor is measuring
the repo rather than the candidate, which mechanizes lab/011's competence-echo
catch; and if the historical fix scores the same rung as every arm, the tasks
are too easy rather than the instrument too coarse — a different remedy, and
unobtainable any other way. **Anchor-based validation covers `replayed` tasks
only**; `authored` tasks have no historical fix and need metamorphic relations
instead, which is why declaring a `fix_ref` on one is refused.

Design consultations: eval-methodology, exchanges
`scope:main:exchange:c973e292d6ab45c7` → `df39a842a5ef4f27` →
`06723ce1b78345a9` (each superseding the prior where it changed).

**The battery ceiling was a binary-oracle ceiling, and grading lifted it
(lab/014–016, resolved lab/018).** Acceptance had saturated at **18/18 across
sonnet, fable, and opus over two replicates**, reading as a battery ceiling.
Graded, the same task de-saturates: half the arms land in the interior, split
between under-fix (L3 — the reported case patched, hyphenated terms still
broken) and over-fix (L5 — project matching loosened as collateral damage). The
task was never too easy; the instrument could not see where candidates fell.

**Open: candidate variance is three to four rungs wide (lab/018, lab/020).**
Under fixed model, task, and arm, rungs spread {2,5,5} on the reader task and a
full 1→5 on the session-death task across 12 replicates per side. Per-cell n=1 is
uninterpretable and campaigns must buy replicates before models or tasks; a Δ=1
effect against that dispersion needs ~43 arms/side at ~$2.30 each.

**Under-specification induces recall — measured (lab/020).** The first gated task
raised memory-on's thalamus-call rate to **5/12 (42%)** against **2/21 (9.5%)**
across every arm on the self-contained tasks, with the memory-off control clean
at 0/12. The mechanism lab/018 inferred from a two-session probe replicates. It
did **not** move the graded outcome: 3/12 vs 2/12 reaching rung ≥ 4, mean rung
2.25 vs 2.33. Retrieval behavior and task quality are separate measurements, and
only the first has moved.

**Open: under-specification lowers the floor as well as raising recall
(lab/020).** Half the arms (12/24) scored rung 1, failing the behavioral oracle;
six concluded in 12–20 turns at a third of the cost of the rest. A prompt that
withholds the constraint also withholds what counts as finished. A gated task
needs enough specification to make "done" legible without restoring the
constraint that does the gating.

**Open: the binding constraint is prompt under-specification in the battery
(lab/018).** Memory-on arms call `mcp__thalamus__*` at **2/21** — an arm-level
count that stands. The comparison it was made against does not: the
"20/31 without conditioning, 11/11 with" contrast came from a cohort built by
slug-filtering `~/.claude/projects/`, and lab/033 established that 696
extraction-sandbox project dirs lived in that directory under names the filter
never accounted for. That denominator is unverifiable and is withdrawn (lab/034);
it is re-derivable once the cohort is defined by the sandbox marker instead of by
slug. The gap is not the runner. Harness fidelity is
verified — `.claude/settings.json` is byte-identical between the task ref and
`HEAD`, the memory-on arm strips write-back hooks only, `SessionStart` injects
in 3/3 arms, and the MCP schemas load. A controlled probe holding the harness
completely fixed and varying only the prompt settles it: the battery's bug
report produces **zero** calls, a past-work question produces
`ToolSearch → memory_open_threads → memory_recall_by_project`, with conditioning
firing in neither.

Both original battery tasks are self-contained bug reports carrying symptom,
counterexample, and constraint, so **the prompt already holds the answer's
inputs** and reading the source dominates. Zero recall is correct behavior, not
a defect. This is also why `memo-surfaced` reads 0/24: it detects knowledge
"unreachable from the prompt", and nothing in those prompts is unreachable.

**Under-specification is a declared task property (lab/019).** The answer is a
task that withholds something: `under_specification` names the withheld fact,
the graph nodes holding it, the rungs it gates, and a `floor_rung` below which
the ladder must stay reachable from the prompt alone — because a fact gating the
*bottom* of the ladder makes memory-on win by construction rather than on merit.
Two claims are enforced structurally: `absence_check` is a command proving the
tree at `source.ref` cannot answer the question (prose is an assertion, a command
is evidence), and a rung listed in `gates_rungs_weak` may not be the
`attributable_outcome`, since a rung reachable without memory cannot be evidence
of memory use.

Selecting a gateable fact turns out to be the hard part, and it is a constraint
this project imposes on itself: the lab notebook lives in the repo and the code
is commented at essay density, so most decisions are recoverable from the
worktree and gate nothing. Three candidates were rejected on `absence_check`
before one survived — which is why the check is mechanical rather than asserted.

**`no_regression` retires, it does not drop.** L1 pins `tests/` at `source.ref`,
which is wrong when the correct fix changes the design those tests assert — on
the session-death task, pinning whole made *every* candidate including `fix_ref`
cap at rung 3. The exemption is pre-registered at test-node granularity, must
equal exactly the pinned tests `fix_ref` fails, and `relocated_to` names the rung
that re-asserts the retired behavior with the opposite sign.

**The rung-witness rule.** Every rung needs a candidate scoring exactly it, or
that rung is unvalidated and the observed gap is carried by some other rung. The
session-death task's mutant set supplies rungs 2, 3 and 4 between the anchors,
and the gate passes 6/6.

**Probe validity held until the environment broke it (lab/016, falsified
lab/020).** `memo-surfaced` fired **iff** the arm called a thalamus tool across
24 arms — then fired in two memory-off arms that cannot recall at all. Both had
read the task YAML out of the operator's checkout, and the probe's pattern is a
session UUID printed in that file. The probe is sound; its environment is not. A
probe searching for a token the candidate can open a file and read measures
reading, not recall. Among arms that could not reach the task file it still
behaves (4 hits, 5 callers, no false positives).

**Two answer-key leaks, both measured, both now closed (lab/020–022).** An arm
runs `--dangerously-skip-permissions`, and it used that freedom two ways:

Rates below are stamped on every record by `thalamus eval rescore`, which
applies both detectors backwards over the campaigns that ran before they
existed. Every rate is arms/arms across all six recorded campaigns; events are
given alongside because an arm that reached twice is still one reached arm.

| channel | measured | closed by |
|---|---|---|
| filesystem — absolute-path reads of the operator's checkout | 13 of 88 arms (21 events) | the container |
| **git object store** — `log --all`, `show <fix_ref>`, `rev-list --all` | **8 of 88 arms (10 events)** | the one-commit repo |

Contamination proper — an escape of either channel that reached an `answer_key`
file — is **5 of 88 arms**. The git channel is concentrated rather than diffuse:
7 of its 8 arms are the single `arm-runner-session-death-classification`
campaign, 7 of that campaign's 27.

The second was the larger and nobody was watching it. A `git worktree` shares
refs and objects with the operator's repo, so an arm could read the fix, every
lab entry describing it, and the task YAML **without naming a path outside its
own directory** — invisible to any filesystem confinement, since the object store
is exactly what git needs to run. One arm ran
`git grep -l "<task-id>" $(git rev-list --all)`; another ran
`git show 8b70330 -- tests/test_reader.py`, the reader task's own `fix_ref`,
which puts the pre-grading campaigns in scope too.

**The arm's checkout is now a repository whose history stops at `source.ref`.**
`prepare_worktree` fetches the single pinned commit at `--depth=1`, naming the
full 40-char object and enabling `allowAnySHA1InWant` on the *remote* side of the
transport so an unadvertised commit is fetchable without a temp branch or any
config left in the operator's repo. Verified on a real checkout: one commit
visible, `git show <fix_ref>` fails, the answer-key sweep returns nothing, and
the inherited suite still passes 224/224 so L1 is unaffected. This also removes
the arm's dependency on the operator's repo, which is what makes confinement
possible at all. The initial environment state is part of the instrument's
definition rather than scaffolding around it — τ-bench grades against an
annotated end state and `pass^k` presupposes an identical start state per trial,
neither of which a shared object store delivers.

**Contemporaneous leakage is refused, not patched.** Ref-limiting cannot help a
task authored *before* the commit it replays: its own battery file would sit in
the checkout. Deleting the battery was tried and is wrong — the pinned suite
asserts the battery holds ≥2 tasks, so stripping it fails L1 for every candidate,
which is lab/019's ungradeable-design defect in a new place. `refuse_self_leaking_task`
refuses instead. All three shipped tasks pass.

**`--sandbox` confines the session** (`docker/arm-runner.Dockerfile`). The arm's
checkout and a private HOME are mounted; the operator's checkout is not, so the
paths lab/020's arms read do not exist. The toolchain is *mounted* from the host
rather than baked, so the arm runs the operator's own `claude` and `uv` and the
image cannot drift. Two runtime facts, both measured rather than assumed:
bubblewrap is lighter and **does not work here** (Ubuntu's
`apparmor_restrict_unprivileged_userns=1` denies the uid map), and Docker
**Desktop** is the wrong daemon — it runs containers in a VM, so bind mounts are
restricted to configured shares and `--network host` is the VM's host, not the
operator's. The runner pins the native context. A missing image is refused, never
silently run unconfined.

The image must also be able to *run the retained hooks*, and the runner refuses
if it cannot. Only the OS layer is baked, and the first build omitted `jq` —
which every hook uses to parse its stdin payload, under `set -euo pipefail`. A
SessionStart hook that aborts does not stop the session; it simply never
injects. So the first confined memory-on arm was never told a memory surface
existed and recorded `recall_calls: 0`, a record indistinguishable from a
candidate that was offered memory and declined it. Two things break at once:
the arm's own primary outcome, and the docs/index 2026-07-19 invariant that the
neutral discipline stays on in *every* arm — hooks that do not run are not on.
`image_missing_hook_deps` probes the image for `HOOK_DEPENDENCIES` before the
first arm launches, so a dead hook layer is a refusal rather than a campaign of
plausible zeros. **Credentials** are checked the same way: the container gets
its own HOME, so the arm needs `.claude/.credentials.json` (the OAuth token) as
well as `.claude.json` (config and state), and a missing token refuses before
launch instead of dying inside the container.

**`--isolate-store` closes the memory-off store hole.** With confinement,
`--network bridge` for arms carrying no memory surface makes the graph
unreachable. This is the open question this section has carried since the first
campaign, where a memory-off session was measured querying the graph over ad-hoc
gremlin: removing the surface never removed the store. It is opt-in because it
**changes the memory-off treatment**, a second factor that must be declared in a
campaign's pre-registration.

`bridge`, not `none`. `none` isolates the store and the model API together, so
the arm dies on turn 1 with `Unable to connect to API (ENOTIMP)` and halts the
campaign — which is exactly what the first attempt at a 24-arm contrast did. The
earlier check confirmed the graph was unreachable and never asked whether the
arm could still run: a property verified about the wrong half of the system.
Re-verified at the TCP layer, because HTTP status codes say nothing useful about
a websocket port — from `bridge` the graph is closed on `localhost:8182` (the
container's own loopback) *and* on the gateway `172.17.0.1:8182`, since the
server binds loopback-only, while `api.anthropic.com` answers. From `host` it is
open, which is what the memory-on treatment needs.

**Detection survives the fix, deliberately.** An arm that reaches for
`git log --all` behaves differently from one that does not, and that difference
is data about the candidate; closing the channel silently would convert a
measured behavior into an absence. Execution provenance treats environmental
interaction as a first-class step type, so the design is **deny at the
environment, measure at the transcript** — the attempt is still a tool call, so
the 9-of-88 rate stays observable after the fix. `detect_history_reach` flags
`--all`, `rev-list`, named branches and `show <sha>` past the pinned ref, and
classifies a command naming the task's own `fix_ref` as `answer_key`; naming
`source.ref` itself is not a reach. It reproduces 8 of the 9 measured arms, the
two skipped being arms that named only their own pinned commit.

`detect_worktree_escape` reads each arm's own transcript for
tool inputs naming the operator's checkout by absolute path and stamps `escapes`
and `contaminated` on the record, on the flag-never-exclude discipline the infra
classifier already follows (§2a). Two classes: `answer_key` — a battery file, or
a file the task's own `fix_ref` changed, since the live tree carries the fix in
code as well as in prose — and `operator_repo` for any weaker escape. Which files
give the answer away is a property of the task, so `fix_touched_paths` derives
the set from `source.ref..fix_ref` rather than trusting a fixed directory list;
that distinction is what separates the two, and it was found by validating the
detector against lab/020's own arms, where a third contaminated arm had run the
live `arms.py` and been missed by hand. Re-derived over that campaign the rate is
**3 of 24**, not the 2 reported.

`contaminated` is deliberately **not** `attributable`. An infra fault means the
verdict is not about the candidate at all; contamination means it is about the
candidate but not about an *unaided* one. The first invalidates a measurement,
the second re-labels it, and collapsing them loses both. The stamp is the
pre-registered exclusion key for a per-protocol read; the intention-to-treat
comparison keeps every arm regardless, which is what lab/020 reported.

**Recall-calling is substantially stochastic (lab/016, superseding lab/015
§2).** lab/015 read a model×task interaction off one observation per cell and
proposed that under-specified tasks invite recall. Replication inverted both
sonnet cells — reader 0→1, consultation 1→0 — meeting the falsification
condition written down before the run. Within a fixed (model, task, arm) cell
the call happens or doesn't; a single campaign's recall column is one sample of
an unknown distribution, so recall-calling cannot serve as a dependent variable
until its base rate is measured. What survives: *when* a call happens it follows
the injected pattern exactly (one `ToolSearch`, then `memory_open_threads`), and
the task/arm-order confound that ran through lab/011–014 is broken by data
(memory-on ran at order 0 on reader and order 1 on consultation, and hits occur
at both).

**`recall_calls` is recorded per run** (`{thalamus, tool_search}`) — whether an
arm reached for memory is the contrast's primary outcome and previously lived
only in transcripts. `tool_search` is tracked separately because it separates
"never tried" from "tried and could not load the schema" (lab/013).

**Metric defect, fixed (lab/015).** `turn_capped` was `num_turns > max_turns`,
which marked *concluded* runs as censored: opus reports 46–53 turns against a
40-turn cap while terminating normally (`is_error=False`, real closing
summary), so the turn count and the cap are not on the same scale. The true cap
signature is errored **with an empty result** — the model never got to
conclude. Corrected rate: sonnet 3/4, fable 0/4, opus 0/4.

**Fixed bug: every campaign run before this one had an inert memory-on arm.**
`session-start.sh` resolved `project=$(basename "$cwd")` to prime session-start
recall. Outside the arm runner `cwd` is the repo root, so this resolved to
`thalamus` and worked. Inside the arm runner, the headless session's `cwd` is the
disposable worktree (`<task-id>--<arm>--<timestamp>`), so `basename` never
equalled `thalamus` and the session-start pull was scoped to a project with
nothing filed under it — confirmed from raw transcripts:
`memory_recall_by_project` returning `"No matching memories found."` in every
memory-on arm run to date (lab/011 and lab/012). Both campaigns' memory-on arms
differed from memory-off only in inert hook overhead, not in memory content;
neither campaign's numbers say anything about memory-on vs memory-off. First
campaign (2026-07-19, pre-distillation, lab/011): memory-off accepted 2/2 vs
memory-on 1/2, memory-on +52% cost, cap binding 4/4. Second campaign
(2026-07-20/26, post-distillation, lab/012, one arm-pair partially voided by an
unrelated mid-campaign OAuth expiry and re-run): memory-on 2/2 vs memory-off
0/2, cost direction mixed. Fixed (lab/012): `run_agent` now threads the
checkout's real project name into `THALAMUS_PROJECT`, which both hook variants
(`claude-code/session-start.sh`, `cursor/session-start.sh`) prefer over
`basename $cwd`/`basename $workspace_root`.

**Fix validated live, campaign discipline holds anyway (lab/013).** A worktree
checks out at the *task's* pinned ref, which also freezes the runner's own hook
scripts at whatever state existed when the task was authored — a fix landing
in the repo doesn't reach a worktree pinned to a pre-fix ref until
`sync_runner_hooks` (`arms.py:120`, called from `prepare_worktree`) overwrites
the worktree's hook-script content post-checkout (`.claude/settings.json`
stays pinned, so only already-wired scripts refresh). With both fixes in
place, transcripts confirm `SessionStart` now injects `project="thalamus"`
correctly. But in lab/013's n=2 sample, **neither memory-on arm called any
`mcp__thalamus__*` tool at all** — the first campaign where that gap was
directly observed rather than merely possible. The mechanical cause was that
the injected instruction was *incomplete*, not merely advisory: Claude Code
surfaces MCP tools by name with schemas deferred, so "call
`mcp__thalamus__memory_open_threads`" named a call the agent could not make as
written, and neither transcript contained anything explaining the discovery
step. `claude-code/session-start.sh` now names it — one `ToolSearch
select:...` loading both tools, conditionally phrased because deferral is a
per-session harness fact the hook cannot see. The Cursor variant does not
carry it (no such mechanism there); both texts are contract-tested
(`tests/test_claude_code_hooks.py`, `tests/test_cursor_hooks.py`).

**Measured, and the verdict is split (lab/014).** The fourth campaign — the
first with zero infra faults, all four arms `attributable` — delivered the
corrected instruction verbatim to both memory-on arms. One
(consultation) followed it exactly: one `ToolSearch` with the prescribed
`select:` query, then `memory_open_threads(project="thalamus")` returning real
threads — **the first arm in any campaign to actually recall real memory
content**. The other (reader) made zero thalamus calls with the identical
instruction in context. So naming the deferred-tool step was *necessary* and is
demonstrably followable; it does not make the call *happen*. Advisory context
not compelling use is now a measured property of a complete instruction, not a
suspicion about an incomplete one — and enforcement stays off the table for the
reason recall scope is server-side (docs/07), so the open design question is
what makes recall worth calling, not what makes it callable.

**A third, unrelated bug in the same campaign, found by refusing to accept
"root cause not fully pinned down" (lab/013).** Both reader arms failed `uv run
pytest -q` with `ModuleNotFoundError` despite each behavioral oracle passing —
first written up as an unexplained infra confound, correctly challenged by the
operator ("this is pretty sus"). Root cause: `pytest` is a
`[project.optional-dependencies] dev` extra, not a base dependency
(`pyproject.toml:15-20`); a fresh worktree's `.venv` only ever gets the base
set auto-synced, so `uv run pytest` finds no `pytest` in `.venv/bin/` and
silently falls through to the unrelated system `python3-pytest`, which can't
see the worktree's own installs. `sync_worktree_env` (`arms.py`, called from
`prepare_worktree`) now runs `uv sync --extra dev` in every worktree before
anything else, closing this for good — verified live (a fresh worktree at the
reader task's ref: 180 passed) and unit-tested. This bug predates lab/013 and
would have hit any prior campaign's candidate or oracle indistinguishably from
a real regression; earlier campaigns simply didn't happen to trip it.

**Infra faults are now classified, not left to be noticed by hand.** Both bugs
above cost a campaign each because the runner rendered an infrastructure fault
exactly like a candidate defect. The runner now names the difference, following
CI research on separating legitimate failures from ones the change under test
cannot explain (arXiv 2111.03382, 2605.05564 — [11 §2a](11-related-work.md)):

- `classify_infra_fault` reads the failure *symptom* — missing non-first-party
  module, collection error, exit 127 — and stamps it on the acceptance entry.
  A missing **first-party submodule** is deliberately excluded: a candidate that
  deletes `thalamus/reader.py` really did break `thalamus.reader`, and calling
  that infra would excuse a real defect. Unrecognized failures stay candidate
  defects.
- `classify_session_fault` separates the two session-death shapes lab/012 had
  to split by hand. `is_error` alone is never the signal — every turn-capped run
  carries it too — but the two shapes are decided on different evidence:
  - **`void`** is decided on *behavior*: errored, one turn or fewer, $0.00.
    That describes a session that did nothing, whatever string it printed, and
    no marker list can enumerate every way a session fails to start. The first
    confined arm proved the point by dying with `Not logged in · Please run
    /login` — an auth failure that the marker vocabulary did not contain, so it
    slipped the gate and an untouched worktree was graded RUNG 1.
  - **`interrupted`** — real work, then death — stays gated on
    `SESSION_FAULT_MARKERS`, because it is the only shape a healthy arm's own
    prose can be confused with (lab/020 stamped a healthy 49-turn arm void by
    reading its summary). An arm that did work can never satisfy the behavioral
    test, so the two gates cannot collide.

  Neither is graded, and both halt the campaign rather than launching the next
  arm against the same dead condition.
- Records carry `infra_faults` and `attributable`. Nothing is ever dropped —
  the verdict stands as measured and the stamp says whether it can be read as a
  fact about the candidate.
- `render_campaign_faults` adds the cross-arm signal a single record cannot
  see: an acceptance command failing **identically in every arm** is usually
  the harness, since the arms are different candidate sessions. Reported as
  suggestive, not conclusive — a task nobody can solve looks the same.

## Layer 2b — In-deployment measurement: the rake registry

Layer 2 authors fixtures and runs them cold in containers. Layer 2b measures the
operator's own traffic instead, where the demand is real because work was
happening rather than because a task presented it (lab/024 §2).

A **rake** is a `problem` Claim carrying a `SOLVED_BY` edge — a mistake already
made and already resolved, registered by ordinary distillation. `thalamus eval
rakes` builds the registry, decides which rakes are *observable*, and emits the
(rake, later-session) pairs an adjudicator would judge. It is stage 0 of Class A
and **claims no outcome**: a candidate is proximity, never an encounter.

Three measured properties of the corpus define the design:

- **Claim identity does not detect recurrence.** Claims are content-addressed on
  (kind, normalized description), so a re-asserted problem should converge onto
  one vertex with two `CONTAINS` edges. It fires 4 times in 575 (`SOLVED_BY`
  edges at `post-sandbox-purge-20260730`; the figure moves with the corpus and is
  rendered every run rather than quoted as a constant). A detector keyed on it
  would see ~1% of the corpus.
- **Unobservable is not "never hit."** A rake whose artifacts no later session
  touched offers nothing to observe. It is bucketed apart and never folded into
  a denominator — the discipline layer-1 attribution already applies to empty
  windows. On the live corpus that bucket is as large as the observable one, so
  merging them would roughly double any benefit number.
- **Artifact identifiers collide across projects.** `Artifact` is global and
  keyed on `identifier`, so one `README.md` vertex is shared by every project
  that touched it. Pairs are gated on the later session sharing the rake's
  originating project; the dropped pairs are counted and disclosed.

Keys touched by more than `HOT_ARTIFACT_SESSIONS` sessions are low-specificity:
"a later session opened `README.md`" is weak evidence that it met a specific
rake. Those pairs are counted apart so a handful of hot files cannot dominate
the queue — flagged, never dropped (arXiv 2111.03382), the rule the infra
classifier and the escape detector already follow.

The measurement is **observational**. It can establish recurrence rates and
their trend, never causation — that needs the randomization layer (arXiv
2009.00148 switchback, arXiv 2309.07353 anytime-valid) on top. Per lab/024 §2.5
the outcome must also be signed two-sided: a metric that counts rakes avoided
cannot observe rakes caused (arXiv 2605.17830).

### Stage 0.5 — pricing the queue before anything is built on it

Nothing in the corpus labels a rake encounter, so the queue's precision is unknown,
and an adjudicator built on it would silently inherit whatever the proximity rule's
error rate turns out to be. `thalamus eval rake-audit --draw` emits a blind
worksheet a human labels; `--score` reads it back. Grounded in
[11 §2f](11-related-work.md), four properties are load-bearing:

- **The draw is uniform over the specific-key stratum, seeded before any pair is
  read.** Judging the most convincing candidates first is active selection, which
  biases the estimate toward the system that built the pool (arXiv 1709.01709). The
  stratum boundary is `HOT_ARTIFACT_SESSIONS`, published before the sample existed.
- **The worksheet withholds the shared artifact key.** That key is the rule's own
  evidence; printing it asks the annotator to ratify the system instead of judging
  the sessions. Each item shows the problem, its solution, and what the later
  session did — never why the queue paired them.
- **Decoys are rendered indistinguishably**: in-window pairs sharing no artifact,
  drawn from the same rakes. They measure the annotator, not the queue, and a decoy
  labelled `hit` may be a real recurrence the key missed — so the decoy rate is an
  upper bound on laxity, never a false-positive rate.
- **`unclear` is a third bucket**, in neither numerator nor denominator, and the
  interval is bootstrapped over *rakes* rather than pairs, because one rake
  contributes up to eight pairs and a pairwise interval would be optimistic.

A single annotator has no inter-annotator agreement to report — the case arXiv
2606.02255 finds least documented — so what the score renders instead is the
annotator's identity, the volume, the abstain count, and the decoy rate. The
estimate prices **precision only**: it says nothing about encounters the artifact
key never registered.

Stages 1–3 are unbuilt. Stage 1 is mechanical rake classes only — `gremlin-guard.sh`
is that detector for exactly one class, and its shares-intent rule is the
load-bearing part at scale. Stage 2's adjudicator is grounded in the duplicate-
detection literature ([11 §2e](11-related-work.md)), which points it at the simple
end: aggregate similarity over the rake's whole group plus time (arXiv 2205.00212)
rather than reach for a judge, and re-validate on a rolling basis because detector
accuracy is sensitive to data age (arXiv 2212.00548). It stays blocked until stage
0.5's sample is labelled. Stage 3 additionally needs the L6 judge and the
answer-leakage audit (arXiv 2606.05037).

## Layer 2c — Did the room treatment occur? (`eval/rooms.py`, `thalamus eval rooms`)

A room arm's treatment is not "sessions were put in a room" — that is a launch flag.
It is that they *collaborated*, and the two come apart silently. A room whose members
never messaged each other is a set of solo sessions wearing a room label, and an arm
like that cannot separate **"rooms do not help"** from **"the room did not happen"**.

So this is a **manipulation check, not a score** — the standing `arms.py` gives its
consequence probes, and for the same reason: it reports whether the intervention
landed, never whether it worked. A room that fails is grounds for excluding the arm,
which must happen *before* outcomes are looked at; dropping arms after seeing them is
the peeking failure the sequential layer exists to avoid.

Two topologies from two ledgers, and the gap between them is the measurement:

- **Nominal** — who was *allowed* to talk, from the pin ledger. It carries members
  that never said anything, which is why enumeration is driven from here: a silent
  room is the only room the check can fail, and reading the roster off the guard
  ledger would make exactly that case invisible.
- **Realized** — who actually *sent*, from the `room-boundary` rows of the guard
  ledger (`{room, scope, target, branch, verdict}`), giving a directed edge list over
  member scopes. Reported as edges, volume, reciprocated pairs, density over the
  member set, and blocked outbound attempts kept apart as evidence of attempted reach.

Three limits it states rather than hides. A realized edge is a **permitted send, not
a delivery** — the guard is outbound-only and fires before the send, so name
resolution can still refuse it (lab/045); that direction of error is the safe one,
since it can only make a room look more collaborative than it was. A **room of one**
is reported as not a room at all rather than as a room that failed to collaborate,
because no pair could have collaborated. And a target that parses but names no member
is counted `unresolved` rather than admitted, since the prefix is not membership and a
phantom peer would inflate the edge set against a density denominator drawn from the
roster — kept distinct from a self-send, which is understood and correctly dropped.

**Not built:** anything that turns this into an outcome. Grading collaboration by
volume, or using realized density to *discount* correlated witnesses in
`substrate/witnesses`, would change a settled decision (docs/09 §Scope refuses to
reduce a count on room membership alone) and needs a consultation, not an inference.

## Layer 2c′ — The degraded-rendering arm (`eval/legibility.py`, `thalamus eval legibility`)

A comprehension test run only at full fidelity is **blind to contrast failure by
construction**, and room `atlas` proved it the expensive way: two dashed markers carrying
meaning shipped at 2.07:1 and 2.97:1 — under WCAG 1.4.11's 3:1 floor for non-text content
— past two reviewers, three rounds, and a cold-read instrument whose every reader received
a perfect rasterisation ([lab/056](../lab/056-the-charter-was-wrong-about-our-own-walls.md),
[lab/057](../lab/057-the-reader-who-could-not-say-which.md)). No comprehension score could
have caught them, because every reader could see them perfectly.

**The arm turns an accessibility check into a comprehension check** — which is the
finding, because for those two defects they were the same check.

**The degradation is applied to the SVG, not the raster.** Rasterising then filtering
needs an imaging stack that the runtime dependency set deliberately does not carry; the
source transform needs none, is exact rather than resampled, and leaves a variant that can
be diffed. It then renders through whatever already renders the original.

**The factor is derived, not picked.** Relative luminance is linear in the linearised
channels, so compressing every channel toward the surface compresses the luminance
difference by the same factor. Requiring a pair at threshold `T` to land on a legibility
floor `F` gives `a = (1/F − 1)/(1/T − 1)` — the surface term **cancels**, so one number
degrades any aid. At `T=3.0, F=1.5` it is exactly `0.5`, and the arm becomes a *threshold
amplifier*: contrast above the criterion survives, contrast below it is pushed under the
floor. The two real defects land at 1.35:1 and 1.50:1 against a corrected 1.62:1.

**Both criteria are carried, because the room checked one and missed the other.** Roles are
read off usage rather than declared — `text` (1.4.3, 4.5:1) from `<text>` elements and the
inherited root fill, `meaningful` (1.4.11, 3:1) from anything with `stroke-dasharray`,
`decorative` otherwise with no floor. A colour that fails against the surface but would
clear its threshold against another fill in the file is reported **indeterminate** naming
that fill, not as a failure: white text on a dark chip is correct and reads as a 1.07:1
catastrophe if the page canvas is assumed, and an instrument that cries wolf is one nobody
runs.

**Validated by mutation and then by a reader.** `--mutate <colour> <ratio>` re-shades one
marking to sit at exactly a chosen contrast, which gives ground truth by construction —
"the degraded reader missed it" is unfalsifiable on its own. Two readers were then given
the same aid, same prompt, same spawn, differing in one colour: the reader on the corrected
artifact named the marked tiers correctly, and the reader on the mutant reported that it
could see two treatments but **explicitly could not say which tiers carried them**. Its
first instinct named the wrong pair.

Greyscale is a **separate arm**, deliberately: it holds luminance fixed so what it tests is
only whether hue was load-bearing. Composing the two would make a failure unattributable.

**What it does not claim.** It is a screening instrument keyed to a published threshold,
not a simulation of any particular person's vision, and `report()` prints the arithmetic so
the claim can be disputed rather than trusted. A reader who loses a distinction has shown
that the distinction was carried by contrast the threshold does not protect — no more.

## Layer 2d — Cluster inference: the test, and whether the design can reject at all

When the treatment is assigned to a **group** rather than a run — a room, a switchback
window — the group is the unit, and the anchored literature (feed `cluster-inference`)
says the usual tools break exactly there: with one or a few *treated clusters*,
cluster-robust t- and Wald tests over-reject severely, cluster-robust standard errors
are biased **downward**, and the wild cluster bootstrap fails in the same corner. The
held recommendation is **randomization inference** (`eval/randomization.py`), which
tests the sharp null by re-dealing the treatment across clusters and ranking the
observed statistic in that distribution. No standard error is estimated, which is why
it does not inherit the bias.

**The design floor, which is the part worth internalising.** The reference distribution
has one entry per possible assignment, so an exact two-sided p-value cannot fall below
`2 / n_assignments` in a balanced design (every assignment's complement is also an
assignment and yields the negated statistic) or `1 / n_assignments` in an unbalanced
one. Consequences, and they are arithmetic rather than further empirical claims:

| clusters | split | assignments | smallest attainable p |
|---|---|---|---|
| 3 | 1/2 | 3 | 0.333 |
| 6 | 3/3 | 20 | 0.100 |
| 7 | 3/4 | 35 | 0.029 |
| 8 | 4/4 | 70 | 0.029 |

So **seven clusters is the smallest campaign that can produce p ≤ 0.05 at all**, and a
*perfectly clean* six-cluster separation still reads p = 0.10. `feasible()` answers this
before a campaign is run, while the shape is still free to change; `thalamus eval
randomize` exposes it with no arguments.

**Two guarantees, reported side by side and never merged.** The RI p-value is exact at
**one** look, and recomputing it as each cluster lands is the peeking failure lab/023
demonstrated first-hand. Anytime-valid monitoring comes from `sequential.py`'s Robbins
confidence sequence, whose interval is valid at every *t* simultaneously —
`randomization.monitor()` is its caller. A sequential *randomization* test is a real
construction this project does not hold the literature for, so the two are presented
separately rather than combined into one number implying a guarantee neither gives.

Monitoring an unpaired design (clusters are treated or not, so there is no per-cluster
difference) runs a sequence per arm and reports both intervals. **Non-overlap is a
conservative signal, not a test of the difference** — two intervals can overlap while
the difference still excludes zero, so the error costs power and never buys false
confidence.

## Layer 3 — Memory that measures itself (M4+)

Close the loop: utility signals feed back into graph maintenance.

- Nodes that are repeatedly **retrieved-but-ignored** decay toward archive —
  layer 1b's waste ranking is the candidate queue.
- Nodes whose use correlates with good outcomes gain retrieval weight.
- Stale literature (superseded versions, dead links) gets flagged for re-ingestion
  or demotion.
- Decay is **archival, never deletion** — utility-driven forgetting must be
  reversible and auditable via the master plane. Every archive verdict carries
  the trace IDs of the retrieved-but-ignored evidence that justified it, so each
  decision is one drill-down from its justification.

**Grading the policy without Goodharting it.** "Ignored-rate went down" is won
by retrieving nothing, so the policy is graded by downstream error instead: a
**resurrection** — an archived node recalled back by real demand — is a
countable false-forget event, the reopen-rate analog of the thread-staleness
design below. With tiny samples the honest statistic is censored and
survival-style: a node archived at time t is "correct so far," not "correct,"
and the report counts node-months of archive exposure against resurrections
rather than fabricating rates from single-digit counts.

**Prior work, and the inversion.** Forgetting-curve decay is established:
MemoryBank (arXiv 2305.10250, in the graph) reinforces a memory *because it was
recalled* and fades unrecalled memories with elapsed time — Ebbinghaus applied
to agent memory. Layer 3 keys on retrieval **outcome**, not retrieval
occurrence: a node retrieved often but never used accelerates toward archive
exactly where recall-count reinforcement would strengthen it. That inversion is
the utility-driven divergence claimed provisionally in
[11-related-work.md](11-related-work.md) §4. What it trades away: utility
verdicts exist only for retrieved nodes, so a pure utility policy leaves
never-retrieved nodes immortal — MemoryBank-style time decay survives as the
fallback prior for that no-signal population, a dial like the rest.

This generalizes the refresh-skill maintenance scheme into a principled,
**utility-driven forgetting policy**: a memory system with a learned forgetting
policy grounded in downstream agent outcomes.

## Per-expert utility: grading the roster

Aggregating layer-1/2 signals per expert answers questions no memory demo can:

- Is this expert earning its keep, or is it a graph that likes being built?
- Was pinning this expert to that session right? (Sustained low-utility retrieval
  under a pin grades **pin quality** — the feedback that replaces a learned router;
  see [02-expert-subgraphs.md](02-expert-subgraphs.md).)
- Do consultations to expert X produce used answers? (Grades the exchange graph.)
- Null-hypothesis test for roster growth: if a candidate domain's retrievals don't
  cluster and out-perform "leave it in an existing expert," it isn't an expert.

**As built:** `thalamus eval pins` renders the routing signal per expert — pinned
utility (per session, worst waste first) beside consulted utility (the expert's
nodes served into *other* scopes' traces). **The verdict line is suspended.** The
disambiguation it implemented — pinned low while consulted high reads "the pin was
wrong" — compares a within-scope rate to a cross-scope one, and the judge scores
~63% within a project against ~5% across (experiments/001), so cross-scope service
is vocabulary-distant by construction and the pattern is the artifact rather than
the finding. It renders both numbers and declines to interpret them until each side
carries its own permutation null. The old threshold made it worse: `used% < 50`
sat *below* the ~57% permuted null, so the "low" branch was unreachable and every
"healthy" verdict was unfalsifiable. The signal line is floor-gated (≥10 attributed nodes
on each side, a dial like the rest): below the floor it says "insufficient data"
rather than pretending a verdict, because no-unmeasured-claims applies to the
routing signal too. Ledger pins are engagement-gated before they count against an
expert: the roster spawns every pinned session at bring-up, so a spawn record
alone is infrastructure churn, not a routing decision. A session becomes
*engaged* at its first user prompt (`pin-engaged.sh`, an event line in the same
ledger); engaged sessions that never landed a trace are counted and named — a
pinned expert nobody's question ever touched memory for is itself a signal —
while idle spawns are disclosed as an exclusion, never judged. First-prompt is a
dial, not a truth (automated prompts count as engagement), and
engaged-but-traceless can lag distillation; both counts are attribution only
(semantics: consultation `scope:main:exchange:63b647977a624b85`).

Verdicts surface on the master plane next to the graphs they grade — rendered
live by the Pulse dashboard ([03-master-plane.md](03-master-plane.md)).

## Discipline

- **No unmeasured claims.** Until layer 2 runs, the honest sentence is "instrumented,
  measuring" — never "it makes the agent better."
- Publish negative results in the lab notebook. "The literature expert's retrievals
  were ignored 70% of the time until X" is more valuable — to the design and to the
  portfolio — than a clean win.
- **Every measurement program checkpoints its result back.** Consult → build →
  return with results → correct. The grounding consultation happens before the work
  and can only check the plan; a second ticket carrying the actual figures and the
  method that produced them is the only step that checks the thing that was built.
  It costs one extra ticket, and the checkpoint that established the rule found four
  errors in a result that would otherwise have shipped. Send the numbers, not a
  summary of them — an expert cannot check a conclusion it is only told about.
- **A rate is rendered with a null and an interval, or with a stated reason it has
  neither** (`eval/rates.py`). Below n=20 the counts render and the percentage does
  not: every campaign here is 6–10 arms, where the convention is the exact paired
  test, and a percentage on n=6 is what travels.

## Open questions

- Graph-snapshot pinning — the prerequisite the freshness- and volume-degraded
  arms are refused without, and the fix for the memory-on residual (arms
  currently read the live graph).
- Store isolation for memory-off — the arm removes the *surface* (MCP + hooks),
  not the *store*: the live graph stays reachable from any arm via ad-hoc
  gremlin over Bash (measured in the first campaign — a memory-off session
  queried it). Graph-derivable facts therefore never discriminate arms; true
  store isolation needs the endpoint blocked, which is network-level work.
- Campaign analysis — runs.jsonl holds per-run records; the paired,
  per-stratum report (sign/permutation tests, floor-gated verdicts) is not
  built, and no cross-arm claims exist until it is. Layer 2d supplies the
  cluster-level test and the anytime-valid sequence, but nothing reads
  runs.jsonl into them: the join from per-run records to a cluster-level outcome
  vector is the missing piece, not the inference.
- Judge scoring — rubrics are recorded in the battery and unused; the guarded
  judge (pairwise, arm-blinded) is not built.
- Battery growth: both seeds are memorization-stratum; transferable-stratum
  tasks must be authored before any campaign can claim beyond memorization.
- Open-thread staleness (designed, not built — lab/009, consultations
  `2e0f6a574658470a` and `fad034208c1c44cf`): an eval-sync sweep over *every* open
  thread, matching thread slug **and its named artifacts** against session summaries
  in all scopes, restricted to a temporal window after thread-open, proposing
  cross-scope RESOLVES *candidates*. The load-bearing rule is the
  **detection/adjudication split**: the detector may be cheap and noisy, but the
  closer is evidence-anchored — a RESOLVES edge is written only with a citation to a
  specific provenance vertex and, where the confirmation is external, the confirming
  actor. **The judge proposes; it never closes**, because false-close via lexical
  collision or temporal coincidence is the failure that bans auto-close outright; and
  the detector's own candidate precision is meta-evaluated against human adjudication
  before its ranking is trusted. Graded by resolution latency (not raw age) with
  still-open threads as censored observations, and re-open rate as the Goodhart guard
  against the pressure the staleness flags themselves create. Thread resolution is a
  consequence-level fact in MQuAKE's sense (arXiv 2305.14795): a thread can be
  perfectly recalled as "open" while the entailed consequence of another scope's
  evidence — "this should close" — goes unevaluated.

  Two things the build must clear first. `RESOLVES` is declared
  `may_cross_scope=False` and conformance enforces it, so the cross-scope edge this
  sweep exists to write is currently illegal — the federation call is part of the
  design, not a detail after it. And the closer's own quality signal is only as good
  as attribution: 84% of `used=true` verdicts on Thread `RETURNS` rest on lexical
  overlap alone, so retrieval counts do not measure whether a thread earned its place.
- Attribution refinement: when does lexical matching mislead, and is an LLM-judge
  pass worth its cost/noise?
- Sample efficiency: a single operator generates limited sessions. Lean on paired
  designs (same task, arms swapped) over volume.
