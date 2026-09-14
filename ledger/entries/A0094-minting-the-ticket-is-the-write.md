---
id: A0094-minting-the-ticket-is-the-write
kind: claim
stated: 2026-09-13T20:19:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 1b31896795fc8d0f9ee9a3a1e78b491b69dbc22c6a9c1ca3ac6b2bd81d376bb7
---

## Assertion

Minting a consultation ticket and writing its Exchange vertex happen in the same function call, so an unrecorded consultation cannot occur.

## Scope

metric: whether the ticket and its graph record are produced by one act or two
cohort: every consultation opened through open_exchange, both protocol tiers
condition: does not cover citation validation on the answer that later closes the exchange

## Grounds

- code: src/thalamus/harness/consultation.py § "open_exchange" =sha256:e66086788582ab08550041e1fbca8da0061ead40074451400128dff6f7be461f

## Warrant

open_exchange's docstring states the mint is the write for both tiers and that an unrecorded consultation is impossible by construction, and its body calls mint_ticket and write_exchange in the same call before returning, so the section both claims and performs the single-act mint-and-write.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
