---
name: tagging-prose-with-claims
description: Turn prose that promises something — a docstring, a README paragraph, a design-document sentence, a comment — into ledger entries, and cite each from the sentence that states it. Use before writing a batch of entries over a file, when prose asserts something no entry holds, when deciding where a citation will physically sit, and to ask with `claims-ledger neighbours` which entries are already about the ground being chosen.
---

# Tagging prose with claims

A tagging pass reads a file's prose, finds the sentences that promise something the
project is answerable for, and gives each one an entry pinned to the artifact that keeps
it true.

Tagging adds a citation and an entry; it removes nothing. What it buys is that the
sentence fails a check when the thing under it moves.

## An entry that is owed is written now

There is no backlog. A commitment written into prose with no entry behind it passes every
check — that is the one door the checkers do not watch — so an entry put off is not an
entry anything will ask for later. The cost of writing it does not fall either: the
citation goes inside the span the entry pins, so a later pass pays the same commit again
plus the drift its own citation causes.

Two shapes of deferral to refuse in particular:

- **A supporting change that needs a claim of its own.** Making something exported,
  configurable or guaranteed so that something else can rely on it is a commitment, and
  the sentence that says so needs an entry like any other. That the change was in service
  of other work does not make it smaller.
- **A repair the checkers have already named.** A drifted pin, a citation whose act no
  longer matches, a supersession a Scope now needs. `claims-ledger check` is green or it
  is not; leaving a finding for later leaves the ledger saying something untrue in the
  meantime.

Where the entry genuinely cannot be written yet — the artifact it would pin does not exist
— say so in the same breath as the reason, and write it as soon as it can be. Silence is
the failure mode, not delay.

## The citation goes inside the section its entry pins

That is the mechanism, not a preference. A pinned ground names a **section** of an
artifact, and what counts as a section is a per-project pattern:

    python -c "from claims_ledger import open_ledger; print(open_ledger().config.section_patterns)"

The sentence that makes the promise and the code that keeps it then live in one span, and
they move together: an edit to either is an edit to the same section, and a reader who
finds one finds the other. A citation parked away from that span still passes every check
— which is the problem. Nothing will ever object, and the reader who most needs the
citation is the one editing the code, who never sees it.

**Writing the citation flags the entries already pinned there, and that is the mechanism
working.** A section carrying seven grounds will flag seven entries when the next citation
is written into it, and each one is discharged by a re-read: `freshness --write`, then a
`corroborated` verdict recording what was read. That is a few minutes and it is the price
of the thing being checked at all. It is not a cost to design around, and a placement
chosen to keep the checker quiet has bought silence by moving the citation away from what
it is about. Batch a file's citations into one commit so the flags arrive once — that is
sequencing, not avoidance.

**Watch the section boundary on a module-level definition.** A section starts at its own
line, so a comment written *above* `NAME = ...` belongs to whatever is defined before it,
and a citation there sits outside the span its entry pins while looking adjacent. Put it
below the assignment, or inside the literal. Check rather than assume — this is invisible
in a diff:

    python -c "from claims_ledger import open_ledger
    from claims_ledger.schema import section_span, read_document
    k = open_ledger().config
    body, _ = read_document('path/to/file.py')
    start, end = section_span(body, k, 'code', 'THE_NAME')
    print(body[start:end])"

**The module docstring is for a claim about the file as a whole**, which is the case where
no section is the right ground — the module has no single definition that keeps the claim
true. It is not the place to put a claim about one function because that function's
section is crowded. If most of a file's citations have collected in its docstring, that is
the tell.

**Ask rather than eyeball it.** Where a project has turned the rule on, `references`
reports a citation that sits outside the span its entry pins, and `claims-ledger sha
--write` reports it for the entry in front of you — which is the moment it becomes
answerable, since the citation is written in the commit before the entry and until the
Grounds exist there is no span to be outside of. Whether a project asks at all is
`citation-placement` in its configuration, and it is off unless somebody set it:

    python -c "from claims_ledger import open_ledger; print(open_ledger().config.citation_placement)"

`off` does not mean the rule is wrong for that project. It usually means the project has
citations that would fail it, and turning it on is a sweep followed by the setting.

## Documents and grounds are different

- **Documents** are the prose scanned for citations. Ask which files those are:

      python -c "from claims_ledger import open_ledger; print(open_ledger().config.documents)"

- **Grounds** are evidence, and the document list does not gate them. A ground names any
  path the project holds.

So a file being outside the document list means only that prose in it cannot carry a
citation — never that a claim about it cannot be grounded.

## One commit

The citation usually sits inside the span the entry pins, and a ground anchored by value
names that span by the digest of its text rather than by a revision, so the code, the
citation and the entry land together. Write each ground's anchor as `=?`:

    - code: src/thing.py § "widget" =?

`claims-ledger sha --write <entry>` fingerprints the entry and fills every `=?` with the
digest of the section as the working tree has it. Then commit the three as one; the
pre-commit hook passes on the first try, because the entry the citation names is there
and the anchor matches the tree. A ground can still be written `@<commit>` by reference,
and that is the form a history rewrite destroys; by value, a squash or rebase costs only
the diff a person would read during repair.

