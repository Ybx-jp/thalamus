---
id: A0122-ty-version-pinned-to-a-patch
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 225b591e870fd596cb3bd3d659eb9e2b787d39995effbb4ef29902a5f40cb349
---

## Assertion

ty is declared at an exact patch version among the project's dev dependencies, rather than a floating version range.

## Scope

metric: how precisely the ty dependency's version is constrained
cohort: the dev extra's declared dependency versions
condition: not the other dependencies in the same table, which may float; the claim is about ty's own constraint only

## Grounds

- toml: pyproject.toml § "project.optional-dependencies" =sha256:bda7b583065a73b47189d216626a611132667059a49fe7aea0a0f5a9da38a9bc

## Warrant

The table lists each dev dependency's version constraint verbatim; ty's entry is an exact-version pin (`==`) where its neighbours use a lower bound, and reading the table is reading the constraint as declared rather than trusting prose to describe it accurately.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: toml: pyproject.toml § "project.optional-dependencies" =sha256:bda7b583065a73b47189d216626a611132667059a49fe7aea0a0f5a9da38a9bc
  artifact: sha256:882b20d486d8460036c447d499c89ffc925bac9a3665882431a11ee4e79081bc
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: toml: pyproject.toml § "project.optional-dependencies" =sha256:882b20d486d8460036c447d499c89ffc925bac9a3665882431a11ee4e79081bc
  note: the claims-ledger floor in this table was raised from 0.0.1 to 0.0.4; the ty pin is untouched and is still spelled to the patch.

## References

- CLAUDE.md · standing · cites-as-live
