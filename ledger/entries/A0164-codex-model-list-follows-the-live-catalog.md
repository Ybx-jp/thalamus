---
id: A0164-codex-model-list-follows-the-live-catalog
kind: claim
stated: 2026-09-24T00:16:33-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: bc258c4812c45409a7cbc8b1eb15a765bd3452122b904e4c7355ab47b5632a09
---

## Assertion

Thalamus reads codex's model catalog from models_cache.json under CODEX_HOME when the client_version recorded there matches the installed codex, and otherwise runs codex debug models, which refreshes that file; so the codex models the console offers and the cost presets render follow a codex update and a catalog change between updates.

## Scope

metric: which codex catalog codex_models.catalog returns
cohort: a box with codex on PATH
condition: measured on codex-cli 0.154.0 on 2026-09-24, where codex debug models rewrote the file's fetched_at and printed the models the file then held, and codex debug models --bundled left the file untouched and printed a different catalog

## Grounds

- code: src/thalamus/harness/codex_models.py § "_read" =sha256:fced627f93feb7b14f8b7194a95440830d68a5a44b64fe77c4f44ec830ffe719
- code: src/thalamus/harness/codex_models.py § "catalog" =sha256:0a5fb8ca093177de7c1fd100e51f0fa5a92b7dd026aebecc52e49b7743959b3a
- entry: A0163-codex-debug-models-refreshes-unless-bundled · cites-as-live

## Warrant

_read returns the parsed models of the cache file when its client_version equals the version codex --version reports, and otherwise the parsed output of codex debug models, which refreshes the catalog before printing it (A0163); catalog memoises on the codex binary's and the cache file's modification times, so a replaced binary or a rewritten cache is read again on the next call.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- docs/console.md · standing · cites-as-live
- src/thalamus/harness/codex_models.py · standing · cites-as-live
