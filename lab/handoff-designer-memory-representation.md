# Handoff — can the graph hold design experience?

**From:** `designer` **To:** a pinned `architect` session **Status:** problem statement, not a design

This is a request to design something, not a design to implement. The observations and
the acceptance criteria are the designer's; the representation is the architect's. Where
this document names a candidate direction it is to show the space is non-empty, not to
choose. Reject any of them freely — but say which observation the rejection rests on, so
the disagreement is about evidence rather than taste.

**Nothing here is urgent.** Neither open gap bites until the design drills in
`lab/penpot-drill-ladder.md` start producing judgements worth storing, and both are
blocked behind Penpot defects P1/P2 in that file. Treat this as scoping, not a queue item.

## Before designing anything

CLAUDE.md's grounding discipline is binding here and this is exactly the case it was
written for. Both open gaps are representation questions with substantial prior art —
argumentation frameworks and preference/qualitative-decision representation for Gap B,
multimodal and content-based retrieval for Gap C — and `literature` currently holds
nothing on either (it holds nothing on visual design at all; ticket
`7f953992f0c347e7`). Run `ground-in-literature`, procure against these gaps, and expect
to consult `literature` and `eval-methodology` before proposing a schema. A schema that
cites nothing has been guessed.

Also run step A0 first: **check whether the graph already answers this.** Some of what
follows may already be representable in a way the designer did not find.

## What is already true

`src/thalamus/contract/ontology.py` declares the vocabulary once and derives it
everywhere — the module docstring records that this replaced hardcoding across seven
consumers. Two contract rules are encoded rather than described, and any proposal must
hold them:

1. **`Artifact` and `Agent` are the only global types.** They are safe to share because
   they carry tier-1 observations of the operator's own repo, or no content at all. They
   are the join key that makes the main plane connective.
2. **Direct expert→expert edges between scoped nodes are illegal.** Consultation routes
   through a session in the main scope. Edges into globals are not crossings —
   `edge_crosses_scope` returns False for them, and docs/09 G3 explains why that is
   load-bearing for the roster granularity metric.

Two further properties matter for anything proposed below:

- **Consumers depend on core *labels*, not on `kind`.** An expert may add namespaced
  kind values without any consumer changing. That is why `Claim` is one label
  discriminated by `kind` rather than one label per subtype, and it is the cheapest
  extension point in the ontology.
- **Adding a `NodeType` or `EdgeType` is now a one-file change** by construction. The
  cost of a new type is no longer plumbing; it is whether the type earns its place.

## What works today, so that the gaps are legible against it

Design knowledge that is propositional or episodic already lands cleanly, and this is
not hypothetical — the Penpot defects P1 and P2 were found, diagnosed and recorded in
one session, and every part of that record has a home: `Claim(problem)` → `SOLVED_BY` →
`Claim(solution)`, `TOUCHES` a global `Artifact`, `DERIVED_FROM` the session `Source`
with `anchors` onto the exact messages. Critique-as-finding — the charter's core
obligation — is `Claim(problem)` against an `Artifact`. None of that needs anything new.

## Gap A — there is no writer for a design-specific claim kind

**Smallest of the three, and possibly a non-problem.** Recorded because the designer
first misdiagnosed it and the correction is the useful part.

`claim_kinds` in a manifest gates **ingestion batches only** (`ExpertManifest.validate`).
docs/06 requires that it name kinds a writer actually produces: *"declaring kinds no
writer produces makes the manifest aspirational, and the contract rejects the batch."*
Every roster scope therefore declares `literature/finding|technique`, because that is
what the shared ingest extractor emits. `designer.yaml` is correct as written.

Distillation is a separate path and writes core kinds only — `decision`, `problem`,
`solution`. So a design critique currently lands as a `problem` or a `decision`,
indistinguishable at the kind level from an architecture decision or a test failure.

**The question for architect:** does that matter? A `design/critique` kind would need an
extractor that emits one before the manifest could honestly declare it, which is an
extraction change, not a manifest change. Two defensible answers:

- **No, and leave it.** Consumers query the `Claim` label, not the kind. Retrieval is
  lexical and a critique's text is already distinctive. The core kinds are domain-neutral
  on purpose, and multiplying them per scope erodes that.
- **Yes, and it generalises.** `reader.py:83` records that claim kind is *"the one
  discriminator found"* with measurable retrieval signal (decision 62% / solution 56% /
  problem —). If kind is the discriminator that works, a scope whose output is
  systematically one flavour of judgement is under-served by three shared values.

Resolve this one on the measurement, not on tidiness. It is cheap either way and should
not gate B or C.

## Gap B — taste is comparative and there is no comparative edge

**The observation.** Accumulated design judgement is substantially a partial order over
alternatives with rationales: *this beat that, for this reason, under these constraints.*
That structure is the durable part. The chosen artifact is disposable — next project,
different constraints, different winner — but "serif body copy lost to the reading
distance on this surface" survives and transfers.

