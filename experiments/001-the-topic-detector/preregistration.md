# Pre-registration — experiment 001

Committed **2026-07-30**, before the calibration was run against either snapshot.
Git history is the timestamp; this file is not edited after the first run, and a
change to it is a new experiment rather than a revision of this one.

## Question

How much of Thalamus's used-vs-ignored rate is retrieval utility rather than shared
project vocabulary, and does any judge variant separate the two better than the
shipped one?

## Hypothesis

H1. The shipped lexical judge carries little discrimination above a cross-session
permutation null.

H2. Narrowing the judged window to **tool-call inputs** carries more, because acting
on a retrieved path is a narrower coincidence than echoing a word in prose.

## Endpoint

κ = (p − p̄₀) / (1 − p̄₀), node-weighted, over every attributed `RETURNS` edge in
scope `main`, where p̄₀ is the mean used-rate over 200 rotations.

A rotation re-judges each retrieval against another session's output window, drawn
from the same window-length stratum (quartiles). Both constraints are part of the
endpoint, not implementation detail: without the cross-session constraint the null
contains the case's own vocabulary, and without the length stratum it measures the
window-length change it introduced.

## Falsifiers

- **H2 is false** if κ for the tool-only judge does not exceed the shipped judge's κ
  by more than the null's own half-width.
- **The purge contrast is null** if κ computed on `pre-sandbox-purge` and on
  `post-sandbox-purge-20260730` differ by less than the null's half-width — i.e. the
  307 self-distillation sessions were not what made the instrument look weak.

## Stopping rule

200 rotations per judge, fixed before the run. The corpus is the entire census at
the pinned snapshot, so there is no sampling decision left to stop: n is whatever
the graph holds.

## Judges scored

Fixed before the run, seven, all defined in `thalamus.eval.attribution.JUDGES`:
`shipped`, `prose`, `tool`, `bounded-1`, `bounded-3`, `bounded-10`,
`tool-bounded-3`.

## What would make the result uninterpretable

Declared in advance so it cannot be discovered afterwards and quietly discounted:

- Reconstruction fidelity below ~95% against the verdicts `eval sync` stored live
  would mean the replay is measuring itself rather than the instrument.
- A judge whose rate is near 0% or near 100% has no headroom, so its κ is unstable
  and must be read as "no signal available", not as "no signal found".

## Seed and data

Seed `20260730`. Snapshots `post-sandbox-purge-20260730` and `pre-sandbox-purge`,
both in `experiments/snapshots.jsonl` with their hashes.
