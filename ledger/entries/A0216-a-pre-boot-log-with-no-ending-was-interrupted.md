---
id: A0216-a-pre-boot-log-with-no-ending-was-interrupted
kind: claim
stated: 2026-10-06T17:59:21-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 858535fdb50667f88f34c0f6de096bdaf1b20cc4b27a11edc7f6e75ba7f5614f
---

## Assertion

A session-end log with no ending whose last write predates the machine's current boot is reported by the console as a distillation the shutdown interrupted, an error, rather than as active, stalled or abandoned.

## Scope

metric: which distillation state the console derives for a session-end log with no summary, no failure mark, no crash and no clean no-op ending
cohort: every `~/.thalamus/logs/session-end-<session id>.log` the pin ledger vouches for
condition: the log's mtime is earlier than the kernel's boot time as `/proc/stat` `btime` reports it; where that cannot be read the boot time is 0 and the clock decides as before

## Grounds

- code: src/thalamus/console/distill.py § "_classify" =sha256:d51bab4e9aae7e3b4c5cca6027a882673fa28cbf6155d75f7b3c651952210a5a

## Warrant

`_classify` reaches `_by_clock` only for a log with no summary line, and immediately before that call compares the log's mtime against the boot time (`BOOTED_AT`, or the value a caller passes); a mtime before it returns `error` with a detail saying the shutdown interrupted extract. No process survives a reboot, so a job whose log stopped before the boot cannot still be running.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T22:07:41-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/console/distill.py § "_classify" =sha256:d51bab4e9aae7e3b4c5cca6027a882673fa28cbf6155d75f7b3c651952210a5a
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-18T22:10:00-07:00 · corroborated · grade: argued · author: architect
  evidence: code: packages/thalamus-console/src/thalamus_console/distill.py § "_classify" =sha256:d51bab4e9aae7e3b4c5cca6027a882673fa28cbf6155d75f7b3c651952210a5a
  note: src/thalamus/console/distill.py moved into the thalamus-console plugin package as distill.py with _classify unchanged, so the assertion is unaffected

## References

- packages/thalamus-console/src/thalamus_console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
