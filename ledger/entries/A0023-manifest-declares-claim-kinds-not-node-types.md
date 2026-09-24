---
id: A0023-manifest-declares-claim-kinds-not-node-types
kind: claim
stated: 2026-09-13T20:21:27-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 8330ae9f578a2d21e8a874eaef5f71fcd1ec3e680f85b1476e51c8a616d90994
---

## Assertion

An expert manifest declares the claim kinds its scope may write; it does not declare new node types.

## Scope

metric: what a manifest's declaration actually adds to the ontology
cohort: every expert manifest
condition: the manifest's own fields only

## Grounds

- code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:d03dc8e58b57c24f4a93820cb23808f177551a7e4dc6a0d35e8cd150b07c34e0

## Warrant

ExpertManifest's fields include claim_kinds and nothing that declares a node label, so the schema itself is the boundary between what a manifest can and cannot add.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-23T22:35:09-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:d03dc8e58b57c24f4a93820cb23808f177551a7e4dc6a0d35e8cd150b07c34e0
  artifact: sha256:e98fbd992a5691484fe1919985f26636e29631899880fc2e2e245464dfb709da
  note: propagated from a moved ground

- 2026-09-23T22:40:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:e98fbd992a5691484fe1919985f26636e29631899880fc2e2e245464dfb709da
  note: ExpertManifest gained a `cost` field selecting a variant of a declared dimension, with its validator and accessor; it declares no node type, so the assertion is unaffected
- 2026-09-23T23:31:40-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:e98fbd992a5691484fe1919985f26636e29631899880fc2e2e245464dfb709da
  artifact: sha256:ab6bc12a7bf2285b36feb97fabff64355c98812fdb9b984b87f94b7aaec23930
  note: propagated from a moved ground

- 2026-09-23T23:50:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/contract/manifest.py § "ExpertManifest" =sha256:ab6bc12a7bf2285b36feb97fabff64355c98812fdb9b984b87f94b7aaec23930
  note: the cost field now names an operator-defined preset and resolves it through a private attribute; still no node type declared, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
