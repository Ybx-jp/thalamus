---
id: A0155-a-quiet-distillation-ages-on-the-clock
kind: claim
stated: 2026-09-21T21:22:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 9aa69a3d40384ce5040a73a4e05b4e4260e57aac977fe32fb8e299af9fffb677
---

## Assertion

A distillation whose log has gone quiet is re-classified on every scan from how long ago that log was last written, so it passes from `distilling` through `stalled` to `abandoned` while one console process stays up.

## Scope

metric: whether the state a quiet log is served under keeps up with the clock across scans in one long-lived process
cohort: every `session-end-*.log` the watcher has already read and cached
condition: the thresholds themselves, and what the roster draws for each state, are separate claims

## Grounds

- code: src/thalamus/console/distill.py § "_by_clock" =sha256:fc5617c26fd5ef0561065172d9039bb366038adbaced508924764e3bda0e9784
- code: src/thalamus/console/distill.py § "DistillWatch" =sha256:0718ccdc74095a80b51e4d73eb818fe3434cf914a4bab036edd2765b31042de4

## Warrant

The three verdicts for a log with no summary line are a function of the clock and of nothing in the file, and `_by_clock` is the single place that derives them. A log that has gone quiet is by definition one nothing writes to, so its `(mtime, size)` cache entry stays valid for as long as the process lives; `DistillWatch.rows` therefore re-derives the verdict through `_by_clock` for every cached state in `CLOCK_STATES` instead of trusting the cached word, and rewrites the cache entry when the word changes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
