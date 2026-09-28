---
id: A0206-addition-gate-runs-as-its-own-unrequired-check
kind: claim
stated: 2026-09-25T02:11:00-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: 657cbb165d6ac5a1c66f0a24599cc8a9683d7de959473c7254fb374071a10044
---

## Assertion

In CI the adversarial job runs every fast-tier qe case except expectation-additions-are-never-silent, and that case runs alone in a separate mute-review job, so its red on a pull request that adds a known-red entry shows as a red mute-review and never as a red adversarial.

## Scope

metric: which CI job reports the additions case's verdict
cohort: the qe-fast workflow's jobs on push and pull_request
condition: which checks block a merge is set by the repository ruleset, not by this tree; on 2026-09-25 the ruleset required adversarial and not mute-review. The yaml ground spans only the `jobs:` line until #300 is fixed, so freshness does not see an edit to the jobs themselves

## Grounds

- yaml: .github/workflows/qe-fast.yml § "jobs" =sha256:31d9430f44b068186410d7ecc88458e0cf5e67b439951f03c391cf0ace3f1ffe

## Warrant

The jobs table defines adversarial with run.py --tier fast --exclude expectation-additions-are-never-silent and mute-review with run.py --only expectation-additions-are-never-silent, so the case is selected by exactly one of the two jobs.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-25T02:56:53-07:00 · contested · grade: argued · author: propagation
  evidence: yaml: .github/workflows/qe-fast.yml § "jobs" =sha256:31d9430f44b068186410d7ecc88458e0cf5e67b439951f03c391cf0ace3f1ffe
  artifact: sha256:e50d0538e4ec550b2b7349789304f4fce91dfd6a357baf2745cafb2999286b25
  note: propagated from a moved ground
- 2026-09-25T02:57:00-07:00 · corroborated · grade: argued · author: main
  evidence: yaml: .github/workflows/qe-fast.yml § "jobs" =sha256:e50d0538e4ec550b2b7349789304f4fce91dfd6a357baf2745cafb2999286b25
  note: the yaml section pattern now opens and ends sections only at top-level keys (#300), so the ground spans the key's whole block where it spanned the key line; read against that block, adversarial runs the fast tier with --exclude expectation-additions-are-never-silent and mute-review runs --only that case, so the assertion holds

## References

- CLAUDE.md · standing · cites-as-live
