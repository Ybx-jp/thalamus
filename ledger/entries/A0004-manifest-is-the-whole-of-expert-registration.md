---
id: A0004-manifest-is-the-whole-of-expert-registration
kind: claim
stated: 2026-09-13T20:02:14-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 4d46355fa423e9f1da6f5d1dc714e734d6dcf75c5a0bb8760599522a45f1aedd
---

## Assertion

An expert is declared by writing one YAML manifest in `config/experts/`, and nothing else registers or wires it up.

## Scope

metric: what else, besides the manifest file, is required to make a scope exist
cohort: every expert manifest under the configured experts directory
condition: only how a scope becomes visible to the harness; a scope's write and capability boundaries are separate declarations inside that same file

## Grounds

- code: src/thalamus/contract/manifest.py § "available_scopes" =sha256:83ef1d996e23a6d2e862fbb2e7e2a2b7d915b3750c5d964f7704724951ba7b1c

## Warrant

available_scopes discovers scopes by scanning the manifests directory alone, with no separate registry consulted, so adding a file is the entire mechanism the assertion describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
