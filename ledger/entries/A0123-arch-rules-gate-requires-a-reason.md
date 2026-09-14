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

## References

- CLAUDE.md · standing · cites-as-live
