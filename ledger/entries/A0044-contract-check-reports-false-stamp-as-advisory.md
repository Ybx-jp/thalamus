---
id: A0044-contract-check-reports-false-stamp-as-advisory
kind: claim
stated: 2026-09-13T20:42:54-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: a7b4c5d56faeafa10d9b232711083ef398c2c61d1322bf2fa7d114f726d5e6db
---

## Assertion

Nothing in the write path gates a `USES` edge on its eval-verified stamp; `contract check` instead reports a cross-scope `USES` edge stamped false as an advisory.

## Scope

metric: whether a false-verified USES edge is rejected at write time or only flagged later
cohort: every cross-scope USES edge stamped false
condition: this reporting behavior only

## Grounds

- code: src/thalamus/contract/conformance.py § "audit_attribution" =sha256:c2d15ef4a05d6b4e3b54d4877993aed35eede816bce81a44d424a56664d1614b

## Warrant

audit_attribution is the same check that classifies a cross-scope USES edge, and its advisory-versus-fail classification is what keeps a false stamp from ever blocking a write.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
