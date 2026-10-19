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
- 2026-10-18T13:51:40-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "rules" =sha256:32bbd0bb1fe636fb04ab9969ec1abafcc804ae1bdf017406a2da3f1d90535432
  artifact: sha256:978235708cf5d50ac0d97d61c82c006dcfaeafa9106b0228dd7694ffcf298447
  note: propagated from a moved ground
- 2026-10-18T13:55:00-07:00 · corroborated · grade: measured · author: architect
  evidence: yaml: arch/model.yaml § "rules" =sha256:978235708cf5d50ac0d97d61c82c006dcfaeafa9106b0228dd7694ffcf298447
  note: the rules gained the extension and plugin-ingest layers and entry may now depend on extension; the substrate rule is unchanged at [vocabulary, archive], so the assertion is unaffected
- 2026-10-18T16:14:12-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "rules" =sha256:978235708cf5d50ac0d97d61c82c006dcfaeafa9106b0228dd7694ffcf298447
  artifact: sha256:784ea16599dba2146c1eba968a3d1d6b759b836d6052e63d91b8066c96bb4129
  note: propagated from a moved ground
- 2026-10-18T16:25:00-07:00 · corroborated · grade: measured · author: architect
  evidence: yaml: arch/model.yaml § "rules" =sha256:784ea16599dba2146c1eba968a3d1d6b759b836d6052e63d91b8066c96bb4129
  note: the rules gained the plugin-reflex layer and harness may now depend on extension; the substrate rule is unchanged at [vocabulary, archive], so the assertion is unaffected
- 2026-10-18T21:22:05-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "rules" =sha256:784ea16599dba2146c1eba968a3d1d6b759b836d6052e63d91b8066c96bb4129
  artifact: sha256:e3cf0832f71b3d9966f3541ed326a1494735a8115cf5fa489d9c2bfb04c0e502
  note: propagated from a moved ground
- 2026-10-18T21:25:00-07:00 · corroborated · grade: measured · author: architect
  evidence: yaml: arch/model.yaml § "rules" =sha256:e3cf0832f71b3d9966f3541ed326a1494735a8115cf5fa489d9c2bfb04c0e502
  note: the rules gained the plugin-measure layer and the plugin-reflex comment now names only the trace tap; the substrate rule is unchanged at [vocabulary, archive], so the assertion is unaffected
- 2026-10-18T22:07:40-07:00 · contested · grade: measured · author: propagation
  evidence: yaml: arch/model.yaml § "rules" =sha256:e3cf0832f71b3d9966f3541ed326a1494735a8115cf5fa489d9c2bfb04c0e502
  artifact: sha256:3f56ab3e75be92ff3235749ac9b8a263bb5242c1bee55f827d3f6354d19cfb7a
  note: propagated from a moved ground
- 2026-10-18T22:10:00-07:00 · corroborated · grade: measured · author: architect
  evidence: yaml: arch/model.yaml § "rules" =sha256:3f56ab3e75be92ff3235749ac9b8a263bb5242c1bee55f827d3f6354d19cfb7a
  note: the rules gained the plugin-console layer; the substrate rule is unchanged at [vocabulary, archive], so the assertion is unaffected

## References

- CLAUDE.md · standing · cites-as-live
