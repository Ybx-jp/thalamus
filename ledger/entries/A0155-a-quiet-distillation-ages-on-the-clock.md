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

- 2026-09-29T12:17:50-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/distill.py § "DistillWatch" =sha256:0718ccdc74095a80b51e4d73eb818fe3434cf914a4bab036edd2765b31042de4
  artifact: sha256:6bb2e54734399d7d00a46f6aea8516a04b03a20b89fc6fbef66d3f6b03baed46
  note: propagated from a moved ground

- 2026-09-29T12:20:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/console/distill.py § "DistillWatch" =sha256:6bb2e54734399d7d00a46f6aea8516a04b03a20b89fc6fbef66d3f6b03baed46
  note: DistillWatch gained _fs_now, which stamps the clean-slate seed from the filesystem clock; the clock-driven re-classification through _by_clock is unchanged

- 2026-09-29T12:40:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/console/distill.py § "DistillWatch" =sha256:0993d4a386ffc58896791848d9df762ab41a368199cce624ed975ac683028fa7
  note: the seed probe now creates the logs directory and the seed comparison is strict; the clock-driven re-classification through _by_clock is unchanged
- 2026-09-29T22:12:55-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/console/distill.py § "DistillWatch" =sha256:0993d4a386ffc58896791848d9df762ab41a368199cce624ed975ac683028fa7
  artifact: sha256:5df063072c3dbcc724a87b4e6bdd8f89fb3b6ec6ae21b85dd2ad9bb119601958
  note: propagated from a moved ground

- 2026-09-29T22:14:00-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/console/distill.py § "DistillWatch" =sha256:5df063072c3dbcc724a87b4e6bdd8f89fb3b6ec6ae21b85dd2ad9bb119601958
  note: the ledger join is keyed by the full session id and by its eight-character prefix for legacy log names, and kill rows are matched against both name shapes; the clock-driven re-classification through _by_clock is unchanged -- the assertion is unaffected

## References

- src/thalamus/console/distill.py · standing · cites-as-live
- docs/console.md · standing · cites-as-live