**What the ontology offers.** `SOLVED_BY` (problem → solution) is directional but not
comparative: it cannot say two solutions were both viable and one was better.
`SUPERSEDES` is explicitly confined to evidence lineage (Source → Source, transcript
snapshots and re-ingestions) and carries no rationale. `BLOCKS` is thread scheduling.
There is no edge whose meaning is *preferred over*.

**Consequence.** The comparison can only be flattened into `Claim.description` prose.
That is retrievable by keyword and not traversable, so the graph can never answer *"what
has this expert learned to prefer, and under what conditions"* — which is the question
whose answer would constitute taste. Worse for the eval loop: a preference that is only
prose cannot be shown to have been used, so `RETURNS.used` attribution cannot grade it.

**Why this scope surfaces it first.** Other scopes converge on a right answer; this one
converges on a defensible one, and defensibility is comparative. But the architect should
test whether the need is really designer-specific — architecture decision records are the
same shape (options considered, decision, consequences), and if so the type belongs to
the roster rather than to this scope.

**Candidate directions, none endorsed.** (a) An edge between `Claim`s carrying rationale
and context in edge properties, following the house qualification idiom already used by
`RESOLVES` and `RETURNS.used`. (b) A first-class node representing the decision with its
options as endpoints — heavier, but gives the alternatives somewhere to live, including
the ones not chosen, which prose loses entirely. (c) Nothing new; a claim kind plus
convention. Prior art in argumentation frameworks and decision-rationale representation
is directly on point and should be procured before choosing.

**Acceptance test.** After three drills, the graph can answer "what does designer prefer
for X, and why" by traversal, and the answer includes at least one rejected alternative
with its reason. If prose retrieval already answers that as well, Gap B is not real —
falsify it that way before building anything.

## Gap C — nothing in the ontology is visual

**The observation.** Design experience is substantially perceptual. A designer's memory
of *"this composition worked, that one didn't"* is not a sentence they once wrote; it is
the thing itself, recognised on sight. Every other roster scope's knowledge is natively
linguistic, so this assumption has never cost anything before.

**What the ontology offers.** `Source` is content-addressed, retained verbatim, and
tier-discriminated — an image could be a `Source` without violating anything, and
`DERIVED_FROM` would make reaching it provenance-mediated. But `label_property` is
`title`, `Chunk.text` is text, `ADJACENT_IN_TEXT` is document order, and retrieval is
lexical throughout. There is no perceptual representation and no similarity that is not
lexical.

**Consequence.** *"Show me the compositions that worked"* is unanswerable in principle,
not merely unimplemented. What the graph retains is the designer's **description** of its
visual experience, which is a lossy, self-serving summary written by the same agent that
will later read it — precisely the "distillation of itself" failure the `Source` node was
introduced to prevent for text. The floor `Source` gives the provenance chain does not
exist on the visual side.

**Evidence this is real and not theoretical.** Drills D3 (identity board) and D5 (hero
illustration) in `lab/penpot-drill-ladder.md` produce judgements whose entire content is
visual. The ladder is designed so that if the graph cannot retain those, it shows up as a
measurement rather than an argument — the drill after D3 either recalls the lesson or
does not. Run the ladder before building for this gap; it converts the question from
speculation to data at no extra cost.

**Constraints any answer must hold.** Images are large and the substrate is TinkerGraph
in memory — the 2026-07-14 decision against chunk nodes was a node-count argument, and
blob size is the same argument in a different unit; `Chunk` was admitted only for the 2%
of the archive that is literature. Anything visual must state where bytes live and why
that is affordable. Provenance must survive: an image reached without a `DERIVED_FROM`
path is a tier-laundering hole, and docs/05's "distillation does not launder" is the rule
to hold. And tier discipline still binds — a rendered export of the operator's own file is
tier 1; a design pulled off the web is tier 2 forever.

**Candidate directions, none endorsed.** (a) Images as `Source` with a locator, no
perceptual retrieval — cheapest, and honest about being an archive rather than a memory.
(b) The above plus a caption or description node co-indexed lexically, which is what
`Chunk` does for text and would reuse a proven mechanism. (c) Perceptual embedding and
similarity — most faithful to the actual gap and the largest change, since nothing in the
substrate does vector similarity today. The prior art here is deep (content-based image
retrieval, multimodal embedding) and none of it is in `literature` yet.

**Falsification.** If, after D3 and D5, a fresh designer session reliably reconstructs
the visual judgement from the distilled text alone, then description is sufficient and
Gap C is closed by evidence rather than by building. The designer's expectation is that
it will not, and the designer should be held to that prediction.

## What the designer wants back

Not an implementation. A judgement on each gap — real, not real, or deferred pending
drill evidence — with the reasoning and the citations that settled it, and for anything
judged real, the seam where it would land. If the answer is "the graph should not hold
this, and design experience belongs in skills and artifacts instead," that is a fully
acceptable outcome and worth stating plainly, because the designer would then stop
expecting recall to carry judgement forward and start writing it down where it works.
