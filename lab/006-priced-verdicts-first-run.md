# 006 — First priced eval run: half the injected retrieval tokens are wasted

**Date:** 2026-07-16 · **Component:** eval loop layer 1b (cost join) · **Status:** measured

## What was measured

Layer 1b landed: Trace nodes now carry `injected_chars` (the rendered response —
the response *is* the injection cost), and `eval report` prices every used/ignored
verdict at an even per-node share (`injected_chars / returned_count`). Re-syncing
the tap backfilled every existing trace via the upsert's on-match path — no
migration, the write path was already idempotent.

First priced run over scope `main` (18 retrievals, 5 sessions, 562 returned nodes):

- **~43.6K tokens** rendered into context by retrieval, total;
- attributed split: 267 used (48%) vs 295 ignored;
- priced split: **~21.9K tokens earned vs ~21.6K wasted (50%)**.

Scope `literature` for contrast: ~731 tokens injected, 25% wasted — small, but the
expert scope's precision is visibly better than main's.

## What the waste ranking shows that counts couldn't

Ranking decay candidates by wasted tokens instead of repeat count reorders the top
of the list: two open-thread nodes ignored only 2x each (~355 tokens apiece)
outrank claims ignored 4x, because threads render bigger. The 4x-ignored cluster
is itself a finding: they are **stepmania-session claims pulled into thalamus
sessions by broad recall queries** and never used — cross-project bleed, exactly
the scoping signal docs/02 wants for pin-quality grading.

## The wider cost question this closed

The run that motivated layer 1b ("am I ripping through my session limit on
retrievals or experts?") answered **neither**: over Jul 14–16, interactive session
burn was ~56M weighted tokens against ~0.15M for all expert consultations, ~51K
rendered by retrieval, and ~350K weighted per steady-state extract run (the 18.7M
extract total was dominated by the one-time Jul 15 bootstrap). Session *length* is
the burn; memory's marginal cost is roughly one distillation pass per session.

## Dials on the record (pressure-test targets)

- Even per-node share within a response — big nodes in a mixed response are
  under-priced, small ones over-priced.
- 4 chars/token, unmeasured against a real tokenizer.
- Weighted-token limit proxy in `eval/cost.py` (0.1x cache read, 1.25x cache
  write, 5x output) — API-price ratios standing in for unpublished limit weights.
- The 50% waste number inherits every layer-1 attribution caveat (lexical
  matching, lab/002's evidence-selection lesson).

## Moral

The denominator was the missing half of the fraction, and it was already lying in
the tap — pricing verdicts took a property and a join, not new telemetry. A node
retrieved-but-ignored twice can now out-rank one ignored four times, which is the
difference between "annoying" and "expensive," and layer 3's forgetting policy
should decay for *expensive*.
