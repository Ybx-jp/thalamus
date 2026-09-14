# Superseding an entry

A ground sits above the append marker and is frozen once the entry is in version history,
so a claim re-established on different evidence is a new entry rather than an edited one.
That is deliberate: a claim resting on new evidence is a different claim from the one that
rested on the old, and the ledger should be able to tell them apart.

Supersession is a chain, never a tree — an entry carries exactly one `superseded` verdict,
and both directions are checked against each other.

## The sequence

    claims-ledger new <slug> --supersedes <old-id>

1. **Copy Assertion, Scope, Warrant and Backing across**, changing only what the new
   evidence changes. Where the Assertion is unchanged, say so; where it is not, the
   frontmatter carries a note of what moved.

2. **Pin the Grounds to the artifact as it now stands**, and ask whether the old ground was
   the right one before carrying it forward. If the span changed for a reason the claim
   does not name, the ground was too wide, and reusing it buys another supersession on the
   next unrelated edit.

3. **Append a `superseded` verdict to the predecessor**, whose evidence names the successor:

       - <timestamp> · superseded · grade: <grade> · author: <you>
         evidence: entry: <new-id> · supersedes
         note: <what changed, and what did not>

4. **Move every citation the reference check named.** Each citing document's inline
   citation, and the matching row in each entry's `## References` — the predecessor loses
   the row, the successor gains it.

5. **`claims-ledger sha --write <path>` on the successor before it is committed.** It
   refuses an entry version control already has, so this happens first.

6. **`claims-ledger check`**, then commit.

## One commit

The citations that move usually sit inside the spans the successor's grounds pin, and a
ground anchored by value names a span by the digest of its text rather than by a revision.
So the successor's grounds are written `=?`, `claims-ledger sha --write` fills them from
the working tree along with the fingerprint, and the moved citations, the predecessor's
verdict and the successor go in one commit with the hook running. A ground written
`@<commit>` by reference still works and is what a history rewrite destroys.

## The tell that a supersession was not needed

If `claims-ledger sha --write` on the successor computes a `verbatim_sha` byte-identical to
the predecessor's, nothing about the claim moved — only its ground did. That is the case
where acknowledging the change is the honest repair and the successor is unnecessary work;
the skill's first outcome covers it.

## Supersession without a drift behind it

Not every supersession starts at `freshness`. The Scope sits above the append marker with
the Grounds, so a Scope that turns out to say the wrong thing cannot be edited either —
and a claim whose Scope names a narrower population than the one it is really about is
repaired the same way, with a successor, even though no pin moved and no checker
complained.

The shape to watch for is a `cohort` that under-covers its own `metric`: the metric counts
over one population and the cohort names part of it. That is not mechanically decidable,
but it is findable — `claims-ledger neighbours` proposes entries whose cohort words nest
inside another's, which is exactly this shape seen from the outside. The successor states
the claim over the population the metric was always counting, and the `verbatim_change`
line in its frontmatter says what moved.

## What supersession costs

An entry file, a verdict, and every citation moved. It is the most expensive of the
outcomes, and the right one exactly when the claim now rests on something different from
what it rested on before.
