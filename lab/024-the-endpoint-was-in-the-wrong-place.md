# 024 — The endpoint was in the wrong place, and the battery is the wrong instrument

**Date:** 2026-07-27 · **Component:** eval loop layer 2 → a proposed layer 2b ·

> **Erratum (2026-07-30).** Figures in this entry are withdrawn or bounded by [lab/034](034-the-corrections-the-instrument-forced.md); see its withdrawal list before citing anything here.
**Status:** two things — (§1) an **interim, exploratory** observation from the
lab/023 campaign while it was still running, and (§2) a **design proposal** for
in-deployment measurement, written for `main` to build. Nothing in §2 is built.

Grounding consultation: exchange `scope:main:exchange:777773c9b77e478d`
(literature expert, 14 validated citations).

---

## §1 — The interim observation

At 19 of 24 arms, with the campaign still running:

| Endpoint | memory-on (n=10) | memory-off (n=9) |
|---|---|---|
| rung ≥ 4 — **the pre-registered endpoint** | 1/10 | 0/9 |
| rung ≥ 3 | 7/10 | 2/9 |
| rung ≥ 2 | 8/10 | 2/9 |

Rungs, in order: on `[3,1,3,3,3,3,1,2,5,3]`, off `[1,1,1,1,3,1,3,1,1]`.
P(on > off) = 0.789; exact one-sided permutation test on U, p = 0.0154.

**What this says.** lab/023 pre-registered "share of gradeable arms reaching rung
≥ 4" for comparability with lab/020. On this data that endpoint reads 1/10 vs 0/9
— indistinguishable from nothing. The separation is real but it lives at the
**1 → 3 boundary**: memory-off piles up at rung 1 (7 of 9), memory-on clears L2
and L3 and sits at rung 3 (7 of 10). The pre-registered threshold sits above the
rung where the treatment acts and cannot see it.

This is the same failure the open thread `ordinal-metric-sign-reversal-open`
records from lab/020 — the threshold metric, the mean, and the rank-based read
disagreeing — now observed a second time, in the opposite direction from the
first, and this time with the threshold reading *null* where the rank test reads
*effect*.

**What this does NOT say, and the discipline matters more than the number.**

- **This is a peek at an incomplete campaign.** The p = 0.0154 is *exploratory*.
  The rank test was selected after seeing the rungs; under the fixed-horizon
  design lab/023 pre-registered, choosing the statistic post hoc is the
  garden-of-forking-paths and the number carries no confirmatory weight. It is a
  hypothesis, not a result. Report it as such or not at all.
- **It is also the argument for §2.4.** The peek happened because a human looked
  at a live dashboard, which is what humans do. A design whose validity depends
  on not looking is a design that will be violated. That is a property of the
  *method*, not of the operator's discipline.

> **Amendment, four arms later — the peek decayed while this note was being
> written.** At 23 of 24 arms: on `[3,1,3,3,3,3,1,2,5,3,1,3]`, off
> `[1,1,1,1,3,1,3,1,1,3,3]`. P(on > off) fell 0.789 → **0.693** and the exact
> one-sided p rose 0.0154 → **0.0589**. rung ≥ 3 is 8/12 vs 4/11; rung ≥ 4 is
> still 1/12 vs 0/11. Two late memory-off arms reached rung 3 and took most of
> the separation with them.
>
> Nothing was wrong with the earlier computation — it is what the data said at
> arm 19. That is precisely the hazard: **a fixed-horizon design monitored
> continuously produces a statistic that wanders, and whichever moment you look
> is the moment you are tempted to report.** Had the campaign been stopped at 19
> arms on the strength of p = 0.015, this note would have recorded an effect the
> full run does not support. The project has now generated its own worked
> example of why `arXiv:2309.07353` (§2.4) is the right instrument — a confidence
> sequence is valid at *every* peek, including the tempting one. Cite this
> paragraph, not the citation, when arguing the change.
- **Censoring still binds.** 12 of the 19 arms are `turn_capped`. The endpoint
  remains "rung reachable within 40 turns."
- Cost so far: $44.49 for 19 arms.

**For main.** Do not amend lab/023's pre-registration to match this — that is
exactly the silent-regrade the tier-0 task-file discipline exists to prevent. Let
the campaign finish and report the pre-registered endpoint as the primary result,
*with* the rank-based read reported beside it and labelled exploratory. Then
pre-register the rung ≥ 3 endpoint, or a rank statistic, for the *next* campaign
and let fresh data decide.

---

## §2 — The battery is the wrong instrument for the project's own thesis

