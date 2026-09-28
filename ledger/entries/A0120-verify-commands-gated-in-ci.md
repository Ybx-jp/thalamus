---
id: A0120-verify-commands-gated-in-ci
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 22bcbe30942f036d24393d784a1e1542346e1daff608e4386e40b1687c1f74d1
---

## Assertion

The verify workflow runs the lint, type-check, test, structure, claims-ledger and contract-check commands as steps of one CI job, so a push or a pull request exercises all of them together.

## Scope

metric: which commands a push or pull request actually runs
cohort: the `verify` job in the CI workflow
condition: not the compose bring-up or graph-logs steps, which support the contract check rather than being verification commands themselves

## Grounds

- yaml: .github/workflows/verify.yml § "jobs" =sha256:31d9430f44b068186410d7ecc88458e0cf5e67b439951f03c391cf0ace3f1ffe

## Warrant

The `jobs` key is the whole of what the workflow executes; every step under it runs on every push and pull request per the trigger the same file declares, so reading the job is reading what CI actually gates rather than trusting a list in prose to stay in sync with it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-25T02:56:53-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: .github/workflows/verify.yml § "jobs" =sha256:31d9430f44b068186410d7ecc88458e0cf5e67b439951f03c391cf0ace3f1ffe
  artifact: sha256:2c2faa0a3d532d784b77ee4f19e32a8d92605fda7a8e58f99b08c22a5235a189
  note: propagated from a moved ground
- 2026-09-25T02:57:00-07:00 · corroborated · grade: measured · author: main
  evidence: yaml: .github/workflows/verify.yml § "jobs" =sha256:2c2faa0a3d532d784b77ee4f19e32a8d92605fda7a8e58f99b08c22a5235a189
  note: the yaml section pattern now opens and ends sections only at top-level keys (#300), so the ground spans the key's whole block where it spanned the key line; read against that block, the single verify job runs ruff, ty, pytest, the three arch gates, claims-ledger check and thalamus contract check as steps, so the assertion holds

## References

- CLAUDE.md · standing · cites-as-live
