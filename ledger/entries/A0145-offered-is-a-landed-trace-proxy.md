---
id: A0145-offered-is-a-landed-trace-proxy
kind: claim
stated: 2026-09-14T10:14:02-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 60220dbcc8dc706fb4d7bc4ea72a143f82ec9f8a613c4083a8f13421f4591871
---

## Assertion

`eval uses` counts a session as offered when it has a landed Trace returning at least one Claim or Chunk, which reconstructs the offer from traces rather than reading the digest's own offer list, and it counts that as a boolean rather than as a population.

## Scope

metric: what puts a session into the citation-coverage denominator
cohort: every Session vertex the report reads
condition: the denominator's definition only, not the coverage rate computed from it and not the cap the digest applies to its offer list

## Grounds

- code: src/thalamus/eval/uses.py § "_session_rows" =sha256:4674ae6e73cbfe8a8debeebec90e85b9a1bb55ab48c6eace4fbb5d0f85fe4258

## Warrant

_session_rows is where offered is defined: the traversal walks QUERIES then RETURNS to a Claim or Chunk, which is a landed trace and not the digest's list, and its limit(1) before count is what makes the value a boolean rather than a count of returned nodes.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/uses.py § "_session_rows" =sha256:4674ae6e73cbfe8a8debeebec90e85b9a1bb55ab48c6eace4fbb5d0f85fe4258
  artifact: sha256:37f90645991e0e69a45c0b7a6eddf4de858bffb91692574ce9f1d43dbd8f73d7
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/uses.py § "_session_rows" =sha256:37f90645991e0e69a45c0b7a6eddf4de858bffb91692574ce9f1d43dbd8f73d7
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the docstring was rewrapped. The assertion is unaffected.

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/eval/uses.py · standing · cites-as-live
