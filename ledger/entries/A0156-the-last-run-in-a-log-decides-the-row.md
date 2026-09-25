---
id: A0156-the-last-run-in-a-log-decides-the-row
kind: claim
stated: 2026-09-21T13:40:37-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 2934f4c33746f4334d6932f809d435e01e7d25c6694d0378aaf0114d8c668463
---

## Assertion

A session-end log is read as a sequence of distillation attempts and only its most recent one decides the console's row, so distilling a session again supersedes what the earlier attempt said about it.

## Scope

metric: how much of a session-end log body the console's classifier reads
cohort: every `~/.thalamus/logs/session-end-<sid8>.log` the pin ledger vouches for
condition: the hook's run mark is what separates attempts; a log that never reached one is read whole

## Grounds

- code: src/thalamus/console/distill.py § "_last_run" =sha256:74766a72d8618685311585297dbe2baeb1a2dd31fed3d19289d78df27d0c1da9

## Warrant

The section returns the log from its last run-mark line onward, and the classifier reads that slice rather than the whole body. A failure the next attempt fixed therefore leaves the row, which the dismissal machinery could only hide and never correct, and a failure the next attempt introduced is not covered by the summary line above it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
