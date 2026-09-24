---
id: A0159-operator-defines-named-cost-presets
kind: claim
stated: 2026-09-23T23:31:21-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: aa79a9f18ccf896a6e957907bd4418e341ee11aad7de6ca635f1d220b4af7801
---

## Assertion

A manifest's cost field names a preset the operator defines in presets/cost.yaml under the config root, with inherit built in and setting nothing, and a manifest naming an undefined preset fails to load.

## Scope

metric: where a cost preset is defined and what happens to a manifest that names one
cohort: every manifest loaded through load_manifest
condition: the cost dimension only

## Grounds

- code: src/thalamus/contract/capabilities.py § "Dimension" =sha256:ded60f797071bfb98eab98aa7e41d275cd02cc005c0c16081e28dfcf5d9259ee
- code: src/thalamus/contract/manifest.py § "load_manifest" =sha256:31535bb70ed2d7be5fba0aa35300825fd5905fadaddfbb5b2ebe1cecd24c3fbe
- code: src/thalamus/contract/manifest.py § "presets_file" =sha256:9d42af3900610af66cbdb33f028a43b7eff14191678c1358090985762bc4cb36

## Warrant

Dimension.presets adds the built-in inherit and refuses a declaration that redefines it, and Dimension.resolve raises on an undefined name; presets_file places the file at presets/<dimension>.yaml under the config root, and load_manifest resolves the selection against it and re-raises with the manifest's path.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
