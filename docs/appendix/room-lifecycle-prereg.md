# Pre-registration — the peer-review ablation

**Id:** `prereg-room-lifecycle-001`. Pass it as `--prereg` on every `thalamus ceremony
start` and `thalamus ceremony assign` row this study covers.

Registered before the room that follows `atlas`. It fixes [12](../12-room-lifecycle.md)
item 10: primary endpoint, harm endpoint, α, ρ, equivalence margin, exclusion rule and
falsifiers. The endpoints, exclusion rule and falsifiers are as settled in
`scope:main:exchange:ea0f471918434824`; α, ρ and the margin in
`scope:main:exchange:23f20d9cad444f3c`.

## Scope, and what `atlas` is

Room `atlas` (2026-08-11) ran before this document existed. It is **observational**:
excluded from every arm, and it cannot be retrofitted into one. That is enforced by the
ledger rather than by intent — `late_assignments` and `late_comparators` read file
position, so an assignment or comparator written for it now is reported as late. It
carries no `assigned` row, no arm on any occasion, no comparator, and no review
occasion. `thalamus ceremony audit` will name `atlas:review` and `uncompared: atlas`
permanently; **neither is to be "fixed."**

`atlas` is also permanently unusable as an out-of-room comparator, for the same reason.
It remains legitimate for design *sizing* — how many deliverables a room produces, how
long occasions run — and that is what it is used for below.

## The one measurable contrast

A ceremony is measurable iff it has multiple independently-assignable occasions within a
single room. Only **peer review of deliverables** passes.

- **Unit of analysis:** the deliverable.
- **Unit of randomization:** the deliverable, randomized inside its room, dealt by
  `thalamus ceremony assign` before the occasion runs.
- **Blocks:** rooms. Permutation restricted so a deliverable never swaps across rooms.
- **Control:** an **equal-cost non-peer pass** — see *The cost match* below, which is
  not yet settled and is a precondition for the first assignment.

This buys causal inference about **one ceremony**, never about the lifecycle. Room-level
inference is descriptive forever: rooms are self-selected, so randomization inference has
no reference distribution at the room level.

## Endpoints

**Primary** — the downstream fate of the room's commitments, measured outside the room:
did the predicted artifact come into existence, did the delegated item become a
decision/solution claim, and does a later **non-room** session build on it, re-litigate
it, or retract it. Signed both ways — durability +, re-raise/retraction/contradiction −.
Resolved through the rake pipeline's pair emission and adjudication, **not** through
content-addressed claim convergence, whose base rate of 4 in 504 across 125 sessions
would read as "nothing durable happened" regardless of truth.

Not the endpoint: the deliverables report, or any LLM judgment of it.

**Outcome coding**, registered here because `RESOLUTION_OUTCOMES` is three strings and
`sequential.track` cannot be fed strings:

| outcome | value |
|---|---|
| `appeared` | 1.0 |
| `absent` | 0.0 |
| `superseded` | 0.5 |

`superseded` sits at the midpoint deliberately and the choice is arguable: the predicted
artifact did not appear, but something replaced it, so scoring it 0 would count a room
that improved on its own forecast as having failed. It is registered now precisely
because it is arguable — deciding it after seeing which arm accumulates `superseded`
rows is the failure this document exists to prevent.

**Harm** — inflated-witness count: claims converging across ≥2 member scopes whose
provenance is one room. No judge; `substrate/witnesses.py` computes it.

**Denominator** — cost per occasion, `thalamus eval cost --by-occasion`.

## α, ρ, and what n means

**α = 0.05.** Confirmed rather than assumed: `randomization.smallest_design(0.05)`
returns (7, 3), which is the arithmetic docs/12's feasibility paragraph rests on. Moving
to 0.01 costs ~18% of interval width and pushes the room-level floor to 9 rooms,
invalidating that paragraph silently.

**ρ = 0.1369.** Operator decision to tune for a longer campaign. Substituting u = nρ into
`sequential.radius` collapses n into a 1/√n prefactor, so the minimizing u depends only
on α: u\*(0.05) = 8.211968 and ρ\* = u\*/n. Hence ρ\*(60) = 0.136866.

The cost of the choice, on the record: at n = 30 the interval is **1.43% wider** than it
would be under the ρ that is tightest there (0.28104 vs 0.27707), and 0.94% tighter at
n = 60. For scale, leaving ρ at the module default of 0.05 would have cost 11.8% at
n = 30.

