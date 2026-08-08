# 042 — The brief nobody cites

**Ends in: don't run the replay. The deciding quantity is underpowered at this corpus
size, and the census turned up a finding about the brief that nobody was looking for —
across 55 answered exchanges, an expert has never once cited a Claim its own brief
handed it directly.**

**Date:** 2026-08-08 · **Graph:** 7,768 vertices / 19,878 edges · **Status:** census
(read-only), no experiment run

## Why the census existed

A proposed memory rule — when experts collaborate in a room, each absorbs into episodic
memory *only what it used* — puts the used-vs-ignored judge on the **write path**.
Eval-methodology (`557f5805ac0e452a`, 18 citations) refused the promotion on the
grounds that a wrong eval judge produces a number read skeptically while a wrong write
gate produces a memory silently and permanently missing things, with no artifact
recording what was dropped. It named one cheap experiment that could kill the rule
without building it: a consultation is already a two-party room, so replay the gate
against labels the system already writes — `REFERENCES{role:brief}` is what the expert
witnessed, `REFERENCES{role:citation}` from the validated answer is what it provably
used. And it attached a binding precondition: **count the pairs first**, and if the
achievable interval is wider than the effect that would change the decision, the honest
outcome is "no signal available", not "no signal found".

That precondition is the whole content of this entry.

## The first census was wrong, and its zero was structural

Universe as literally specified — direct `role:brief` edge targets, per exchange —
gives 55 answered exchanges, 323 pairs, 1,054 citation edges, and **zero** overlap in
every single exchange. A clean zero across 55 trials is a result to distrust, not to
report, so the falsifier ran before the number moved: what labels do the two edge roles
actually point at?

| role | Thread | Session | Claim | Source |
|---|---|---|---|---|
| `brief` | 124 | 122 | 77 | 0 |
| `citation` | 26 | 20 | 999 | 9 |

The brief serves **entry points** — open threads and recent sessions. The answer cites
**claims**. They are near-disjoint populations by construction, so the zero measured the
schema, not the experts. Reporting it as "experts ignore their briefs" would have been
a false finding with a real number attached.

## The viable universe is one hop out

A brief serves Session S; S `CONTAINS` Claims; did the answer cite any of *those*, in
the same exchange? That is a genuine witnessed-versus-used pair with a machine-written,
non-lexical label.

- 48 of 55 answered exchanges have a non-empty witnessed set
- **807** (exchange, witnessed-claim) pairs
- **89** positives — witnessed and cited within the same exchange
- base rate **0.110**, Wilson 95% CI [0.090, 0.134], half-width 0.022 unclustered

## Why it still cannot decide the question

The base rate is not the deciding quantity. The rule lives or dies on the judge's
**false-negative rate** — how often it calls "unused" something the expert provably
cited — and that is estimated on the 89 positives, not the 807 pairs.

Those 89 sit in **12 exchanges**, and 70 of them (79%) in six `eval-methodology`
exchanges alone. At lab/041's measured ICC of 0.229 and a mean positive cluster of 7.4,
deff ≈ 2.5 and the effective n is roughly **36** — an interval near ±16pp on the FN
rate. A write gate's decision turns on whether that rate is nearer 10% or 30%. ±16pp
cannot separate them, and a per-expert reading is worse: four fifths of the evidence
comes from one expert, so nothing here generalises across the roster.

**Verdict: no signal available.** Not "the rule survived", not "the judge is fine" —
the measurement that would discriminate cannot be taken at this corpus size, and the
pre-declared response to that case is to say so rather than to run it anyway and report
whatever came out.

## The finding nobody was looking for

Within an exchange, **zero of 54 brief-served Claims were ever cited by the answer that
brief was assembled for** — in 55 exchanges. Not a small number: zero. Yet 31 of those
54 were cited by *some other* exchange later, so these are citable claims that the
brief surfaced to the one expert that did not use them.

Every one of the 89 positives arrived through the Session→`CONTAINS` route: the brief
pointed at a session, and the expert cited claims found *inside* it. So the brief's
demonstrated value is as a set of **entry points for the expert's own ticketed
retrieval**, and not as a delivery of evidence. Whatever the brief hands over directly,
the answers are built from something else.

That bears on the receiver-assembled-brief design well beyond the room question, and it
is measured rather than argued. It also lands beside a held external result the
opposite way round: docs/11 §4 records that verbatim chunks beat LLM-extracted typed
artifacts by 15.9–22.0pp, which is a tax on graph-assembled briefs. This is the same
suspicion arriving from our own graph.

## Consequence

- The replay is **not run**. Re-run the census when the exchange corpus roughly triples,
  or when positives spread past a dozen exchanges and one expert.
- The queries are validated and in the `gremlin-python` skill's RECIPES.md.
- The finding about brief citation rates deserves its own consultation before it changes
  the brief's design — it is a measurement, and what it *means* is not settled here.
