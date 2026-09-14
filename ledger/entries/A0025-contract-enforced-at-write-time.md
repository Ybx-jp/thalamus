---
id: A0025-contract-enforced-at-write-time
kind: claim
stated: 2026-09-13T20:23:41-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: d015a3df1ba27609042fb2c190828309201639d0b06da8b7780ebf0158af61b2
---

## Assertion

The federation contract is enforced at write time, not filtered at read time: orphans and violations are rejected by the gate every session write goes through.

## Scope

metric: whether a violation is rejected at write or only hidden later at read
cohort: every session write
condition: the gate function only

## Grounds

- code: src/thalamus/contract/conformance.py § "write_session_checked" =sha256:c5541e0050b4261aff9aef3cfd344951997725070f876dafa737562272c26351

## Warrant

write_session_checked is the one gate every session write passes through, and it is what rejects an orphan or violation before it lands, which is the write-time enforcement the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
