---
id: A0137-write-reuses-check-verified-bytes-within-a-day
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 75f9f489ab02fd2e4bc5c8fc17c527d8af2cfa2efc5c90e5472e64c768c1d160
---

## Assertion

Bytes a recent `--check` already fetched and retained are reused by a following ingest for a bounded window rather than being fetched again, and that window is one day.

## Scope

metric: how long a `--check`'s verified bytes are reused instead of being re-fetched
cohort: the reuse window on a previously verified fetch record
condition: not the fallback-to-fetch behaviour when the archived bytes are missing or the window has expired, which this entry does not claim about

## Grounds

- code: src/thalamus/harness/ingest.py § "_VERIFIED_WINDOW_SECONDS" =sha256:5234bbea61a79fea5a4df16603a82d2fe63f31005cf2d3de987e5419e1cc45ac

## Warrant

`_VERIFIED_WINDOW_SECONDS` is set to `24 * 60 * 60`, and it is the exact bound `_verified_bytes` compares a prior fetch record's age against before deciding to reuse its bytes instead of issuing a new request; the value is the window, in seconds, directly.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T13:51:40-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/ingest.py § "_VERIFIED_WINDOW_SECONDS" =sha256:5234bbea61a79fea5a4df16603a82d2fe63f31005cf2d3de987e5419e1cc45ac
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-18T13:55:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: packages/thalamus-ingest/src/thalamus_ingest/ingest.py § "_VERIFIED_WINDOW_SECONDS" =sha256:5234bbea61a79fea5a4df16603a82d2fe63f31005cf2d3de987e5419e1cc45ac
  note: harness/ingest.py moved into the thalamus-ingest plugin package as thalamus_ingest/ingest.py; the window is still one day, so the assertion is unaffected

## References

- CLAUDE.md · standing · cites-as-live
