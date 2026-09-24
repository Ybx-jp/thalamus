---
id: A0162-cost-preset-lands-in-codex-profile
kind: claim
stated: 2026-09-23T23:48:28-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: f6e6de2732f6639e2d45c84f67f9821c0af291a15bc2e78729d8dc4710ea5000
---

## Assertion

The Codex profile renderer writes a scope's cost preset into its generated profile as top-level keys: model, the codex slug for the preset's model class, when the preset sets a model class, and model_reasoning_effort when it sets an effort.

## Scope

metric: what the cost preset changes in a generated Codex profile
cohort: every scope rendered by render_codex_profile
condition: codex-cli 0.154.0, where a live codex exec on such a profile (gpt-5.6-luna, low) reported that model and reasoning effort under --strict-config on 2026-09-23

## Grounds

- code: src/thalamus/harness/pin.py § "_codex_cost_keys" =sha256:15ae491e853349edc3c3a0f3969379142d65833e9478548aedea3f95f98b6bd0
- code: src/thalamus/harness/pin.py § "CODEX_MODELS" =sha256:d6e8f9f0d33cd1e6e437c8cbcc2fc5f77d6d75bd4ab280fa3f57093221793036

## Warrant

_codex_cost_keys emits a model line only when the preset sets model_class, looked up in CODEX_MODELS, and a model_reasoning_effort line only when it sets effort; render_codex_profile places its output before the mcp_servers tables, where TOML reads the lines as top-level keys.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T00:17:03-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "_codex_cost_keys" =sha256:15ae491e853349edc3c3a0f3969379142d65833e9478548aedea3f95f98b6bd0
  artifact: sha256:d67ac3f84b5a6e662081f44a21360cad7801970b8f7b925d5dc3885bfb0d25fb
  note: propagated from a moved ground

- 2026-09-24T00:40:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/pin.py § "_codex_cost_keys" =sha256:d67ac3f84b5a6e662081f44a21360cad7801970b8f7b925d5dc3885bfb0d25fb
  note: the model key now takes the CODEX_MODELS slug through codex_models.current, which follows the live catalog's upgrade chain (A0164); it is still written only when the preset sets a model class, as a top-level key, and model_reasoning_effort is unchanged

## References

- docs/concepts.md · standing · cites-as-live
