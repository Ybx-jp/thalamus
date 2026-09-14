---
id: A0092-qe-is-denied-src
kind: claim
stated: 2026-09-13T20:17:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f9015ab142950e558d9e04f57dc29568f75f117def2f3d9e42e6d6d14367ee51
---

## Assertion

The shipped qe manifest's write_boundary denies every path under src/, with a stated reason that the scope holding the adversarial suite must not repair the implementation it asserts against.

## Scope

metric: what qe's own write_boundary denies and the stated reason why
cohort: the qe expert manifest specifically, not the write_boundary mechanism in general
condition: does not cover whether the deny is actually enforced at runtime, only what the manifest declares

## Grounds

- yaml: config/experts/qe.yaml § "write_boundary" =sha256:897dbf902d249bb0044facc9227b86935583755a14303132bc4476808c5863db

## Warrant

qe.yaml's write_boundary key lists "*/src/*" under deny_globs with a reason stating qe holds the oracle, not the fix, so reading this key shows exactly what is denied and the stated justification in the same place.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- README.md · standing · cites-as-live
