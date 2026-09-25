---
id: A0123-arch-rules-gate-requires-a-reason
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6700d57d7e3900a992cb793993bbc2ae0f663736e007d674bb9df0db268075a4
---

## Assertion

A dependency edge the declared architecture layers forbid can only pass the rules gate by way of an accepted-exception entry that carries a stated reason.

## Scope

metric: what makes a forbidden dependency edge pass the rules gate
cohort: the `accepted` exception list in the architecture model
condition: not the rule-violation detection itself, which is a separate mechanism this entry does not claim about

## Grounds

- yaml: arch/model.yaml § "accepted" =sha256:d25cd73c382e24c3c09efd927448278d11bbfdbd2f2c2d5469153db30ce05815

## Warrant

Every entry under `accepted` carries a `reason` field alongside the edge it excuses; an exception list whose members are all required to justify themselves is the mechanism the claim describes, and the file is where that requirement is actually authored rather than merely documented.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-25T02:56:53-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "accepted" =sha256:d25cd73c382e24c3c09efd927448278d11bbfdbd2f2c2d5469153db30ce05815
  artifact: sha256:bfc4dca40e053cb410679f40ec472425d376da9db29292702c586ea1e4b8ac8b
  note: propagated from a moved ground
- 2026-09-25T02:57:00-07:00 · corroborated · grade: measured · author: main
  evidence: yaml: arch/model.yaml § "accepted" =sha256:bfc4dca40e053cb410679f40ec472425d376da9db29292702c586ea1e4b8ac8b
  note: the yaml section pattern now opens and ends sections only at top-level keys (#300), so the ground spans the key's whole block where it spanned the key line; read against that block, each accepted edge carries a reason, so the assertion holds

## References

- CLAUDE.md · standing · cites-as-live
