# CI Failure Triage — the loop, the boundary, and what is allowed to go quiet

**Status:** design; the loop is not built. The one part that is built is the invariant
protecting the oracle the loop writes to, under *The oracle's own protection*. The
boundary this rests on was settled by the `architect` round `073d451b006e4a81`, which
narrowed the allow-list ruling of 2026-08-11 (`1ed468b61248497e`) rather than
overturning it.

## The problem, measured

`qe-fast` was red on fifteen consecutive pushes to master and **none of them carried a
new regression**. The suite's exit codes were doing exactly what they were designed to
do and nothing consumed them: two triaged entries had drifted (`13/13 unscoped` against
a real `16/17`; `2 site(s)` against a real `3 site(s) across 4 file(s)`) and one triaged
defect had been fixed without its expectation being deleted.

That is the trust-erosion mechanism the flakiness literature measures directly —
developers "may lose trust in their test suites and stop considering failures even if
some of them are caused by real faults" (`scope:qe:chunk:87bfe1d0…-0002`, arXiv
2111.03382). A gate that is always red is not a gate. The object here is not to make CI
green; it is to make red mean something again, and to make the thing that turns red into
green a decision someone made on purpose.

## Why an expert hop at all

The honest justification is narrow, and stating it narrowly is what keeps the hop from
being decorative. Under a fixed reasoning-token budget with good context utilization,
single-agent systems match or outperform multi-agent ones across three model families
(`scope:literature:claim:414011b1207b38ef`), on an information-theoretic argument via the
Data Processing Inequality (`scope:literature:claim:be24e99a17184318`); multi-agent
becomes competitive only where single-agent context utilization degrades
(`scope:literature:claim:24bd7f990bd37f8a`).

So the hop is **not** justified by a second opinion being smarter. It is justified by the
partition: `qe` holds the accumulated triage corpus — every prior expectation, its
witness, and why it was pinned where it was — and `main` holds the implementation. The
hop earns its cost only while that corpus is larger than one context can carry. If it
ever isn't, the correct response is to delete the hop, not to defend it.

## What the suite already decides

The classification input is not a log. `tests/qe/run.py` emits a structured verdict per
case, and the taxonomy is already the one triage needs:

| Verdict | Exit | Meaning |
|---|---|---|
| `ok` | 0 | passed, or failed exactly as triaged |
| `known-red` | 0 | failed, and an expectation pins this witness |
| `drifted` | 1 | failed as expected but **differently** — the defect changed shape |
| `new-failure` | 1 | failed, and no expectation covers it |
| `fixed` | 2 | passed, but an expectation says it should fail |
| `malformed` | 3 | the case itself is broken — not evidence about the code |

Triage reads the **CI** run's ledger, never a local one. The two genuinely differ:
`tmux-invocations-name-their-socket` records that the runner image has no tmux at all, so
a locally-run suite is a report about the wrong machine.

## The loop

1. The operator invokes `/triage-ci`. There is no automatic trigger, by choice — the
   first version proves the dispatch before anything runs unattended.
2. `main` pulls the CI ledger and spawns the `thalamus-qe` subagent with every non-`ok`
   verdict. Scope is **all currently-red cases**, not only the newest.
3. `qe` classifies each case and takes the actions it may take unilaterally (below).
4. For anything needing implementation work, `qe` files one Linear issue per case into
   the **Claude Code Agent Reports** project on the Thalamus team.
5. `main` reads the issue, **independently verifies the classification against the
   ledger**, and acts in `src/`, where `qe`'s existing `*/src/*` deny stops it.
6. A fix makes the suite exit 2, and only `qe` may delete the expectation. `main` hands
   back to the same `qe` agent with its context intact; the fix is not done until CI is
   green.
7. Disagreement between them escalates to the operator. The room path for this waits on
   `--to main` being addressable at all (`dispatch-to-main-target-broken`).

## What is allowed to go quiet

