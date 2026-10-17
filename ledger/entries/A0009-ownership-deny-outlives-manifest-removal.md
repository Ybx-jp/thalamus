---
id: A0009-ownership-deny-outlives-manifest-removal
kind: claim
stated: 2026-09-13T20:07:49-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 73481d0acd12564d203d2fcc97e5bdca81228dda95918875f270c6304311b06a
---

## Assertion

The deny half of a path-ownership row survives its owning scope's manifest being removed, while the grant half does not, so deleting a manifest for an owning scope leaves that tree unwritable by everyone rather than freed.

## Scope

metric: whether a deny is conditioned on the owning scope's manifest still existing
cohort: every scope with a PATH_OWNERSHIP row
condition: the ownership check only; a manifest's own write_boundary grant is a different code path this claim does not cover

## Grounds

- code: src/thalamus/contract/ownership.py § "denies" =sha256:f0aeb0e581efdd7ad82b9a459881139deeaead1d76fe39f785fa9f775b1e8008

## Warrant

denies reads only PATH_OWNERSHIP, with no lookup into whether the named owner's manifest still exists, so the deny it returns cannot depend on the manifest being present.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T22:41:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/ownership.py § "denies" =sha256:f0aeb0e581efdd7ad82b9a459881139deeaead1d76fe39f785fa9f775b1e8008
  artifact: sha256:27838606d38088faf18a6af18cc6ed7394e29a9778b9f48572dcc69fcd80f524
  note: propagated from a moved ground
- 2026-10-16T22:43:58-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/contract/ownership.py § "denies" =sha256:27838606d38088faf18a6af18cc6ed7394e29a9778b9f48572dcc69fcd80f524
  note: denies now reads the config root's rows and takes an optional root; it still exempts only a row's owner, so the deny survives the owner's manifest being removed. #343 moves the ownership table out of the package into the config root's ownership.json. The assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
