---
name: repair-a-drifted-pin
description: Discharge a finding from `claims-ledger freshness` — moved, withdrawn, unstable pin or unknown — by choosing among acknowledging an immaterial change, superseding the entry, or recording that the claim did not survive. Use when freshness or check reports any of those, when the pre-commit hook refuses a commit, and when an edit lands inside a span a ground names.
---

# Repair a drifted pin

`claims-ledger freshness` compares each pinned ground against the revision it names. It
reports four things, and they do not mean the same thing.

**This is the wrong skill if** the finding names an act and a status —
`<act> against <id>, whose status is …`. That is `claims-ledger references` objecting to a
citation, and `choosing-a-citation-act` covers it.

## Read the finding before deciding anything

    claims-ledger freshness

| finding | | what it needs |
| --- | --- | --- |
| `fresh` | silent | nothing |
| `has moved` | flag | a discharge, below |
| `withdrawn` | fail | a discharge, below; the path is gone from the working tree |
| `unstable pin` | flag | re-pin at a revision — **no verdict discharges this** |
| `unknown` | fail | fix the repository — **no verdict discharges this** |

The last two are not drift. An `unstable pin` names no revision, so there is nothing to
compare and nothing to discharge. An `unknown` is version control declining to answer, and
a verdict written over it records a judgement nobody made.
`reference/findings.md` has each in full, including which kinds of change land where —
a rename reports as `withdrawn` rather than `moved`, because the path a ground names is
gone from the working tree.

## Discharging a moved or withdrawn ground

### 1. Let the machinery record what it saw

    claims-ledger freshness --write

This appends a `contested` verdict carrying the drifted pointer and what the artifact
reads as now. Exit 1 is correct — it wrote something. Write this one with the tool rather
than by hand: it carries provenance the checkers hold it to, and a hand-written one under
the propagation author claims a check that did not run.

The entry is now `contested`, so `claims-ledger references` names every document citing it
`cites-as-live`. That list is the prose the repair has to reach.

### 2. Decide what actually changed

Read the Assertion against the artifact as it now stands. Four outcomes, and the checkers
accept all of them.

**The artifact moved; the claim is untouched.** A renumbering, a reformat, a section moved
within a file or to a different file, a rename. Append a `corroborated` verdict naming the
section where it now is, at the current revision, with a note recording the move:

    - <timestamp> · corroborated · grade: <grade> · author: <you>
      evidence: <type>: <path> § "<section>" =?
      note: <what moved, and that the assertion is unaffected>

The anchor is stated by value: `claims-ledger sha --write <entry>` fills `=?` with the
digest of the section as the working tree has it, on a committed entry too, since the
verdict sits below the append marker. A reading by value needs no commit to be placed at,
so it goes in the same commit as the edit it read. `@<revision>` is still accepted and
names a commit that has to exist already.

`contested` is not terminal, so the status moves to `corroborated`, citations that read
`cites-as-live` stay legal, and the entry keeps its id. The evidence must name the artifact
as it is now rather than restating the ground — `claims-ledger validate` refuses a
corroborating verdict pointing at a ground the entry already cites, which is what makes
this a record of a reading rather than a restatement.

That is the whole repair for an immaterial change. What it asserts is that someone went and
looked; the ground stays as written, and the verdict is the note tracking where the artifact
went.

**The claim is re-established on different evidence.** Supersede —
`reference/superseding.md` has the sequence. A ground cannot be edited once the entry is in
history, so a claim resting on new evidence is a new entry.

**The claim no longer holds.** Append a `refuted` or `retracted` verdict whose evidence
points at what settles it, and rewrite the prose. Citations move with the sentence.

**The question is open and should stay visible.** Leave the entry `contested` and change
the citing prose to `cites-as-contested`. `choosing-a-citation-act` covers writing that on
both sides. Visible in the prose, that is: the ground itself is compared from its last
reading and its recorded drift discharges it there, so `freshness` says nothing more about
it until a corroboration is appended.

## Before writing a successor, ask what moved

If a span changed for a reason the claim does not name, the *ground* is the thing that was
wrong, and carrying it into a successor buys another supersession on the next unrelated
edit. Narrow it instead: name the thing that carries the rule rather than something that
follows it, and configure a section pattern if the claim is about something smaller than a
whole definition or table.

The tell is mechanical. `claims-ledger sha --write` on the successor computing a
`verbatim_sha` byte-identical to its predecessor's means the claim never moved and only its
ground did — the case where narrowing is the whole of the repair, and often the case where
acknowledging is enough and no successor is needed at all.

## Two things that stay true

**Verdicts append and only append.** Everything above the append marker is frozen once the
entry is in history, and `claims-ledger validate` compares against history to catch an edit
there. Repair by adding to the end, never by revising a ground or removing a verdict.

**Land it without rewriting history.** A ground stated by reference names a revision, so a
squash merge, a rebase merge or a force-push over rewritten history removes the evidence
for every such ground pinned into the vanished commits at once, and each one then costs a
supersession. Merge commits only, on any branch whose commits a ground names by
reference. A ground stated by value loses only the diff a person would read during
repair, and a reading of the section as it now stands moves it past that.

## Reference

- `reference/findings.md` — the four findings, what produces each, and what discharges it.
- `reference/superseding.md` — the supersession sequence, both directions checked.