**ADD is the mute primitive.** This corrects the intuition the design started from. A
failing case with no expectation returns `NEW_FAILURE` → exit 1
(`tests/qe/expectations.py:113`); add an entry matching it and the same failure returns
`KNOWN_RED` → exit 0 (`:132`, `run.py:195-203`). Adding is the action that converts a red
gate to green. Widening an existing witness pin is a *lesser* form of the same act — it
broadens a mute already granted. A policy that gates widening while leaving addition
unilateral guards the smaller escalation and leaves the larger one open.

The rule, therefore:

> **`qe` acts unilaterally when a fact in the ledger justifies the action. A judgment
> call routes through the report.**

| Action | Unilateral? | What justifies it |
|---|---|---|
| Delete an entry whose case now passes | yes | `outcome: passed` — exit 2 exists to demand this |
| Repair a malformed case | yes | exit 3 — the case is broken, and a broken case is not evidence |
| Add an entry for a still-failing case | **no** | `qe`'s classification alone |
| Widen an existing witness pin | **no** | subsumed by the above; it is an addition to a granted mute |

One test decides it: *is the case passing or failing?* Deleting rests on an observed
pass. Adding rests on an agent's opinion that a red is acceptable.

This is Progent's **monotonic confinement** — the effective action space may only shrink
without approval, "preventing silent privilege escalation even under adversarial inputs"
(`scope:literature:claim:089fc912caa2d576`, arXiv 2504.11703) — applied to an oracle
instead of a privilege policy. It is not an invention and is not claimed as one.

Two further reasons the gate sits on addition rather than on widening. First, `qe`
classifying its own finding as "triaged, not a regression" is self-verification without
external feedback, the configuration measured to fail and sometimes *degrade* performance
(`scope:literature:claim:20b8f7fdb645f789`, arXiv 2310.01798, ICLR 2024). Second, the
cost is asymmetric in the direction that matters: Herzig & Nagappan report precision
0.85–0.90 against recall 0.34–0.48 on Windows 8.1 and Dynamics AX, and argue precision is
the more important value because a real defect misclassified as a false alarm "could lead
to defects elapsing quality assurance", while a missed false alarm costs only efficiency
(`scope:qe:source:8c49f532…`, ICSE 2015). Their recommended use of the classifier is
explicitly **not to suppress failing tests outright**.

## The boundary

`tests/qe/` is writable only by `qe`. That is allow semantics over a path, which the
2026-08-11 ruling held to be incoherent inside a guard that fails open. The reopening
succeeded, and it is worth recording precisely *how*, because the evidence that motivated
it did not survive.

