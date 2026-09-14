---
id: A0026-contract-check-audits-the-live-graph
kind: claim
stated: 2026-09-13T20:24:48-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 7905dcbe5fa17e15e90dc3716b3ccb95434dc86d2336ebd09733ccc4ecab1a08
---

## Assertion

`thalamus contract check` audits the live graph against the federation contract.

## Scope

metric: what the contract-check command audits
cohort: the live graph at the time the command runs
condition: the audit function only

## Grounds

- code: src/thalamus/contract/conformance.py § "check_graph" =sha256:1adc4f7461a937a06018d22257d3a7f4c524638ffc03a3eb2988f9653ddae27a

## Warrant

check_graph is the function thalamus contract check runs, so its behavior is what the command's audit consists of.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
