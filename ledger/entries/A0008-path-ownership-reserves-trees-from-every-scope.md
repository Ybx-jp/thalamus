---
id: A0008-path-ownership-reserves-trees-from-every-scope
kind: claim
stated: 2026-09-13T20:06:42-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 799b3f08ed0a2c4d18445175676d72667850332c28c2ceedb508c7f0b5e375f5
---

## Assertion

`PATH_OWNERSHIP` reserves a tree for one scope and denies every other scope from writing it, `main` included; `tests/qe/` is currently its one row.

## Scope

metric: which paths are reserved, for which scope, and how many such rows currently exist
cohort: the whole path-ownership table
condition: the declared rows only; how a denial is actually enforced against a write attempt is a separate claim

## Grounds

- code: src/thalamus/contract/ownership.py § "PATH_OWNERSHIP" =sha256:f33adb9ac694919a583e2e6961574c7deb18b249407e5a660f77c470dfd9a4cf

## Warrant

PATH_OWNERSHIP is the literal tuple of (glob, owner, reason) rows, so reading it directly settles both which tree is reserved for which scope and how many rows currently exist.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
