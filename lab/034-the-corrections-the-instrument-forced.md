# 034 — Calibrating the instrument withdrew more numbers than it produced

**Date:** 2026-07-30 · **Component:** eval layer 1 (`eval/calibration.py`, `eval/waste.py`, `eval/snapshots.py`) · **Status:** measured + withdrawal list. Supersedes the magnitudes in lab/006–007, lab/018, lab/024, lab/029, lab/031–032.

## What happened

Two consultations — eval-methodology and literature, run against the whole corpus —
converged on one diagnosis: the project had been quoting rates with no null, no
interval, and no way to regenerate them. Acting on it produced two published
experiments and a longer list of numbers that stop being citable.

The programme is in `experiments/`; this entry is the ledger.

## Built

| | what it closes |
|---|---|
| `thalamus snapshot --name/--serve` | Every lab figure was computed against a live graph that moves at every session end. A published number now cites a hash-identified state, served read-only from a throwaway container. |
| `eval/calibration.py` | The permutation null as a standing instrument: cross-session, stratified on window length, with its own interval, a paired κ bootstrap, and a reconstruction-fidelity gate. lab/032's script existed only in a scratchpad and could not be re-run. |
| `attribution.JUDGES` | Judge variants (prose / tool-call / bounded-N) scored *beside* the shipped judge instead of replacing it. The shipped window is byte-identical, so stored verdicts keep meaning what they meant. |
| `eval/waste.py` | Ratio-of-totals waste with sessions as PSUs, a delete-one-session jackknife, ICC and design effect, and the token-weighted chance correction. |

## Measured

**experiments/001.** Shipped judge: 63.3% used against a 57.3% permuted null,
**κ = 0.140 [0.028, 0.272]**. Six pre-registered alternatives; none beats it. The
pre-registered hypothesis — that tool-call inputs discriminate better than prose —
is **falsified** (κ 0.138, inside the null's half-width), and prose-only is clearly
worse (0.053), so the axis is quantity of window rather than kind of evidence.

The null's *design* is worth more than the judges are: stratified 0.140 against
unstratified 0.186, a 0.046 swing.

**experiments/002.** 33.8% of injected tokens judged unused, **95% CI [27.2, 40.5]**,
±6.6pp — 3.5× the interval a verdict-level estimator would have claimed. Chance
corrected: about **17.5% of injected tokens are demonstrably earned**. ±3pp needs 143
sessions against 29; the corrected figure cannot be reached by waiting at all.

## Two findings that were not on anyone's list

**A control that could not fail.** The purge comparison was pre-registered as a
falsifier and is withdrawn as one. Both snapshots yield the same 222 retrievals
across the same 29 sessions: the 307 purged sessions made no retrievals, so they
were never in the rate or in the rotation pool. Only 37 verdicts (1.5%) differ.

**27% of verdicts sit on text that can change underneath them.** `Claim` vertices
are content-addressed on (kind, normalised description), so a rewrite mints a new
vertex and claim text is immutable. `Thread` and `Session` are upserted latest-wins,
and `ingested_at` carries the writing *session's* timestamp rather than the write
time — so the graph cannot say when a node's text last changed. Reconstruction
fidelity (99.1%) counts verdicts that *flipped* and is structurally blind to text
that moved without flipping one. The bias is directional: a session that retrieves a
thread and then rewrites it moves the real window toward the node and no rotated
partner's. κ on claims only — the auditable 73% — is 0.149 [0.041, 0.294], so this
did not produce the headline, but the exposure stands until the judged term-set is
recorded on the `RETURNS` edge at judgement time.

## Denominators, both snapshots

| quantity | pre-purge | post-purge |
|---|---|---|
| vertices / edges | 6,440 / 14,979 | 5,591 / 13,849 |
| Sessions (main / all scopes) | 422 / 445 | 122 / 139 |
| Threads (open) | 388 (260) | 335 (207) |
| SPAWNS : RESOLVES | 432 : 72 | 336 : 72 |
| Claims (problem) | 2,576 (664) | 2,434 (629) |
| SOLVED_BY | 602 | 575 |
| Traces / RETURNS | 541 / 2,810 | 541 / 2,773 |
| Sources | 527 | 221 |

Rescaling an old rate against these is wrong: the purge was not a random thinning.
Re-derive or withdraw.

## Withdrawal list

Stop citing these. Each affected entry carries a stamp pointing here.

- **lab/029, all graph-population figures** — 262 main-plane sessions, the 141
  `thalamus-extract-*` count, the project split, the 2×2, the odds ratio ~8, "83% of
  wasted claim volume", "off-project 75% ignored vs on-project 9%". Its
  `thalamus-extract-*` sessions *are* the class lab/033 purged. Direction may
  survive; no magnitude does.
- **lab/029's dial audit deltas** — used 50%→69%, wasted 46%→30%. A 19pp swing is far
  outside what a κ≈0.14 instrument can attribute to a dial. The fan-out counts
  (41.9 → 11.2 nodes) survive as fan-out.
- **lab/018's session cohort and its docs/04 republication** — "20/31 without
  conditioning, 11/11 with". Built by slug-filtering a directory that held 696
  sandbox dirs under names the filter never accounted for. The arm-level 2/21 stands.
- **lab/006 and lab/007 used-rates** — "half the injected retrieval tokens are
  wasted", the 68%/46% split, literature-scope 25%. Pre-purge corpus, pre-calibration
  instrument, n = 5 sessions, no interval. Replaced by experiments/002. The 83%
  replay reduction is a fan-out number and survives.
- **lab/024 §2's substrate census and §1's interim peek** — pre-purge; the peek is
  citable only as the anytime-valid demonstration it is labelled as, never as an effect.
- **lab/031's used-rate magnitudes** — every value sits at or below the ~57% null and
  the whole spread is inside the instrument's discrimination band. **The null result
  survives and is strengthened**: there was no dial to tune because there was no
  signal to tune on.
- **lab/032's absolute denominators** — 2,367 verdicts, 377 threads / 306 open,
  398:71 SPAWNS:RESOLVES. Its permutation *contrasts* survive in kind; its κ≈0.086 is
  not comparable to experiments/001's 0.140 because the nulls were drawn differently
  and both intervals contain each other.
- **Every `eval pins` "signal: healthy"** — the threshold sat below the null, so the
  negative branch was unreachable and the positive verdicts unfalsifiable. The report
  now declines to interpret its own numbers.
- **Mean-of-rungs and every power number derived from it** — ordinal-as-interval with
  a demonstrated sign reversal on this project's own data.

**Not withdrawn:** all arm-level results, the deterministic zero-model gates
(lab/017 7/7, lab/019 6/6), lab/021's contamination correction, lab/022's channel
enumeration, lab/030's dial isolation, and every null conclusion in lab/030–032.

**Ends in:** corrections.
