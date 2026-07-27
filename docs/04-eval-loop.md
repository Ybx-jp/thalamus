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

Used-vs-ignored attribution starts crude (lexical/structural matching between
retrieved content and the session's outputs, judged post-hoc) and that is fine —
a crude measure beats no measure, and refining attribution is itself lab-notebook
material. Traces land as episodic memory (the trace store **is** a property graph),
so the eval loop needs no side database: it reads the same substrate it grades.

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

## Layer 2 — Counterfactuals (M4)

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
*live* graph and could write via `memorize`.

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
adequacy in the interior where all 18 observed arms live. The discrimination bar
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

**Open: the battery, not the runner, is the bottleneck (lab/014, confirmed
lab/015–016).** Acceptance saturated at **18/18 across sonnet, fable, and opus
over two replicates** — a battery ceiling, not a model ceiling, so no memory
contrast has anywhere to appear at any capability tier. Harder tasks or a graded
oracle must precede any further campaign spend.

**Probe validity, the sturdiest result so far (lab/016).** Across 18 valid arms
`memo-surfaced` fired **iff** the arm called a thalamus tool — zero mismatches,
zero false positives, and all 9 memory-off control arms silent.
`fix-name-convergence` stayed **0/18**: surfacing is well measured, memo *use*
is still unevidenced anywhere.

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
- `classify_auth_fault` separates the two credential-death shapes lab/012 had
  to split by hand: an expiry on the closing turn leaves a real worktree the
  oracles can still grade (stamped, graded, campaign stopped), while an expiry
  before any work leaves nothing (1 turn, $0.00 — stamped `void`, *not* graded,
  campaign stopped). `is_error` alone is not the signal; every turn-capped run
  carries it too. `AuthFault` halts the campaign rather than launching the next
  arm against dead credentials.
- Records carry `infra_faults` and `attributable`. Nothing is ever dropped —
  the verdict stands as measured and the stamp says whether it can be read as a
  fact about the candidate.
- `render_campaign_faults` adds the cross-arm signal a single record cannot
  see: an acceptance command failing **identically in every arm** is usually
  the harness, since the arms are different candidate sessions. Reported as
  suggestive, not conclusive — a task nobody can solve looks the same.

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
nodes served into *other* scopes' traces). Pinned low while consulted high reads
"the pin was wrong"; both low reads "the expert needs work" — docs/02's
disambiguation, mechanical. The signal line is floor-gated (≥10 attributed nodes
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
  built, and no cross-arm claims exist until it is.
- Judge scoring — rubrics are recorded in the battery and unused; the guarded
  judge (pairwise, arm-blinded) is not built.
- Battery growth: both seeds are memorization-stratum; transferable-stratum
  tasks must be authored before any campaign can claim beyond memorization.
- Open-thread staleness (designed, not built — lab/009, consultation
  `2e0f6a574658470a`): an eval-sync sweep proposing cross-scope RESOLVES
  *candidates* (detector may be noisy; the closer must cite specific evidence —
  nothing auto-closes), graded by resolution latency with still-open threads as
  censored observations and re-open rate as the Goodhart guard. Thread
  resolution is a consequence-level fact in MQuAKE's sense (arXiv 2305.14795):
  a thread can be perfectly recalled as "open" while the entailed consequence
  of another scope's evidence — "this should close" — goes unevaluated.
- Attribution refinement: when does lexical matching mislead, and is an LLM-judge
  pass worth its cost/noise?
- Sample efficiency: a single operator generates limited sessions. Lean on paired
  designs (same task, arms swapped) over volume.
