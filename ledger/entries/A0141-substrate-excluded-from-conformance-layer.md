---
id: A0141-substrate-excluded-from-conformance-layer
kind: claim
stated: 2026-09-13T19:47:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 34ddd03a9920e8ca1a2e6a1b25dfd67e20743d6728ce8c58307c4b62ddea2553
---

## Assertion

The declared architecture forbids the substrate layer from depending on the conformance layer that holds the federation contract's checks, while permitting it to depend on the shared vocabulary and archive layers.

## Scope

metric: which layers the substrate layer is permitted to depend on
cohort: the declared dependency rule for the substrate layer
condition: not the measured dependency graph, only what the declared rule permits

## Grounds

- yaml: arch/model.yaml § "rules" =sha256:3de9d845afcc5a08180ea1bdee33f4932a424b2a997ed6e9d1982acab308266a

## Warrant

The rule for `layer: substrate` lists `may_depend_on: [vocabulary, archive]`, which does not include `conformance` — the layer holding `contract/conformance.py` and the rest of the contract's checks — while every higher layer's rule does include it; reading the rule is reading the boundary directly rather than inferring it from where modules happen to sit today.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-25T02:56:53-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "rules" =sha256:3de9d845afcc5a08180ea1bdee33f4932a424b2a997ed6e9d1982acab308266a
  artifact: sha256:32bbd0bb1fe636fb04ab9969ec1abafcc804ae1bdf017406a2da3f1d90535432
  note: propagated from a moved ground
- 2026-09-25T02:57:00-07:00 · corroborated · grade: measured · author: main
  evidence: yaml: arch/model.yaml § "rules" =sha256:32bbd0bb1fe636fb04ab9969ec1abafcc804ae1bdf017406a2da3f1d90535432
  note: the yaml section pattern now opens and ends sections only at top-level keys (#300), so the ground spans the key's whole block where it spanned the key line; read against that block, substrate may depend on vocabulary and archive only, and conformance is not among them, so the assertion holds

## References

- CLAUDE.md · standing · cites-as-live
