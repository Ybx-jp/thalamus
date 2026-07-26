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
competence echo.

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
(`tests/test_claude_code_hooks.py`, `tests/test_cursor_hooks.py`). Whether
this closes the gap is unmeasured — a corrected instruction still cannot
compel use, and enforcement remains off the table for the same reason recall
scope is server-side (docs/07). No campaign to date has produced an arm that
actually recalled and used real memory content; the graph-only-token probes
remain only negatively validated (correctly silent so far), never positively.

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