docs/04 states the differentiator: the offline benchmarks are "fixed dataset,
external grader, run once," and Thalamus's contribution is "a **live,
in-deployment, self-maintaining loop** over the operator's own sessions." The
battery as built is the offline half. It authors fixtures, runs them cold in
containers against a fully-autonomous agent, and grades with an external ladder —
a faithful reimplementation of the thing docs/04 says we *extend*.

The literature consult sharpened this rather than softening it.
`scope:literature:claim:9f8a7ea52c8519e9` — Mem2ActBench "*simulates* persistent
assistant usage." `scope:literature:claim:33eea799487ccdfa` — MemoryBank took its
qualitative claims from real user dialogs and its **numbers** from LLM-simulated
ones. **No held work derives a quantitative utility estimate from live traffic.**
That is not a gap we are failing to fill; it is the one asset we have that the
field does not.

### 2.0 — What already exists, so this is not a rewrite

| Substrate | Count | Writer |
|---|---|---|
| Sessions (2026-06-17 → 07-27) | 120 | `thalamus extract` |
| `problem` / `solution` Claims; `SOLVED_BY` edges | 537 / 489 / 486 | distillation |
| `decision` Claims; `SUPERSEDES` edges | 631 / **3** | distillation |
| Archived transcripts | 125 (209 MB) | content-addressed archive |
| Guard events (171 pass / 39 block, 43 sessions) | 210 | `gremlin-guard.sh` |
| Attributed retrieval verdicts (60.2% used) | 1,895 | `eval sync` |
| Pin ledger (110 sessions, 66 engaged) | 176 | `session-start.sh` |

Every node carries `ingested_at`, so **memory-state-as-of-time-T is
reconstructible**. That single property is what makes an in-deployment
counterfactual possible without a container.

### 2.1 — Class A: rake recurrence

A **rake** is a `problem` Claim carrying a `SOLVED_BY` edge — a mistake already
made and already resolved. There are 486 of them, and they were registered by
normal distillation, not by anyone authoring a task.

Real rakes from this repo's own history: `--network none` cutting the model API
alongside the store (lab/023); hook scripts needing `jq` in the arm image
(lab/023); gremlin traversals built but never terminated; the MCP server arming
per *process* so `/clear` is not enough; dialect slips between gremlin-lang and
gremlin-python.

**Outcome, four-way per encounter:** never hit / hit and recovered via recall /
hit and recovered by rediscovery / hit and not recovered.

Framed as an **obligation discharged or violated**, not a score — AOEP-v0
(`scope:literature:claim:db78a71b570e17ce`) scores state-mutation and recovery
obligations rather than answer quality alone.

**The prototype already ships.** `gremlin-guard.sh` is a rake detector for
exactly one rake class, with 210 real events and a `rescue_rate` that requires a
corrected retry *sharing intent* (≥2 shared traversal steps) rather than any
later passing command — tightened deliberately, per verification consultation
`8f6ad2d6f4024b2c`, because wrapper/textedit passes would saturate the metric.
Class A is that pattern generalized from 1 rake to 486. The shares-intent rule is
the load-bearing part and gets *more* load-bearing at 486, not less.

Why it beats a container arm: the demand is real. The rake was encountered
because work was happening, not because a fixture presented it.

### 2.2 — Class B: decision durability

**631 decision Claims. 3 `SUPERSEDES` edges.** CLAUDE.md states the decision log
is binding and must not be re-litigated without new evidence. That is a declared
obligation with a measurable violation, and nothing currently measures it.

The vocabulary is already in the graph:
`scope:literature:claim:72bf894dd6f0edfb` gives six diagnostic axes — authority,
scope, mutability, provenance, recoverability, actionability. **A closed decision
is an item with high authority and low intended mutability**; a re-litigation
metric reads mutability violations against declared authority.
`scope:literature:claim:86b33e929db69138` puts task ledgers, commitments and
audit records inside the system boundary as first-class operative state, which is
what licenses treating "the record it already made" as gradeable.

**Detection sketch.** A session emits a decision Claim on a topic where a closed
decision exists, reaching a different outcome, with no `SUPERSEDES` edge written
and no new evidence cited. **The legitimate reversal — new evidence, `SUPERSEDES`
written — is the PASS case.** Getting that sign right is what keeps the metric
from punishing the operator for learning.

### 2.3 — Class C: held-out session replay

The class that most resembles how the operator actually works, and it keeps the
counterfactual arm structure while discarding the authored fixtures.

For a real session S at time T the system holds: **the prompt actually typed**,
the graph as of T (via `ingested_at`), and what actually happened (transcript,
diff, resulting Claims). Replay the real prompt against memory-as-of-T versus
no-memory. The task distribution becomes the operator's own.

