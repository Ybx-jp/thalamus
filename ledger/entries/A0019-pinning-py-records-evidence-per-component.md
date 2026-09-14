---
id: A0019-pinning-py-records-evidence-per-component
kind: claim
stated: 2026-09-13T20:17:59-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: c6a8bdc250f5fc1867d90118c4360a85793a1dcb16bd050b7a57523a7b04b36c
---

## Assertion

`contract/pinning.py` records, per harness and per component, the evidence for whether a pin property actually binds there.

## Scope

metric: whether the pinning table's claims are checked against evidence or merely declared
cohort: every row in PIN_ROWS
condition: the check function only

## Grounds

- code: src/thalamus/contract/pinning.py § "check_pinning" =sha256:b3a89ed3d90ebacdd93eb67b4a50b1fcbe30957dece980aa1aa0868fc0dad3f3

## Warrant

check_pinning is what walks PIN_ROWS against its evidence, so its presence is what keeps pinned from silently meaning more on one harness than another.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
