---
id: A0205-an-eval-sync-crash-reads-as-distilled-not-undistilled
kind: claim
stated: 2026-09-25T01:39:48-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 57fddb99df89129c7f88e39ab0ad6ff791f7dad5c890332a5d69147b17fd98f8
---

## Assertion

A session-end log whose extract finished with no failures and whose chained `thalamus eval sync` then crashed is reported by the console as a failure of the sync on a distilled session, and never as a distillation that did not happen.

## Scope

metric: the detail the console derives for a session-end log whose run ended in a traceback
cohort: every `~/.thalamus/logs/session-end-<sid8>.log` the pin ledger vouches for, whichever harness's hook wrote it
condition: the latest run holds a summary line reporting zero failures, a traceback below it, and no `extract exited N` line; a traceback with no summary above it is extract's own crash and is A0178's subject

## Grounds

- code: src/thalamus/console/distill.py § "_classify" =sha256:a5906bdbd52910d271a666e19443cf1c2c393f34a13f8a61d984a210dfe48ab2
- entry: A0178-a-crashed-extract-is-a-failure-not-a-stall · distinguishes
- entry: A0156-the-last-run-in-a-log-decides-the-row · distinguishes

## Warrant

Both hooks run `eval sync` only after extract has printed its summary — the claude-code hook after checking extract's exit status, the codex hook unconditionally — so within one run a traceback below a clean summary can only be the sync's. The section compares the index of the last traceback mark against the index of the summary line and, when the traceback is below a zero-failure summary and no exit line was recorded, prefixes the exception line with `distilled; eval sync failed`, keeping the row in the error state.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
