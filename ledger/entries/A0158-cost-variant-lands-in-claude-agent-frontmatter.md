---
id: A0158-cost-variant-lands-in-claude-agent-frontmatter
kind: claim
stated: 2026-09-23T22:34:08-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 398764b6238aa9a9395a124bd335d6d067ca90a2fe9836a764380172259ca7b5
---

## Assertion

A manifest's cost field selects one variant of the cost dimension, defaulting to inherit, and the Claude Code agent renderer writes that variant's model class and effort into the generated agent file's model and effort frontmatter.

## Scope

metric: what the cost field changes in a generated Claude Code agent file
cohort: every scope rendered by render_agent
condition: Claude Code only; the Cursor and Codex renderers do not read the field

## Grounds

- code: src/thalamus/contract/capabilities.py § "COST" =sha256:62d1693c076884bc47ece1278049b74af705fa7701d836d2eae665d93b4e917c
- code: src/thalamus/harness/pin.py § "_cost_frontmatter" =sha256:25662a37c668e85039ba722765aeb1bc56aa672e6528081161db170a7d510ab8

## Warrant

COST declares the variants, their settings and the inherit default the manifest field falls back to; _cost_frontmatter is the only reader of the selected variant and emits the model and effort lines render_agent places in the frontmatter.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-23T23:31:40-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/capabilities.py § "COST" =sha256:62d1693c076884bc47ece1278049b74af705fa7701d836d2eae665d93b4e917c
  artifact: sha256:35c5870ea21b9cdf3d46fd54aa9f283cd43b6bd6f71f216e56d2d34f052981ff
  note: propagated from a moved ground

- 2026-09-23T23:31:40-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/pin.py § "_cost_frontmatter" =sha256:25662a37c668e85039ba722765aeb1bc56aa672e6528081161db170a7d510ab8
  artifact: sha256:2fcb127371fe0651d24517b9e34a06a5d06a9b1848f83dd73b7eb2d31cba44ab
  note: propagated from a moved ground

- 2026-09-23T23:50:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/pin.py § "_cost_frontmatter" =sha256:2fcb127371fe0651d24517b9e34a06a5d06a9b1848f83dd73b7eb2d31cba44ab
  note: the cost dimension's variants became operator-defined named presets (inherit stays built in and the default); _cost_frontmatter reads the resolved preset's model_class and effort into the same frontmatter lines, so the assertion holds with "variant" read as "preset"

## References

- docs/concepts.md · standing · cites-as-live
