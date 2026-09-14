# What an entry holds

`claims-ledger new <slug>` writes a scaffold with every section present and placeholders
where judgement is needed. The placeholders are deliberate: the checkers have plenty to
say about them, which is what stops a draft being mistaken for a finished entry.

    claims-ledger new --help          the frontmatter options and what each means

## Frontmatter

`id`, `kind`, `stated`, `author`, `grade`, `supersedes`, and `verbatim_sha`. Predictions
and hypotheses also carry `credence` and `resolves_when`.

`verbatim_sha` is a fingerprint over the parts of the entry that must not drift after it
is committed. `claims-ledger sha --write <path>` computes it, fills each ground's `=?`
anchor with the digest of its section as the tree has it, and refuses an entry that
version control already has — so it is run before the entry's first commit, not after.

## Assertion

One claim, in the project's own words, with no quotation marks. This is the sentence a
reader is being asked to rely on, and the sentence a citing document is held to.

## Scope

`metric`, `cohort`, `condition` — what is measured, over what, under what circumstances.
Scope is prose a reader checks, and it does not go stale, so a claim whose cohort is
broader than any single ground can say belongs here rather than in more grounds.

## Grounds

Typed pointers to the evidence. One per line. A sectioned type names a span and may carry
a revision:

    <type>: <path> § "<section>" @<revision>

Grounds sit above the append marker and cannot be edited once the entry is in history.
That immutability is what makes a pin reproducible, and it is why re-establishing a claim
on new evidence is a new entry rather than an edit.

Not every ground is evidence. An `entry:` ground names another entry and carries an act,
and two of those are relations rather than support: `challenges`, which disputes the other
entry and demands a verdict on it, and `distinguishes`, which says the two are different
claims about the same artifact. `validate` reports an entry whose every ground is a
distinction, because it has said what it is not and rested on nothing. Because Grounds are
frozen, only the newer entry can write either one; the older never points back.

## Warrant

The rule by which the grounds support the assertion — the step a reader would otherwise
have to supply. This is where a claim whose Scope is wider than its grounds says how the
pattern generalises.

## Backing

Quotations, each naming its source and speaker. `claims-ledger resolve` holds every
quotation to the source it names: the text must be there, elisions must be marked, and a
paraphrase inside quotation marks is a finding. `none` is a legitimate value.

## The append marker

    <!-- APPEND BELOW THIS LINE ONLY -->

Everything above it is frozen once the entry is committed. Everything below — Verdicts and
References — grows.

## Verdicts

Append-only. Each carries a timestamp, a status, a grade, an author, an evidence pointer
and a note. The entry's status is derived by walking this list; nothing stores it.

Verdicts the machinery writes carry provenance the checkers hold them to, which is why
`claims-ledger freshness --write` and `claims-ledger propagate --write` exist rather than
leaving them to be typed.

## References

One row per document that cites this entry, and the act it cites with:

    - path/to/document.md · standing · cites-as-live

`claims-ledger references` checks this against the documents themselves in both
directions: every citation must be listed here, and every row here must name a document
that really cites it that way.