**The evidence brought did not reach the ruling.** Harness-Bench's 24.6%
(`scope:literature:claim:19922a8410ee9fed`) was cited as measuring that blocks cause
stalls rather than route-arounds. It cannot: the category is a union ("tool errors **or**
blocked commands not followed by effective recovery"), so no share of it is attributable
to policy blocks; the denominator is failed trajectories, so it is a composition
statistic and not a rate; and it is structurally blind to route-around, since a
successful route-around is not a failed trajectory. It was cited to rule out the exact
thing it cannot see. More decisively, the original reason was a coherence argument about
policy shape and never an appeal to lab/008's trade, so overturning lab/008 would have
left it standing.

**What did reach it was a narrowing of the original sentence.** The discriminator is:
*does the rule change the default over its own complement?* A global allow-list does —
anything unenumerated becomes denied, over a namespace owned upstream. A bounded
ownership row does not: it is a deny with an owner exception, and its failure mode is
*permit*, which is the status quo. It cannot be worse than what ships today. The
incoherence objection was aimed at the global case and does not survive at directory
scope.

Three consequences for the build:

- **The table lives beside `ROSTER_CAPABILITY_DEFAULT` in `contract/manifest.py`**, not
  in the per-scope manifests. `config/experts/` holds seven manifests and no `main.yaml`;
  a per-manifest deny cannot express this rule because the scope it most needs to bind
  has nowhere to declare it. Writing the owned glob into the other six is the same
  normalization error the 2026-08-11 decision already rejected, and still would not cover
  `main`.
- **Fail closed on the rule, not on the guard.** This is a house pattern rather than a
  new design: `write-guard.sh:58-66` degrades to a raw-payload search rather than
  aborting. The box cannot be wedged, because `Bash` is not on `role-guard`'s matcher
  (`install.py:90`).
- **Keep the `main` short-circuit, and order it after the ownership test.** The
  short-circuit is a statement about who `main` is, not a performance hack, but it is also
  where the performance lives. Measured on this box: a manifest load costs **155 ms/call**,
  bare python 15 ms, jq 3 ms. Testing the target *path* before resolving any scope keeps
  the entire fast path — the common case exits before the exemption is consulted.

Enforcement is structural rather than prose because prose is the configuration measured
failing: MAST names "Disobey Role Specification" as a distinct failure mode
(`scope:literature:claim:d675b5b74b2cdd34`), and the repair that worked in the system it
studied was structural authority, +9.4% task success
(`scope:literature:claim:db0928fe2cfd3616`).

## The handoff is a pointer, never a warrant

`main` holds `src/` write authority. The Linear report supplies the designation of what
to change. Anyone who can write a Linear issue can therefore supply that designation —
which makes `main` the confused deputy, and makes `qe`'s inability to write `src/`
irrelevant to this particular risk. The tracker is an agent-to-agent bus, and an external
bus is the same residual as the Agent Teams mailbox already named open in the trust
model, with a vendor's name on it.

The remedy is a constraint on `main`, not on the tracker:

> **Every action `main` takes must be derivable from the ledger alone.** The report says
> where to look. It never says what is true.

If `main` can act on something present only in the Linear text, the separation is
decorative. This follows FIDES's treatment of integrity labels — content that leaves the
system and returns must not come back carrying higher integrity than untrusted external
input (`scope:literature:claim:708f50d08755c509`,
`scope:literature:claim:ff7360fe27df20c6`).

Note what "independent verification" does and does not mean here. `main` and `qe` are
drawn from the same base model, so this is **evidence independence, not model
independence** — `main` verifies against artifacts (`expectations.json`, the case witness)
that `qe` cannot write into `main`'s decision path except through the report. That is the
weaker of the two and is what we actually have. The corpus holds no measurement of
actor/verifier error correlation at a shared base model; the nearest anchor is
self-preference in LLM evaluators, where self-preference tracked self-recognition and
fine-tuning on superficial features did not reproduce the effect
(`scope:literature:source:68fd9012…`, arXiv 2404.13076).

## The oracle's own protection

The rule above is enforced as a content invariant over `expectations.json` **and its diff
against a base**, not as a hook. A hook binds a tool call, so `Bash`, Cursor and a human
editor all route around it, and in CI there is no scope for one to consult; the file alone
cannot tell an addition from a repair, which is why the diff is part of the subject. The
invariant is the FAST case `expectation-additions-are-never-silent`
(`tests/qe/cases/expectation_additions.py`), hermetic apart from `git`.

It asserts that the entry set has not **grown** and that no surviving pin has been
**widened** — a `witness_contains` that is a substring of the base's matches everything
the base's matched and more, and an emptied pin matches every witness. Deletions and
narrowings pass, because both can only make the suite louder. A re-pin onto text that
neither contains nor is contained by the old pin is deliberately not flagged: re-pinning is
how a drift gets triaged at all, and a permanent red nobody can clear is the trust erosion
this design starts from.

**It verifies no approval, and offers no field by which an addition could declare itself
approved.** That absence is the design. This repo holds no authorization artifact a
hermetic check could verify — the close ledger disclaims operator authentication in its own
docstring (`harness/closes.py`) and lives under `$HOME`, so CI reads it empty for the same
reason `ceremony ack`'s store would be; Linear is the untrusted bus named above; and an
agent editing the file runs at the operator's uid with `git` and `gh` in PATH, so any token
it could be asked to produce it could also mint. An `approved: true` key would be a rubber
stamp with a schema.

What an adding agent cannot mint is the **base**: the prior server-side tip of the pushed
ref, which the forge writes into the event payload after the push has landed. So the
guarantee is a detection boundary, and stating it exactly is what keeps it from being
overread:

> An addition costs the adding agent a red CI run on the commit that introduces it, naming
> the entry, and no edit to `expectations.json` can buy that run's silence.

The prevention boundary — that a human must have read that run before the tree can go quiet
— needs branch protection with required review on the default branch. That is repo
settings rather than `tests/qe/`, and it is not configured.

Three conditions take MALFORMED (exit 3), the one verdict `reconcile()` lets no expectation
absorb: an entry naming this case, which would let an addition acknowledge itself; no
determinable base; and a duplicate JSON key or duplicate case name on either side, which
`json.loads` and `load()` respectively resolve by last-wins and would make the set
difference unsound. Adding an entry for this case therefore converts its exit 1 into an
exit 3, which is louder — that is what closes the self-mute loop.

## Prior work

None of the three components is novel and none is claimed as such. The **path-ownership
primitive** is an *instantiation* of Progent's deterministic least-privilege enforcement
(arXiv 2504.11703, `scope:literature:claim:494478ed390a2959`) at path rather than
tool-argument granularity, and of the "no capability permissions / no policy engine" gaps
Agentverse names for agent platforms generally
(`scope:literature:claim:59ddcdff44575b0a`, both severity High). Its default-deny posture
is Saltzer & Schroeder's fail-safe-defaults principle, held here secondhand via arXiv
2606.04990 §4.4. The safety comes from the default, **not** from expressing authority
per-resource rather than per-principal — those are the column and the row of one access
matrix, and a design claiming otherwise would be wrong. The structural-rather-than-prose
enforcement follows MAST (arXiv 2503.13657; 14 modes over 150 traces, κ=0.88,
`scope:literature:claim:11750ab72cf137b8`; extended to 1,642 traces across 7 frameworks,
`scope:literature:claim:81cbcfe73a0f48a5`). The trade accepted is Progent's own: a static
least-privilege policy is brittle against unanticipated legitimate work, which is why
Progent needs an LLM policy updater and an SMT solver. We accept the brittleness because
repo paths are a closed namespace we own, and we record that this **narrows**, for a
bounded set of directories, the allow-list refusal recorded for `capability_boundary` in
[11](11-related-work.md) §3a1.

The **actor/verifier handoff** is a *convergence* on MAST's task-verification category
and on the finding that LLMs do not reliably self-correct without external feedback
(arXiv 2310.01798, `scope:literature:claim:cbbef440ef3c4912`). It is an *extension* only
in grounding verification in an evidence artifact rather than in model independence — and
the cited work names what that trades: at equal reasoning-token budget the extra hop is a
cost, not a benefit, unless the scope partition carries a corpus one context cannot hold.
AgentCollabBench operationalizes the residual worry as Consensus Pollution Rate and
measures topology effects comparable in magnitude to backbone model choice (arXiv
2605.08647).

The **mute-resistant oracle** is an *instantiation* of Progent's monotonic confinement
applied to a test oracle, motivated by the measured trust-erosion mechanism in CI
flakiness research (arXiv 2111.03382; 18% of suite executions fail and 13% of those are
flaky, arXiv 2605.05564) and by the precision-over-recall asymmetry Herzig & Nagappan
measured at industrial scale (ICSE 2015). The approval boundary is drawn at *any action
that can make CI quieter on an agent's own judgment*, which is addition, not only
widening.

## Not built, and deliberately so

- **No automatic trigger.** `/triage-ci` is operator-invoked. An unattended trigger is a
  later decision, and a red gate nobody reads is the failure this design starts from.
- **No room.** The close loop and the dispute path both want a room, and both need
  `--to main` to resolve. It does not: `preflight` filters on a `LiveSession.scope`
  *derived from* `--agent`, and the qe fixture's main member is written with no agent key
  at all, which is the condition under test. A manifest alone would not close it — the fix
  has to reach scope derivation. Until then, disputes escalate to the operator.
- **No thread.** Work that needs a tracker entry goes to Linear. An agent cannot open a
  thread, and no surface will be added that lets one.
