---
id: A0178-a-crashed-extract-is-a-failure-not-a-stall
kind: claim
stated: 2026-09-21T13:40:37-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: ce660ffc6d8589586aeb18c2760e098c81b2b16ca6f4835f409cc577ca2d91a0
---

## Assertion

A distillation whose `thalamus extract` died on an exception is reported by the console as a failure naming that exception, and never as a stall or an abandoned run.

## Scope

metric: which distillation state the console derives for a session-end log whose run ended in a crash
cohort: every `~/.thalamus/logs/session-end-<sid8>.log` the pin ledger vouches for, whichever harness's hook wrote it
condition: a crash that reached the log — either as the non-zero exit status `session-end.sh` records or as the traceback the process printed; a crash that left no log at all is the killed-window row's subject, not this one

## Grounds

- code: src/thalamus/console/distill.py § "_classify" =sha256:19f622f2e6e10b6bd5eb56ecf58c5c08f693860dbf12c2ecda561500bce9c552

## Warrant

The section decides a non-zero `extract exited N` line and a `Traceback (most recent call last):` mark as `error` before it reaches the idle-time comparison that produces `stalled` and `abandoned`, so no crashed run can be aged into either. The detail it returns is the last unindented line of the final traceback, which is the exception type and its message. The two signals are taken as alternatives because the two hooks differ: `hooks/claude-code/session-end.sh` checks extract's status and writes the exit line, while `hooks/codex/session-end.sh` checks none and leaves only the traceback.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-25T01:40:56-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/console/distill.py § "_classify" =sha256:19f622f2e6e10b6bd5eb56ecf58c5c08f693860dbf12c2ecda561500bce9c552
  artifact: sha256:a5906bdbd52910d271a666e19443cf1c2c393f34a13f8a61d984a210dfe48ab2
  note: propagated from a moved ground
- 2026-09-25T01:45:00-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/console/distill.py § "_classify" =sha256:a5906bdbd52910d271a666e19443cf1c2c393f34a13f8a61d984a210dfe48ab2
  note: the section gained a branch for a traceback below a zero-failure summary (the chained eval sync crashing, A0205); that row is still `error` and still names the exception, prefixed with which half failed, and an extract crash with no summary above it is decided exactly as before — the assertion is unaffected

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
