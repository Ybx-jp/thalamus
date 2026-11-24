---
id: A0259-a-scope-reports-to-main-unless-its-manifest-names-a-declared-superior
kind: claim
stated: 2026-11-23T17:35:57-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 54654e1414281581a2dd77e869460171f27f7a3b6121a73a92d9e56986883542
---

## Assertion

An expert manifest's reports_to names the scope it reports to and defaults to main. Read across the roster, every chain has to end at main: a scope that reports to itself, to a name outside main and the declared scopes, or round a loop is refused with the manifest's path. main is the root, and a chain of any depth is accepted.

## Scope

metric: whether the roster's reports_to values form one tree rooted at main
cohort: every manifest under the config root's experts/, read through reporting_graph
condition: the tree is checked when it is read; loading one manifest alone checks that the field is a string

## Grounds

- code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:50a10758e207f8d803bc1f78b3aeb0bbf8eb5c4baeaedb9aaa21e78261cdcbf4
- code: src/thalamus/contract/reporting.py § "build" =sha256:89736bb2a6a4580eb87909ef751c420e9016a64276ec669b8d11396c5ea8877d
- code: src/thalamus/contract/reporting.py § "reporting_graph" =sha256:463e866aa8c0e9b9337416f02f2daaa78676331aaa04a0b890b1119e0ce3b172

## Warrant

ExpertManifest declares reports_to with MAIN_SCOPE as its default. reporting_graph loads every manifest's reports_to and passes the map to build with each scope's manifest path. build refuses main as a key, a scope equal to its superior, and a superior outside main and the map's keys, then follows each scope's superiors until main and refuses a revisit as a loop; the walk runs until it reaches main or a revisit, whatever its length. Each refusal is a ValueError prefixed with the path from the map.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-11-23T20:53:28-08:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:50a10758e207f8d803bc1f78b3aeb0bbf8eb5c4baeaedb9aaa21e78261cdcbf4
  artifact: sha256:95646f6236406d8384815d944e2a8707a0ca9050065318a227a737548d91f0ed
  note: propagated from a moved ground

- 2026-11-23T20:56:00-08:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:95646f6236406d8384815d944e2a8707a0ca9050065318a227a737548d91f0ed
  note: The class gains a rules field defaulting to the empty string and a private record of the config root it was loaded from. The assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
