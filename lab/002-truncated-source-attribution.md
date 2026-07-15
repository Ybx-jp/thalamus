# 002 — Attribution against a truncated Source snapshot silently under-counts

**Date:** 2026-07-15 · **Component:** eval loop layer 1 (first live run) · **Status:** workaround

## What broke

The first live used-vs-ignored attribution run scored **0 of 18** returned nodes as
used — against a session whose transcript demonstrably echoed the retrieved content.
`outputs_after()` was seeing zero characters of agent output.

## Why

Two stacked causes, both instructive:

1. **A session distilled while still open accumulates multiple Source snapshots.**
   The live transcript grows between `--write` runs and content-hashes to a new blob
   each time (the Source-count growth documented in docs/10). Session `16a29708` had
   three snapshots: 61 KB, 96 KB, 1.75 MB. Sync picked one with `limit(1)` — Gremlin
   order is arbitrary, and it chose the 61 KB one, which ends hours before the
   retrieval being attributed. Attribution then correctly reported that a transcript
   containing nothing after the trace timestamp uses nothing.

2. **The verification trace itself had a timestamp after the agent's last output.**
   The session's `/clear` records extend to 15:35Z but its last assistant turn is
   ~12:00Z; a trace timestamped 12:00Z attributes against genuinely empty output.
   "0 used" and "attribution is broken" look identical from the summary line.

## Workaround

Sync now picks the **largest** snapshot (`order().by("byte_size", desc)`) — the most
complete evidence for the session. With that fix and a mid-session timestamp, the same
trace attributed 18/18 used (the self-recall degenerate case: a session's own claims
matched against its own transcript — expected, and impossible live, since the querying
session is never in the graph before it ends).

## Moral

An attribution number with no denominator check is a lie waiting to happen. The eval
loop's own first output was a false negative produced by evidence selection, not by
matching — the kind of failure docs/04 says to publish rather than quietly fix. A
`retrieved-but-transcript-empty` counter (distinguishing "ignored" from "nothing to
judge against") is the refinement this run motivates.

**Follow-up (same day):** byte_size was itself only a proxy — it assumes transcript
files never shrink, which Claude Code's compaction does not promise. Snapshots now
form an explicit lineage: a new transcript Source `SUPERSEDES` the session's previous
head at write time, consumers read the head (no incoming SUPERSEDES; `ingested_at`
breaks ties on pre-lineage data), and the live graph was backfilled. Selection is now
defined by provenance, not guessed from a file property.
