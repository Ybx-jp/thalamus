---
id: A0227-this-repo-reserves-tests-qe-for-qe
kind: claim
stated: 2026-10-16T22:43:58-07:00
author: architect
grade: measured
supersedes: A0008-path-ownership-reserves-trees-from-every-scope
verbatim_change: the table moved out of the package into the config root's `ownership.json`, so the claim is about this repository's table, and a config root without the file reserves nothing
verbatim_sha: 15cbedafcdf7592ed1fbbec4ea92b54fa0e79715248af7cc53d2616c05230ca5
---

## Assertion

This repository's ownership table, `config/ownership.json`, reserves `tests/qe/` for `qe` and denies every other scope from writing it, `main` included; it is the table's one row, and a config root without the file reserves nothing.

## Scope

metric: which paths are reserved, for which scope, how many rows this repository declares, and what a root without the table reserves
cohort: this repository's ownership table and the reader that resolves it from a config root
condition: the declared rows and their resolution only; how a denial is enforced against a write attempt is a separate claim

## Grounds

- json: config/ownership.json § "qe-oracle" =sha256:eeb9dfe14470f2ce8fe5a450a48c78a7a060f9d8248eb2b981738fe842656941
- code: src/thalamus/contract/ownership.py § "rows" =sha256:d57ccdbecac74160c397264ccc61e8d8f1de14ef9bbce06cf2fb6a303ec25054

## Warrant

The `qe-oracle` row is the table's only key and names `*/tests/qe/*` with owner `qe`; rows returns the config root's rows and returns none when the file is absent, and denies exempts only the row's owner, so every other scope, `main` among them, is denied.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