**The load-bearing design constraint.** Do *not* convert history into "what did
we decide about X." `scope:literature:claim:7e9f8d11227e502f` names passive
retrieval in response to explicit questions as the failure mode, and
history-derived questions default to exactly that shape. Real prompts do not —
they are work requests where memory is *instrumentally* useful. KnowU-Bench
(`arXiv:2604.08455`, **held**) is the nearest published statement of the
principle: hide the profile, expose only behavioral logs, force inference rather
than lookup — and it reports the bottleneck is preference *acquisition*, not task
execution. Its own interaction is simulated, so it supplies the principle, not a
precedent for live measurement.

**The validity threat: circularity.** Whatever generates the task read the same
history that holds the answer. Per docs/11 §4 phrasing this is **not found in the
2026 scan** as a named threat for generator-shares-provenance-with-grader
designs. Two mitigations the scan did surface:

- Mem2ActBench's transferable contribution is the **audit step, not the
  generation trick** — `scope:literature:claim:c9367ddb558b1815`, 400 tasks with
  91.3% human-confirmed memory-dependence. Hand-confirm a sample.
- `arXiv:2606.05037` (**held**) carries a concrete answer-leakage audit, shipped
  as `audit_prompt` CI infrastructure, covering validator-message leaks where the
  grader's own plain-English field carries the fix. Its sharpest datum: the
  paper's headline comparison **only holds after the audit** — the leak was large
  enough to invert a result. **The existing battery is wide open to that class**
  — the L2–L5 assertion strings in
  `arm-runner-session-death-classification.yaml` are prose the candidate reads on
  failure.

### 2.4 — The statistics have to change with the tasks

n = 12 fixed-horizon campaigns with a pre-registered threshold are the wrong
instrument for one operator with 120 sessions. The literature scope returned
**not found in the 2026 scan** for switchback, interrupted time series, N-of-1
and anytime-valid inference alike — a genuine hole, but unlike the Hernán &
Robins / Whitehead problem in docs/11 §4 a *procurable* one. **Both anchors below
are now held** (`eval-methodology`, feed `campaign-statistics`).

- **`arXiv:2309.07353` — anytime-valid inference in N-of-1 trials.** The single
  best fit for the stated constraint: one unit, sequential, no fixed horizon,
  valid under continuous monitoring. It dissolves §1's peeking problem as a
  matter of design rather than willpower, and it dissolves the underpowered-
  campaign problem — evidence accumulates indefinitely instead of being spent in
  $54 chunks.
- **`arXiv:2009.00148` — switchback experiments** (Bojinov, Simchi-Levi, Zhao).
  Randomize memory-on/off per *session* in live work. The threat is carryover: a
  memory-off session still *writes* to the graph and later memory-on sessions
  inherit it. Carryover in time is what switchback designs exist to handle. Pair
  with `arXiv:2606.03012`, "Powerful Switchback Experiments — Or Not?", as the
  skeptical read.

### 2.5 — The finding that could invert Classes A and B

**`arXiv:2605.17830` — "Remembering More, Risking More: Longitudinal Safety Risks
in Memory-Equipped LLM Agents"** — **held** (`literature`, feed `thalamus`), and
the ingest confirmed it is *stronger* than the scan summary. Memory-enabled
agents consistently exceed a NullMemory baseline in violation rate; the rate
shows a robust upward trend as accumulated exposure grows; the measurement
instrument is a trigger-probe protocol evaluating a fixed probe set against
accumulating real memory. Crucially, **order-randomization experiments** identify
what drives the degradation — which makes this a constraint on how this project
randomizes its own arms, not only on what it expects to find.

It points opposite to this project's prior, and it changes how Classes A and B
must be built:

1. **Sign the metrics two-sided.** Recurrence and re-litigation must be able to
   report *harm*, not merely absent benefit. A metric that counts rakes-avoided
   cannot observe rakes-caused.
2. **Stratify by exposure.** The graph grew to 4,358 vertices in six weeks. If
   the effect is exposure-dependent, pooling June and July sessions averages over
   the exact gradient carrying the finding. `ingested_at` already supports the
   cut.
3. **It offers a third reading of the lab/020 and lab/023 nulls** — not only "the
   instrument is blunt," but "benefit and contamination are cancelling." The
   current design cannot separate those. An exposure-stratified in-deployment
   metric can.

This is worth procuring whether or not any of Classes A–C ship.

### 2.6 — Ingest queue — **done 2026-07-27, all five held**

Per docs/06: anchor first, dry-run the title check before `--write`. All five IDs
came from search-result summaries rather than from the papers; **all five
dry-runs resolved to the intended document**, so the mis-resolution failure mode
docs/10 records did not fire this time. Contract check clean afterwards (4,623
vertices / 11,028 edges).

