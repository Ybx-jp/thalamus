# 007 — Query-shape autopsy: the hook was innocent, the dump was guilty

**Date:** 2026-07-16 · **Component:** reader recall path · **Status:** shipped, prediction on record

> **Erratum (2026-07-30).** Figures in this entry are withdrawn or bounded by [lab/034](034-the-corrections-the-instrument-forced.md); see its withdrawal list before citing anything here.

## The hypothesis (operator's)

Open threads were topping the waste ranking because the SessionStart hook fires a
blanket `memory_open_threads` on every session.

## What the priced traces actually said

Half right, and the wrong half mattered more:

- **Mechanism confirmed**: every wasted Thread token traces to the session-first
  `open_threads` call. **Magnitude refuted**: ~1.4K tokens total, and that call is
  the *best-performing* retrieval in the tap — 68% used, vs 46% for mid-session
  `memory_recall`. The hook stays.
- **The real sink**: mid-session `memory_recall`, ~19.7K tokens wasted. Worst
  queries returned 50–81 nodes at 28–40% use; best returned 3–5 at 66–80%. The
  shape signal was **fan-out, not wording**.

## Root causes (both in `reader.recall`)

1. **OR-matching with no floor** — one generic keyword out of ten ranked a
   session. That is the cross-project bleed from lab/006: stepmania sessions
   matching thalamus queries on "memory, evaluation".
2. **Indiscriminate detail dump** — a matched session rendered *every* claim it
   contains. 267 of 295 ignored nodes were these ride-alongs.

The `matched on:` line also listed every query keyword rather than the terms that
hit — a lie in the audit trail, now fixed to report actual hits.

## The fix (BudgetMem's low-budget tier, instantiated — arXiv 2602.06025)

- Match floor: a multi-keyword query must hit ≥2 distinct terms (single-keyword
  queries untouched).
- Details render only claims the query's terms touch, capped at 8, remainder
  elided to an honest stub carrying no vertex ID — the eval loop never prices
  phantom returns.

Replaying the worst bleeder ("execution provenance, evidence tracing, consultation
records...", formerly 77 nodes / ~5.0K tokens / 28% used): **6 nodes, ~0.9K
tokens**, top result on-topic. 83% injection reduction on the worst shape.

## Prediction on record

Over the next ten synced sessions, `eval report` scope `main` should show:
recall fan-out ≤ ~15 nodes/trace, wasted share falling from 50% toward ≤30%,
with used% *not* falling (if used% drops, the floor or the cap is eating real
matches — loosen the dial, don't celebrate the savings).

## Dials added (pressure-test targets)

- Floor of 2 distinct keyword hits — blunt; scoring by hit *fraction* is the
  obvious refinement if it over-filters.
- Detail cap of 8 — arbitrary; the elision stub says what it hides.
