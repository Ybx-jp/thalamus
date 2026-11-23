---
id: A0255-an-autonomous-run-consults-at-tier-two
kind: claim
stated: 2026-11-23T11:02:17-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: d10d9e5d6f3cfc8a0bb093b91648749acce5f6e58febce363163bc73cc196198
---

## Assertion

An exchange record carries the session type of the session that opened it and that type's tier, so a consultation an autonomous run opens is written at tier 2 and an attended session's at tier 1. A rendered exchange names an autonomous asker as an autonomous run at tier 2 in its full form, its index line and its brief header.

## Scope

metric: the tier and session_type an opened exchange is written with, and how a rendered exchange names its asker
cohort: exchanges opened through consultation.open_exchange, by the full ticket and the quick tier
condition: the type is the one passed by the caller or, when none is, the one the process resolves; an exchange written before the field existed carries none and renders as before

## Grounds

- code: src/thalamus/harness/consultation.py § "open_exchange" =sha256:53ad9c98c554939334b32e375ea986879cabdcc1aca4c401d3c37d13a2b9cf55
- code: src/thalamus/substrate/reader.py § "ExchangeResult" =sha256:72fe4a7dfd242998497d7980199f73f7ef788648119eab1f2c88bd94a311f7fd

## Warrant

open_exchange takes the given session type or pin.process_session_type and builds the provenance at session_type_tier of it, writing tier and session_type onto the exchange's properties. ExchangeResult carries the session_type read back from the vertex, and its format, format_index and format_header all name the asker through _asked_by, which appends the autonomous-run tier-2 marker for an autonomous exchange.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/consultation.py · standing · cites-as-live
- src/thalamus/substrate/reader.py · standing · cites-as-live
