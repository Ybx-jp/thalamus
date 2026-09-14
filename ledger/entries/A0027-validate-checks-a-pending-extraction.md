---
id: A0027-validate-checks-a-pending-extraction
kind: claim
stated: 2026-09-13T20:25:55-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 2764328511226c5d7b854a7d972892a7b36d4dace85f9597cb0d0670de008c6b
---

## Assertion

`thalamus validate` checks a pending extraction against the contract before it lands in the graph.

## Scope

metric: what thalamus validate checks, and whether that happens before or after landing
cohort: a session extraction not yet written
condition: the check function only

## Grounds

- code: src/thalamus/contract/conformance.py § "check_session" =sha256:9b137cd2c05b9733ad3ffd24d35f6332ac26ba94018123cfd1972bc9f8b8319f

## Warrant

check_session is the function that validates a SessionGraph before it is written, which is exactly the pre-landing check the assertion describes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
