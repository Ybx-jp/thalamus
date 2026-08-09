# 048 — The treatment that was only a label

The room shipped across 043–047 as a *boundary*: discovery, delivery and resumption,
each partitioned and each measured. None of that work asked whether a room is any
good, and the question turns out to split in three, only one of which has ever been
measured.

- **Containment** — does the boundary hold? Measured, repeatedly (045, 046, 047).
- **Epistemic** — does recording a room stop the graph reading one conversation as
  N-fold independent agreement? `substrate/witnesses` now implements the reading;
  nothing has measured whether the artifact occurs.
- **Productive** — do experts in a room do better work than experts working alone or
  consulting by ticket? Never measured, never designed, and the assumption underneath
  the whole feature.

This entry is the design for the third, the grounding that constrained it, and the one
instrument built. lab/045's own "not yet measured" list contains zero efficacy items,
which is how long this went unnoticed.

## The corpus is the first finding

Measured against the live graph and ledgers, 2026-08-09. The denominators move —
sessions distil continuously — but the numerators are the point and they do not:

| | |
|---|---|
| Sessions in the graph | 194 |
| …carrying a `room` property at all | 8 |
| …with a **non-empty** room | **1** (`symtest`) |
| …with a `forked_from` | **0** |
| Guard-ledger rows | 358 |
| …written by the room boundary | **5**, all from `alpha`, the 045/046 probe room |

Every quantity the design would analyse is zero or one, and the one is synthetic.
`e3ba1bf` says the same thing from the write side: *"No number moves on today's graph
— nothing in it carries a room or a fork parent yet."* Any room result reported before
a real capture period would be reporting the fixture.

## The grounding came back mostly empty, and that changed the design

Consultation `612a5b32c1f04851` to the literature expert, 27 validated citations.
**Three of four areas held nothing at all** — and "nothing" meant *never procured*,
not *checked against the field and absent*. That distinction is the useful part: the
gaps were purchasable, and were purchased (feeds `permutation-null`,
`cluster-inference`, `evidence-independence`; see [docs/11](../docs/11-related-work.md)).

Four things the grounding changed:

**1. The inference plan is unavailable by construction.** With one or a few *treated
clusters*, cluster-robust t- and Wald tests over-reject severely; with a single treated
cluster the score for the treatment dummy is **exactly zero**; and the wild cluster
bootstrap — normally the fix — fails in the same corner. Cluster-robust standard errors
are biased *downward* there, i.e. toward false positives. **A room is one cluster, and
rooms accumulate slowly.** The pre-grounding plan ("cluster at the room level") would
have produced confidently wrong intervals in the direction of the project's own
headline claim. Randomization inference is the anchored fallback, and `sequential.py`'s
Robbins normal-mixture confidence sequence — built, and still with no caller — is the
other half.

**2. Three literatures were wearing one word.** *Cluster-robust inference* is the
analysis-side fix; *cluster-randomized / group-randomized trial* is the design-side
shape where the randomization unit is the group; *multi-level modelling* is the
variance-components framing. Conflating them reads as confused, and the first draft
did.

**3. The permutation null was already contaminated.** `calibration.rotate` selected a
null partner on `session_id != case.session_id`, so a room-mate was a *legal* partner —
and its own docstring says why that is wrong: a different session, *"or the vocabulary
is shared by construction and the null is not a null"*. Room-mates and forks share the
conversation itself. Winkler et al.'s **exchangeability blocks** are exactly this move:
when units are not exchangeable, restrict the permutation space by nesting so
correlated units are never swapped for one another. Fixed in `be2d00c` — and the same
source prices it, since restricting the space costs power.

**4. The novelty claim is dead, and the premise is grounded.** Coordination-mechanism-
as-treatment and group-as-atomic-unit both have 2026 prior art in the graph. Held
tier-2: communication **topology explains 7–40% of outcome variance** in LLM
multi-agent systems. That empirically supports the *premise* that room-mates are
structurally correlated. It supports nothing about how to *adjust* an estimate for
that correlation, and the two must not be cited with equal confidence.

## The counterfactual is not "no room"

Comparing room against solo confounds the room with *any* cross-expert contact. The
project already ships a second coordination mechanism — the consultation ticket — so
the arms are **solo / ticket / room**, and the baseline is already measured: lab/043
timed consultation cold-start at **303, 372, 383, 417, 462 s**. That is the cost the
room's fast tier was built to attack, and it is the natural primary endpoint.

The outcome must be **signed and two-sided** ([docs/04](../docs/04-eval-loop.md)): a
metric that counts collaboration wins cannot observe collaboration *harms*, and
correlated error is the most likely way a room makes things worse.

