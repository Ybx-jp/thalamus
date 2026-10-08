---
id: A0215-teardown-noise-is-not-a-crash
kind: claim
stated: 2026-10-06T17:59:20-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 57f926e3cf501ffbd910f7a7fb5c49dada0108717c81d50e0acbdd3db6409836
---

## Assertion

A traceback Python printed for an exception it ignored during interpreter teardown is not read by the console as the crash that ended a distillation, and does not supply the row's detail.

## Scope

metric: which distillation state and detail the console derives for a session-end log carrying a traceback introduced by an `Exception ignored` line
cohort: every `~/.thalamus/logs/session-end-<session id>.log` the pin ledger vouches for
condition: the ignored traceback is the only one in the latest run, or it follows a real traceback before the hook's exit line

## Grounds

- code: src/thalamus/console/distill.py § "_traceback_starts" =sha256:21e81822e88b8982b5ed3a79221a91cb46c0cae2e2bb16e0bda91fbefd33eff0
- code: src/thalamus/console/distill.py § "_crash_detail" =sha256:8d9abbaba0f081981f07a6317ee2e192c5cf66f2608460d57100c1fa3486be9c

## Warrant

`_traceback_starts` drops every `Traceback (most recent call last):` line whose previous line begins `Exception ignored `, which is the header CPython writes for an exception raised in a finalizer and swallowed; `_classify` decides crash-versus-not on that list, so a log whose only traceback is teardown noise falls through to its summary or to the clock. `_crash_detail` stops reading the final real traceback at the first `Exception ignored ` line, so noise printed after a real crash cannot become the last unindented line it returns.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
