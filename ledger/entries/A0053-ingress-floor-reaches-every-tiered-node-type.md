---
id: A0053-ingress-floor-reaches-every-tiered-node-type
kind: claim
stated: 2026-09-13T20:51:57-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: c73eff7a9661a602f471251a511b9e7e5e03b264f9545dea3b07c87e31c40b3a
---

## Assertion

The ingress floor reaches every extracted node type that carries a tier -- claims, threads and artifacts alike -- not only the three claim lists.

## Scope

metric: which extracted node types the floor is applied to
cohort: every type in the extractor's tiered-lists coverage
condition: coverage only

## Grounds

- code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:ba7eb912db22a33630a8205e96cf5cb67fff0bac1ec27ec0f1405aa8db33af9d

## Warrant

apply_ingress_floor's own docstring states its coverage is every enumerated list whose type carries provenance, not the claim lists alone, which is this claim exactly.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-18T16:14:12-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:ba7eb912db22a33630a8205e96cf5cb67fff0bac1ec27ec0f1405aa8db33af9d
  artifact: sha256:d67842e1031c75f28b6fbbb1714c6177e1233d506cc9e88d4b0c0b7e8794c2a0
  note: propagated from a moved ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/harness/extraction.py § "apply_ingress_floor" =sha256:d67842e1031c75f28b6fbbb1714c6177e1233d506cc9e88d4b0c0b7e8794c2a0
  note: the docstring names the tokenizer word_forms, its public name now that the reflex plugin imports it; the floor's logic is unchanged, so the assertion is unaffected

## References

- docs/concepts.md · standing · cites-as-live
