# lab/057 — The reader who could not say which

**Date:** 2026-08-11 · Built from `teacher`'s P6 proposal in room `atlas`
([lab/056](056-the-charter-was-wrong-about-our-own-walls.md))

The room shipped two dashed markers carrying meaning at **2.07:1** and **2.97:1**, under
WCAG 1.4.11's 3:1 floor. Two reviewers and three rounds missed them. So did the cold-read
comprehension instrument, and `teacher` diagnosed why:

> Every cold reader in this room received a full-fidelity rasterisation, so every one of
> them had perfect contrast sensitivity, and the instrument is blind to contrast failure
> *by construction*.

`thalamus eval legibility` is the arm that fixes that.

## The transform

Degrade the **SVG**, not the raster. Rasterising then filtering needs an imaging stack the
runtime dependency set deliberately does not carry (`numpy`/`scipy` sit behind the
`experiments` extra); a source transform needs nothing, is exact rather than resampled, and
leaves a variant that can be diffed and looked at.

Relative luminance is linear in the linearised channels, so compressing every channel
toward the surface compresses the luminance *difference* by exactly the same factor. With
`S = Ls + 0.05`, requiring a pair at threshold `T` to land on a floor `F`:

```
L_T − Ls = S·(1/T − 1)      L_T′ − Ls = S·(1/F − 1)
a = (1/F − 1) / (1/T − 1)
```

**`S` cancels — the factor is independent of the surface.** One number degrades any aid,
which is what makes "below threshold lands below the floor" a general property rather than
a per-aid calibration. At `T=3.0, F=1.5`, `a = 0.5` exactly.

| marker | before | after |
|---|---|---|
| the shipped defect | 2.07:1 | **1.35:1** |
| the second defect | 2.97:1 | **1.50:1** |
| the WCAG threshold | 3.00:1 | 1.500:1 |
| the correction | 4.24:1 | **1.62:1** |

The arm is a **threshold amplifier**: it does not merely make everything fainter (it does),
it carries the criterion onto the legibility floor so the ordering either side of it
survives and becomes visible to a reader.

## Validation, in two steps

**1. Mutation — ground truth by construction.** `--mutate '#6e7781' 2.07` re-shades the
corrected marker back to the contrast it originally shipped at. The audit catches exactly
one failing colour, at the right role and the right ratio; the parent passes.
`--strict` exits 1 on the mutant and 0 on all four shipped aids. Without a mutant, "the
degraded reader missed it" is unfalsifiable — a reader can miss a thing for any number of
reasons.

**2. The reader.** Two subagents, same prompt, same spawn, same aid, differing in one
colour. Key pre-registered before either ran: *pass Q1 only if the reader names tier 0 and
tier 3 as the marked pair.*

- **Corrected artifact, degraded (marker at 1.62:1)** — passed:
  > "Tier 0 and tier 3 (the first and last boxes) have dashed outlines, while tier 1 and
  > tier 2 have solid outlines."

- **Mutant, degraded (marker at 1.35:1)** — failed, and failed informatively:
  > "the image is rendered at such low contrast that I cannot reliably tell you which pair
  > is which. I should not guess. What I can state confidently: the four boxes are *not*
  > uniform."

The mutant reader could resolve *that* two boxes were marked and not *which*. Its first
instinct named tier 2 and tier 3 — **wrong** — and only its own self-check caught it. A
less careful reader would have reported a falsehood with confidence, which is the exact
failure the marking exists to prevent: a reader who cannot resolve it sees the unwritten
tiers as ordinary rows.

## Two design corrections found while building

**The instrument produced a false positive on its first real run.** `scopes.svg` reported
white text failing at 1.07:1 — white text on a dark `#1f2328` pill, which is 15.80:1 and
correct. Measuring every colour against the page canvas is wrong for anything sitting on a
chip, and resolving it properly needs geometry and z-order this module does not do. So a
colour that fails against the surface but *would* clear its threshold against another fill
in the file is reported **indeterminate, naming that fill** — one specific question a
reader settles by looking. An instrument that cries wolf is one nobody runs, which is the
failure mode this whole line of work is about.

**Both WCAG criteria are carried, not just the one that was missed.** An instrument
covering only 1.4.11 would reproduce the room's defect in the other direction. Roles are
read off usage rather than declared: `text` from `<text>` and the inherited root fill,
`meaningful` from `stroke-dasharray`, `decorative` otherwise. Text wins where a colour does
both jobs, since 4.5 is the stricter floor.

The palette scan reads **strokes as well as fills**, because the room's reviewer extracted
`fill=` alone, reported a nine-colour palette as five, and could not have found either
defect — both were strokes.

## What it does not claim

It is a screening instrument keyed to a published threshold, **not a simulation of any
particular person's vision**, and the distance between those is not something this closes.
`report()` prints the arithmetic so the claim is disputable rather than trusted. A reader
who loses a distinction has demonstrated that the distinction was carried by contrast the
threshold does not protect — no claim about prevalence, severity, or any real reader's
experience.

Greyscale is a **separate arm** on purpose: it holds luminance fixed, so what it tests is
only whether hue was load-bearing. An aid can pass either and fail the other, so composing
them would make a failure unattributable.

The reader arm inherits `teacher`'s own correction (lab/056): a subagent on this machine
gets `CLAUDE.md` and the skill descriptions in its system prompt, so no reader is truly
cold. The defence is that the contamination is **matched** — both arms spawn identically
and differ only in the artifact — so the differenced result holds while any absolute claim
about "a stranger" does not.
