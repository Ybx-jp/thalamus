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

- 2026-09-14T10:30:34-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/consultation.py § "open_exchange" =sha256:e66086788582ab08550041e1fbca8da0061ead40074451400128dff6f7be461f
  artifact: sha256:95b2e82afa1eb493ba271163ecdefc54741a75faf0665a4e4b76518eb97e7d91
  note: propagated from a moved ground
- 2026-09-14T10:30:53-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/consultation.py § "open_exchange" =sha256:95b2e82afa1eb493ba271163ecdefc54741a75faf0665a4e4b76518eb97e7d91
  note: Read at the current revision. The write-gate change (7de0d95) added gate=refuse_unless_exchange_protocol_holds to the write_exchange call; mint_ticket and write_exchange are still performed in the one call before returning, so the single-act mint-and-write is unaffected.

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
