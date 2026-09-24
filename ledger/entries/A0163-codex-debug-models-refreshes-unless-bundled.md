---
id: A0163-codex-debug-models-refreshes-unless-bundled
kind: claim
stated: 2026-09-24T00:16:32-07:00
author: main
grade: argued
supersedes: none
verbatim_sha: a418fb4add9eb3064c84acde93877d5f1be5a3b36a4d4c65d78e871399bc1a39
---

## Assertion

codex debug models renders codex's model catalog as JSON after refreshing it, and with --bundled skips the refresh and renders only the catalog shipped inside the binary.

## Scope

metric: what codex debug models prints and whether it refreshes first
cohort: codex-cli 0.154.0
condition: the command's own help text; says nothing about where the refreshed catalog is stored

## Grounds

- source: codex-debug-models-help · §codex debug models

## Warrant

The command's description says it renders the raw model catalog as JSON, and the only option naming a refresh says --bundled skips it and dumps the bundled catalog, so a run without --bundled refreshes before rendering.

## Backing

- source: codex-debug-models-help · §codex debug models
  speaker: OpenAI
  quote: "Render the raw model catalog as JSON"
- source: codex-debug-models-help · §codex debug models
  speaker: OpenAI
  quote: […] "Skip refresh and dump only the bundled catalog shipped with this binary"

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References