## Choosing a ground

A ground should name what makes the claim true and nothing else.
`reference/choosing-a-ground.md` has the cases. The short of it:

- **Name the thing that carries the rule**, not something that merely follows it. A ground
  on a consumer goes stale for every edit to that consumer.
- **Narrower is not always better.** A ground that can never go stale is worse than one
  that goes stale often, because nothing will ever tell you. Check what a narrow pattern
  actually spans before resting a claim on it — `claims-ledger references` prints what it
  read.
- **Grade honestly.** `claims-ledger new --help` lists the grades. A choice the project
  *made* is `asserted`, forbids an evidence ground, and never goes stale. A statement that
  something *does* what it says is `measured` and takes a pin that `freshness` watches.

Several claims resting on one section is a normal shape — it is what enumerating a
section's invariants looks like. The count is also how many entries the next edit inside
it flags.

## Ask who is already there

    claims-ledger neighbours 'code: path/to/file.py § "the_section" =?'
    claims-ledger neighbours <entry id>

Once a ground is chosen and before the entry is written, this answers with the entries
already resting on that span, or whose Scope `cohort` nests inside the one being drafted.
The pointer form is the one that works before the entry exists — the question is asked of
the ground being considered.

It is advisory. It exits 0 whatever it finds, `check` does not run it, and it decides
nothing. What it is for is the pair no checker can see: two entries about the same
function that name nothing of each other are out of range of every rule by construction,
and the moment the grounds are being chosen is the only moment anything asks.

Each answer says whether the ledger already relates the two. For one it does not:

- **The same claim, said twice** — write one entry, or supersede the older.
- **Different claims about the same artifact** — record it once, as a `distinguishes`
  ground in the entry being written, with the Warrant saying how they differ. It sits
  *beside* the grounds the entry rests on: a distinction is not support, and `validate`
  reports an entry whose every ground is one. `choosing-a-citation-act` has the act in
  full.
- **Neither** — near is not inconsistent, and most neighbours are neither. Leave them.

The answer ends with the ground line for each pair it did not find a relation for, written
out verbatim, so recording one is a paste rather than a recollection. Grounds are frozen
once an entry is committed, so those lines go in the entry still being written; between two
committed entries the distinction waits for whichever is superseded next. Deciding is still
yours — but if the answer is that they are different claims, that is an entry-shaped
commitment and it is written in this pass, not noted for a later one.

`claims-ledger neighbours --count` prints the distribution over a whole ledger — median,
mean, most, and how many entries have none — which is what says whether the lookup is
worth running on a given project.

## What `validate` checks in the wording

`claims-ledger validate` applies rules to the wording itself, and reports each by name.
Three worth knowing before drafting. Two read the Assertion:

- **An Assertion that reads as an absence or a priority claim needs a `search:` ground.**
  The test is on words, not sense, so an ordinary sentence can trip it. Rewording is
  usually cheaper than adding a search ground you did not mean.
- **An Assertion carries no quotation marks.** Quoted material belongs in Backing, where
  it is checked against its source.

And one reads the Scope against the Warrant:

- **A Scope and a Warrant name one set of statuses, not two nested ones.** Where a Scope
  names each of the ways an entry falls and never says `terminal`, while the Assertion or
  Warrant does, `validate` **flags** it. Those are two populations — a status can be
  terminal without being a fall — and it is the Warrant a person implements, so an entry
  written that way states one rule and gets another. A flag, not a failure: widening the
  Scope and narrowing the Warrant are both legal repairs, and only the author knows which
  claim was meant. The finding names the status that separates the two sets, and
  `choosing-a-citation-act/reference/vocabulary.md` has the statuses with which are
  terminal.

`reference/entry-anatomy.md` covers what each section of an entry is for.

## Order of operations

1. List the sentences in the file that promise something.
2. Draft each Assertion.
3. Choose each ground: the narrowest section that carries the rule.
4. `claims-ledger neighbours` on each ground, before writing the entry, and decide what to
   do with anything it surfaces.
5. Write every citation, each inside the section its entry pins.
6. `claims-ledger new <slug>` per entry; fill Assertion, Scope, Grounds, Warrant and
   Backing; write each ground's anchor as `=?`; add the `## References` row naming each
   citing document and the act it uses.
7. `claims-ledger sha --write` on every new entry, before it is committed — it fills the
   anchors from the tree, and refuses an entry version control already has.
8. `claims-ledger check`, then one commit — code, citations and entries — with the hook
   running.

Step 8 will report drift on entries already pinned to the sections the citations went
into. That is expected and it is the mechanism working; `repair-a-drifted-pin` covers
discharging each with a re-read, which goes in the same commit.

## Reference

- `reference/entry-anatomy.md` — the sections of an entry and what each is for.
- `reference/choosing-a-ground.md` — ground width, and the two failures that are cheap to
  avoid while writing and expensive afterwards.
