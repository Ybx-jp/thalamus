---
id: A0146-served-stamp-rendered-per-role
kind: claim
stated: 2026-09-14T10:14:02-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 726fcad40ad10d7499f74e633263d8b9ecd92cc3e6b1549c3e6fb1d00b63e329
---

## Assertion

`eval uses` renders the verified stamp split by USES role rather than pooled across roles, because the served-by-trace rule governs the reason role and a rejected alternative is minted by the extraction that rejected it and was never served.

## Scope

metric: whether the verified stamp is reported per role or pooled, and why
cohort: every USES edge the report reads, of any role
condition: how this report renders the stamp; what the stamp itself records when eval sync writes it is a separate claim

## Grounds

- code: src/thalamus/eval/uses.py § "UsesReport" =sha256:3deee41b9668035e58ddac85d063107ef99fd66c62c85a81d98ea0c304471d70

## Warrant

UsesReport holds stamps keyed by role before stamp label, and its render walks that mapping role by role, so the split is a property of the structure the report accumulates into rather than of how one caller prints it.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/uses.py § "UsesReport" =sha256:3deee41b9668035e58ddac85d063107ef99fd66c62c85a81d98ea0c304471d70
  artifact: sha256:f608e78d4fe59a1864ee2494e32cf2db2dfe2064cf23f8c278accbb8c42b8aff
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/uses.py § "UsesReport" =sha256:f608e78d4fe59a1864ee2494e32cf2db2dfe2064cf23f8c278accbb8c42b8aff
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the docstring was rewrapped. The assertion is unaffected.

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/eval/uses.py · standing · cites-as-live
