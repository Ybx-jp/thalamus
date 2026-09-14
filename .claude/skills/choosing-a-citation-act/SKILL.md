---
name: choosing-a-citation-act
description: Match a citation's act to the status of the entry it names, choose among the repairs available when a status moves, and relate two entries that turn out to be about the same artifact. Use when `claims-ledger references` reports "<act> against <id>, whose status is …" or "is shaped like a citation but … is not a citation act", when a citing sentence is being written or moved, when a drift, a challenge or a fallen ground has changed an entry's status, and when `claims-ledger neighbours` surfaces a pair to reconcile or distinguish.
---

# Choosing a citation act

A citing sentence promises one thing: that the act it names is true of that entry's status
as it stands. `claims-ledger references` checks exactly that, in both directions — the
citation in the document, and the row in the entry's `## References`.

When it objects, the sentence and the status disagree. Several repairs make them agree
again; they differ in what they assert and in what they cost.

**This is the wrong skill if** the finding says `has moved`, `withdrawn`, `unstable pin`
or `unknown` — that is `claims-ledger freshness`, and `repair-a-drifted-pin` covers it.
A finding naming an act and a status is about the entry's status, so re-pinning does not
reach it.

## Read the current state first

    claims-ledger status                 every entry and the status it derives to
    claims-ledger references             every citation, checked both ways

Statuses derive from the verdict list rather than being stored, so the status an entry had
when you last looked is not evidence about now.

## The acts

    claims-ledger references             names the act and the statuses it allows

`reference/vocabulary.md` has the full table and how to read it from the package rather
than from memory. In short: `cites-as-live` speaks of a claim in good standing,
`cites-as-contested` of one under question, `cites-as-fallen` of one that did not survive,
`challenges` is written by an entry that disputes another, and `distinguishes` by an entry
saying it is a different claim about the same artifact.

`cites-as-fallen` is legal against every status, which makes it available whenever the
prose means to discuss a claim as it stands rather than to rely on it.

**Two lists, not one.** A document may write the four citation acts; the last two are
written only as an `entry:` ground, by one entry about another. Print both rather than
remembering which is which:

    python -c "from claims_ledger import ACTS, ENTRY_ACTS; print(ACTS); print(ENTRY_ACTS)"

Writing `distinguishes` in a document is reported, not ignored — `references` names an id
this ledger minted, followed by a comma and an act-shaped word that is not a citation act,
which is also what catches a mistyped act. The repair is the act, not the sentence.

## When a status moves

The status is a question put to a person, and these answers are all legitimate. Pick the
one that describes what is true.

**Say what is now the case — change the act.**
Update the citation in the document and the matching row in the entry's `## References`.
Both sides, or `references` objects the other way. The entry keeps its status, the
sentence describes it accurately, and the check is clean.

**Re-establish the claim on the artifact as it stands — supersede.**
A ground cannot be edited once the entry is in history, so a claim re-established on new
evidence is a new entry: `claims-ledger new <slug> --supersedes <old-id>`, with the old
one carrying a `superseded` verdict and every citation moved.
`repair-a-drifted-pin/reference/superseding.md` has the sequence.

**Record that it did not survive.**
Append a `refuted` or `retracted` verdict whose evidence points at what settles it, then
rewrite the prose. Citations move with the sentence, or become `cites-as-fallen` where the
prose still means to name the claim.

**Record that it still stands — corroborate.**
Append a `corroborated` verdict. This is a statement that a person went and looked, so it
carries what was read and when. Sincerity is the one thing no checker can check: a
corroborating verdict that records a reading nobody did leaves every checker clean over an
Assertion that is false.

Where the finding is a drift the claim does not depend on — a section that moved, a
renumbering, a rename — `repair-a-drifted-pin` covers acknowledging it without touching
the claim.

## `cites … from outside § "…"`

The entry named rests on a section of this very document, and the citation is somewhere
else in it. The repair is to move the citing sentence into that section, not to change the
act or the ground: what the rule is protecting is that a promise and the code keeping it
sit in one span, so that an edit reaches both.

It arrives only where a project set `citation-placement`, and it is the one `references`
finding that says nothing about a status. Moving the sentence flags every entry pinned to
the section it lands in — that is the mechanism, and `repair-a-drifted-pin` covers
discharging each with a re-read.

## Two entries about the same thing

Not every relation between two entries is agreement or attack. Two claims can be about the
same function, and be different claims — a pair no checker can see, because neither names
the other and every rule that reads an `entry:` edge is out of range by construction.

    claims-ledger neighbours <entry id | entry path | ground pointer>

Advisory. It exits 0 whatever it finds, `check` does not run it, and it decides nothing: it
answers with the entries sharing a ground span, or whose Scope `cohort` nests inside this
one's, and says which of them the ledger already relates. The ground-pointer form is the
one to use before the entry exists, while the grounds are being chosen.

Four honest answers to a pair it surfaces, and the command ranks none of them:

- **They are one claim.** Reconcile them — usually by superseding one, with its citations
  moved.
- **They are different claims.** Record it once, as a `distinguishes` ground in the newer
  entry, with the Warrant saying how they differ. It is legal against a target of any
  status, it propagates nothing, and it is not support — so it goes *beside* the grounds
  the entry rests on, never instead of them.
- **One disputes the other.** That is `challenges`, and it demands a verdict on the target.
- **Leave them.** Near is not inconsistent, and most neighbours are neither.

Only the newer entry can write the relation, because Grounds are frozen once committed. The
older one never points back; the lookup is what reads it from the other side, which is why
recording the distinction is what stops the next reader redoing the comparison.

The answer ends with the ground line for each pair it found no relation for, verbatim, so
that recording one is a paste. Which of them to write — if any — is the judgement the
command is handing over, and it is a judgement made in the pass that surfaced the pair: a
distinction noticed and left unrecorded is one the next reader pays for again, which is
the whole cost the act exists to remove.

## Writing a citation

1. `claims-ledger status` for the entry's status now.
2. Choose the act that is true of it.
3. Write it on both sides: the citation in the document, and the row in the entry's
   `## References`.
4. `claims-ledger references` before committing — it prints what it read.

Removing the citation also clears the finding, by removing the link the ledger exists to
keep.

## Reference

- `reference/vocabulary.md` — statuses, acts, grades and kinds, and the command that
  prints each of them.
- `reference/status-derivation.md` — how a verdict list becomes a status, and which
  verdicts stop the walk.
