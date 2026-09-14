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

## References

- CLAUDE.md · standing · cites-as-live