| Paper — verified title | Scope / feed | Feeds |
|---|---|---|
| `2009.00148` Design and Analysis of Switchback Experiments | eval-methodology / `campaign-statistics` | §2.4 — batch anchor |
| `2309.07353` Anytime-valid inference in N-of-1 trials | eval-methodology / `campaign-statistics` | §2.4 |
| `2606.05037` Self-Reflective APIs: Structure Beats Verbosity for AI Agent Recovery | eval-methodology / `eval-leakage` | §2.3 + the existing battery |
| `2605.17830` Remembering More, Risking More | literature / `thalamus` | §2.5 |
| `2604.08455` KnowU-Bench | literature / `thalamus` | §2.3 task shape |

**Three things the ingest changed, beyond confirming the IDs:**

1. **`2309.07353` is a better fit than claimed.** It does not merely tolerate
   sequential monitoring — it "permits interim peeking of results" as an explicit
   property of its potential-outcomes framework, and reports that peeking can
   yield *shorter, lower-risk* trials. §1's peek is the failure mode this paper
   is built for.
2. **`2606.05037` is not primarily a leakage paper**, and the procurement should
   be read accordingly: it is an API-design paper whose *secondary* contribution
   is the audit. The reusable part is concrete — the authors shipped
   `audit_prompt` as CI infrastructure for detecting answer leakage — and one
   extracted finding is directly load-bearing here: the structured-vs-plain-English
   comparison **only holds after the audit**, i.e. the leak was large enough to
   invert a headline result. That is the argument for auditing this repo's own
   L2–L5 assertion prose, not a general caution.
3. **`2604.08455` does not weaken docs/11 §4's absence claim.** It calls itself
   an *online* benchmark, but the interaction comes from an LLM-driven user
   simulator over structured profiles — simulated, not live traffic. The
   hide-the-profile principle §2.3 cites it for holds; the claim that no held work
   derives quantitative utility from live traffic also holds.

**Secondary queue, unchanged and still unheld:** `arXiv:2603.25973` (MemoryCD —
verify the "real histories" claim on ingest), `arXiv:2606.03012`,
`arXiv:2602.11243`, `arXiv:2508.00751`.

Secondary, if the above land well: `arXiv:2603.25973` (MemoryCD — claims *real*
user interaction histories; verify that word on ingest), `arXiv:2606.03012`,
`arXiv:2602.11243` (may contain the closest thing to a name for repeated failure
modes), `arXiv:2508.00751` (interleaving + counterfactual estimation in one
deployed system — the only arXiv-reachable bridge to the IR interleaving
tradition; the canonical interleaving papers are ACM/institutional and
allowlist-blocked, same procurement class as Hernán & Robins).

---

## What main should pick up, in order

1. **Let lab/023 finish.** Report the pre-registered rung ≥ 4 endpoint as primary;
   report the rank-based read beside it, labelled exploratory. Do not amend the
   pre-registration retroactively.
2. **Ingest the five in §2.6**, dry-run first. `2309.07353` and `2605.17830` are
   the two that change decisions.
3. **Class A first.** It has a shipping precedent (`gremlin-guard.sh`), needs no
   new plumbing, reads substrate that already exists, and is observational — no
   arms, no containers, no per-arm dollar cost.
4. **Class B second.** Cheapest possible version: report the count of
   re-litigations found, with `SUPERSEDES`-written as the pass case. 631 decisions
   against 3 SUPERSEDES edges is either a very obedient operator or an unmeasured
   failure mode, and today nobody knows which.
5. **Class C only after the leakage audit exists**, because it inherits the
   circularity threat and the mitigation is the audit.

## Threats to this proposal, stated before it is built

- Classes A and B are **observational**. They can establish recurrence rates and
  their trend; they cannot establish that memory *caused* a change without the
  §2.4 randomization layered on top. Do not let a recurrence dashboard become an
  unlabelled causal claim.
- Class A's rake registry is only as good as distillation's `problem`/`SOLVED_BY`
  extraction, which has never been audited for precision or recall. A rake the
  extractor missed is a rake the metric will score as "never hit."
- The `used` verdict feeding any Class D join is lexical overlap at two arbitrary
  thresholds (`MIN_MATCHED_TERMS=2`, `MIN_MATCHED_RATIO=0.3`) and is explicitly
  not a utility claim (`report.py:9-10`). It is a covariate, never an endpoint.
- All of §2 is **not found in the 2026 scan** as a published design. Per docs/11
  §4 that is provisional and weak evidence — the first thing to re-check on the
  next scan, not a novelty claim.
