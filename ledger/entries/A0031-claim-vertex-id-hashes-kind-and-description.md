---
id: A0031-claim-vertex-id-hashes-kind-and-description
kind: claim
stated: 2026-09-13T20:29:23-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6aac0f509131a452c55211213da7cad92ba7783f0ba04c51de76dbfa807f6e68
---

## Assertion

A `Claim`'s vertex id contains a hash of its own `(kind, description)`, so the id is itself a claim about the content and re-hashing asks whether the address still agrees.

## Scope

metric: what a Claim vertex's id is derived from
cohort: every Claim node
condition: the id-construction method only

## Grounds

- code: src/thalamus/substrate/schema.py § "Claim" =sha256:96ef724d9e69262f6ba3562d15c9eab8ba19e9327125be0a8f4388067fcbcb93

## Warrant

Claim.content_id computes the id from exactly (kind, normalized description), so the id is provably a function of that content and nothing else.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
