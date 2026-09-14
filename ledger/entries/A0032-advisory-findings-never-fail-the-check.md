---
id: A0032-advisory-findings-never-fail-the-check
kind: claim
stated: 2026-09-13T20:30:30-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6c180d78581cf4f044b31214a6920196a09d0cdd626f70faeab1caff718143b6
---

## Assertion

Findings from the second, third and fourth audit directions are advisories: they are printed but never fail the check.

## Scope

metric: which findings are fatal versus advisory
cohort: every finding the four-direction audit can produce
condition: the severity classification only

## Grounds

- code: src/thalamus/contract/conformance.py § "severity_of" =sha256:63cad26cf08f9dba0047ab51c3b9ba26e0fc8e8ecea4804f70cbdbc184bab651

## Warrant

severity_of is what assigns ADVISORY versus a failing severity to a finding, so it is the code that decides which findings can only ever be printed.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
