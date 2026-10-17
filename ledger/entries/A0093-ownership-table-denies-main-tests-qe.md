---
id: A0093-ownership-table-denies-main-tests-qe
kind: claim
stated: 2026-09-13T20:18:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 9cda72e7d38a14b9e0e4fa00b19f1dad43f53eaa34b6b214c3c6d27a0666fa17
---

## Assertion

The path-ownership table denies every scope but qe from writing under tests/qe/, with a stated reason that this is the mirror of qe's own denial of src/, so each scope is barred from adjusting what the other asserts.

## Scope

metric: what the ownership table denies and to whom
cohort: every scope other than qe, against the tests/qe/ tree specifically
condition: does not cover how the denial is enforced at the tool level, only what the table declares

## Grounds

- code: src/thalamus/contract/ownership.py § "PATH_OWNERSHIP" =sha256:f33adb9ac694919a583e2e6961574c7deb18b249407e5a660f77c470dfd9a4cf

## Warrant

PATH_OWNERSHIP's one row denies */tests/qe/* to every scope but qe, with a reason naming the mirror relationship to qe's own src/ deny explicitly, so the section states both the denial and its rationale directly.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T22:41:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/ownership.py § "PATH_OWNERSHIP" =sha256:f33adb9ac694919a583e2e6961574c7deb18b249407e5a660f77c470dfd9a4cf
  artifact: absent
  note: propagated from a withdrawn ground
- 2026-10-16T22:43:58-07:00 · corroborated · grade: measured · author: architect
  evidence: json: config/ownership.json § "qe-oracle" =sha256:eeb9dfe14470f2ce8fe5a450a48c78a7a060f9d8248eb2b981738fe842656941
  note: The tests/qe/ row, its owner and its mirror-of-src reason moved verbatim from contract/ownership.PATH_OWNERSHIP to this row. #343 moves the ownership table out of the package into the config root's ownership.json. The assertion is unaffected.

## References

- README.md · standing · cites-as-live
