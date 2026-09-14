---
id: A0042-unresolvable-handle-is-dropped-not-written
kind: claim
stated: 2026-09-13T20:40:40-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 8e060730ff9a88b64802be665c63c54e9040cedf8f288eba8402cd9ed95fef52
---

## Assertion

A handle naming nothing the session was actually served is dropped rather than written as a reference.

## Scope

metric: what happens to a reference handle that does not resolve against the served list
cohort: every reference handle an extraction names
condition: the resolution function only

## Grounds

- code: src/thalamus/harness/extraction.py § "resolve_references" =sha256:d5a9ed2eadd39ce6c0dd494b984262a6d73afe3e55ec774e070996de94f8fbf9

## Warrant

resolve_references is what maps a handle back to something actually served and discards it when that fails, which is the drop-not-write behavior stated.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