## Built: the manipulation check (`eval/rooms.py`, `thalamus eval rooms`)

The treatment is not "sessions were launched into a room" — that is a flag. It is that
they *collaborated*. A room whose members never messaged each other is a set of solo
sessions wearing a room label, and an arm like that cannot separate **"rooms do not
help"** from **"the room did not happen"**. So, before any outcome: two topologies from
two ledgers.

- **Nominal** — who was *allowed* to talk, from the pin ledger, including members that
  never said anything.
- **Realized** — who actually *sent*, from the guard's `room-boundary` rows, which
  already carry `{room, scope, target, branch, verdict}` and are therefore a directed
  edge list over member scopes.

Enumeration is driven from the **pin** ledger deliberately: a silent room is the only
room the check can fail, and reading the roster off the guard ledger would make exactly
that case invisible.

```
Rooms (2):
  room `alpha`: treatment occurred — 2 permitted send(s) over 1 directed pair(s)
    among 2 members; density 1.00; 0 reciprocated pair(s)
  room `symtest`: NOT A ROOM — 1 member, so no pair could collaborate;
    exclude rather than count as a room arm
  treatment occurred in 1/2 room(s) — arms from the rest are not room arms and
    should be excluded before analysis, not after
```

Two findings on a five-edge corpus, both of which would otherwise have been assumed
away: `alpha`'s collaboration is strictly **one-way** (`main` → `homelab`, never
answered), which is a broadcast rather than the reciprocal fast tier docs/07 describes;
and `symtest`, the single non-empty room in the graph, is a **room of one** — not a
room that failed to collaborate, but no room at all.

It is a **manipulation check, not a score** — `arms.py`'s standing for its consequence
probes, and for the same reason. Exclusion happens *before* outcomes are read; dropping
arms after seeing them is the peeking failure the sequential layer exists to avoid.

### Three bugs the real data found

- **The prefix is not membership.** `alpha-typo` parses exactly as cleanly as
  `alpha-homelab`, so an unrecognised peer became a node the roster never had —
  inflating the edge set against a density denominator drawn from the member set. Both
  ends must now resolve to known members. Caught by a test fixture written to assert
  the opposite.
- **A self-send is not an undercount.** The live ledger holds one of each: a target
  resolving to the sender's own scope (understood, correctly dropped) and an unparseable
  one (the edge list is missing something). Lumped together, every self-send raised a
  lower-bound caveat the data did not support.
- **The guard ledger is shared, and nothing filtered it.** `load_guard_events` read
  every row in `~/.thalamus/guards/`, so the room-boundary rows were already being
  counted as gremlin-guard activity in the fluency report and the live pulse feed.
  Rows now carry their writer.

## Not built, deliberately

Anything that turns the check into an outcome. Grading collaboration by volume, or
using realized density to **discount** correlated witnesses in `substrate/witnesses`,
would change a settled decision — [docs/09](../docs/09-schema-and-federation.md) §Scope
refuses to reduce a count on room membership alone, and refuses to infer dependence
from agreement at all. Note the closest prior art does the opposite: Dong et al. detect
copying *from agreement patterns*, where Thalamus reads a recorded launch fact. Message
volume is also a recorded fact, so the move is arguably admissible — but that is a
consultation, not an inference.

Also not built: a topology harness. Nodeglass (`~/code/nodeglass`) is a well-tested
domain-general graph substrate whose scorers sit behind a protocol, and the guard
ledger is a real observed edge list, so the fit is genuine. It is deferred on evidence:
five edges from one room, and every metric it would add is *comparative*.

## The reason that generalizes: write-time obligations versus read-time ones

`witnesses.py` was correctly written against zero data, because **the stamping is what
is lost by waiting** — nothing in a finished graph separates three sessions that agreed
from three that were in the room together. That argument is load-bearing and it does
not transfer. The guard ledger is already recording every edge, so a structural-metrics
layer over it can be built at any time with nothing lost. *Now-or-never applies to
capture, never to analysis* — and the two are easy to confuse when both look like "we
have no data yet."

## The falsifier

If realized room topologies turn out not to **vary** across rooms once real rooms run,
then topology-as-independent-variable is dead for this corpus, the Nodeglass line buys
nothing, and the room/ticket/solo comparison collapses back to three categorical arms
with a few-treated-clusters problem. That check is cheap, comes first, and is the thing
to run before any of the above is built further.

## Moral

The boundary work measured everything about the room except whether anyone was in it
talking. A feature can be fully instrumented along the axis its author was thinking
about and completely uninstrumented along the axis that carries its value — and a
"room" flag on 1 of 194 sessions looks identical, in every report, to a room that
worked.

**Ends in:** design + instrument + 3 bugs.