> **n counts pairs, not occasions.** `sequential.paired_differences` is per-unit, so a
> campaign of 60 reviewed-deliverable occasions split 30 treated / 30 control gives
> **n = 30**, not 60 — and ρ\*(30) = 0.2737. This registration tunes for **60 pairs**,
> i.e. ~120 deliverable occasions. Read against `atlas`'s 5 deliverables per room, that
> is a campaign on the order of 24 rooms, and the campaign should be reported as
> under-tuned rather than retuned if it ends short.

## The equivalence margin — deferred, with a trigger

**No margin is registered now, and this is a finding rather than an omission.** All three
derivation routes are closed today:

- The catalogued margin-setting methods (point-estimate, FDA fixed-margin, synthesis) all
  require a historical comparator effect. The ledger holds **0 commitment rows and 0
  resolution rows**, so the endpoint's scale is unobserved.
- The cost route is closed **by this design's own control**: an equal-cost control makes
  incremental cost zero by construction, so a cost-derived margin divides by zero.
- Endpoint construction alone gives nothing binding.

And a harder constraint makes any number registered today meaningless. `SequenceState.within`
requires the *whole* interval inside the equivalence region, so futility needs
`margin ≥ radius(n) + |mean − null|`. At n = 60, radius = 0.19592 — so **futility requires
margin ≥ 0.196 even with the mean exactly on the null.** Below that the branch is dead;
at or above it, "practically equivalent" spans peer review flipping ~39% of deliverables
by a full outcome category. Every margin available at n = 60 is either unattainable or
meaningless.

**Registered instead:**

1. **Trigger** — the margin is set when **25 control-arm resolutions** exist, a number
   derived by `gold.required_n`'s method targeting SE(p_control) = 0.10.
2. **Rule fixed in advance** — the fixed-margin method applied to the control arm's
   observed resolution rate, so the setting procedure is registered even though its input
   is not. The margin is computed once, from the first 25, and never revisited.
3. **The futility branch stays dead rather than inflated.** If the computed margin falls
   below `radius(n) + |mean − null|` at the n then reached, the campaign reports "futility
   unreachable at this n" and continues to horizon. Widening the margin to make futility
   attainable is prohibited.
4. **`horizon` is registered now**, since it needs no margin: the campaign stops at
   n = 60 pairs and reports where the interval sat.

## The cost match — unsettled, and a precondition

The ablation's control must be cost-matched, and **the basis is not yet decided.** It
cannot be occasion burn as the ledger is currently used: `atlas`'s occasions were opened
and closed as brief brackets around ceremony moments — `atlas:open:1` ran 5m16s — while
15 of its 20 revisions landed outside every window. Matching on occasion burn would match
the bracket rather than the treatment.

Two candidate bases, neither registered: hold occasions **open for the duration of the
work** they name, or match from `revision` rows' `author_scope` and timestamps. **The
first assignment may not be dealt until one is registered as an amendment to this
document.**

## Exclusion

A room must pass `eval/rooms.py`'s manipulation check **before** any outcome is read.
Exclusion happens before outcomes, never after — dropping arms after seeing them is the
peeking failure `sequential.py` exists to prevent.

## Falsifiers

**F1** — if a majority of rooms fail the manipulation check, the ceremony structure
produced no collaboration and the lifecycle is a label on solo sessions. If realized
topologies do not *vary* across rooms, topology-as-independent-variable is dead here.

**F2** — if the fraction of ceremony outputs referenced in a later session *outside* the
ceremony that produced them is indistinguishable from `eval/attribution.py`'s permutation
null, the ceremonies produce write-only artifacts. Report the null beside the number and
exclude room-mates as null partners.

**F3** — the ablation reaching `futile` under the margin set by the trigger above is a
result, not a failure. It currently has **n = 0**: no review occasion has ever been
recorded.

## What the next room must capture

`atlas` recorded no review occasions despite holding three review rounds, and all 20 of
its revisions carry `author_scope: "designer"` — a single-author room, which is the
likeliest way the next room again produces review *work* that leaves no review
*occasions*. So, beyond what the ledger already takes:

1. A `thalamus ceremony start <room> review` per round, with `--prereg
   prereg-room-lifecycle-001` and the dealt `--arm`.
2. `--author` on every `ceremony revise` naming the scope that actually authored it.
3. An `assign` row before each review occasion, and a `comparator` row at open.

## Amendment

The margin trigger and the cost-match basis are the only two open parameters, and each
has its resolution procedure fixed above. Nothing else is amendable. A confidence
sequence retuned after seeing the data is a fixed-n test wearing a disguise; an endpoint
moved after seeing the data is worse. Precedent: lab/023's pre-registered rung≥4 endpoint
was left unamended when live data showed rung≥3 separating cleanly.
