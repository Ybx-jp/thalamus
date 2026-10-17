---
id: A0226-init-seeds-an-empty-config-root-with-the-examples
kind: claim
stated: 2026-10-16T22:40:00-07:00
author: architect
grade: measured
supersedes: none
verbatim_sha: 2fee0ffd4096e2a863cad5319bf226b5520825a4b9ffc37f57b7c8759c4ed3bf
---

## Assertion

An installed wheel ships two example experts, `literature` and `qe`, with `budget` and `cost` presets files, and `thalamus init` copies them into a config root that holds no manifests, never replacing a file that is already there.

## Scope

metric: which files init copies into the config root, and when it copies none
cohort: every `thalamus init` run, against whatever config root it resolves
condition: the seeding only; a root holding any manifest receives nothing

## Grounds

- code: src/thalamus/harness/install.py § "seed_config" =sha256:9dc915f47b1a6b071d1105af9518d030db4760ff43f51c4ee8004b701cce8f4b
- code: src/thalamus/harness/install.py § "EXAMPLES_DIR" =sha256:aaac52f9ac4a2248173e5ba419c587717becafed0a443706f42f97d25c815d6f

## Warrant

seed_config returns before copying anything when the config root's `experts/` holds a manifest, and otherwise copies each `*.yaml` under EXAMPLES_DIR to the same relative path, skipping any destination that exists; EXAMPLES_DIR is the package's own `examples/`, which holds `experts/literature.yaml`, `experts/qe.yaml`, `presets/budget.yaml` and `presets/cost.yaml` and so ships in the wheel.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
