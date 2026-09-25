---
id: A0085-pulse-prices-retrieval-cost
kind: claim
stated: 2026-09-13T20:10:00-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 276ee6bc5cf6b741b7a521c06a330e7345a7105b6d6403b4a7ab6baef0f11392
---

## Assertion

`thalamus pulse` is backed by a function that assembles a cost report over a project's recorded retrieval activity.

## Scope

metric: whether a cost report is computed from recorded retrieval activity rather than estimated some other way
cohort: the pulse command's reporting for a single project directory
condition: does not cover the live-dashboard rendering itself or its refresh behavior, only that a cost report is assembled from recorded activity

## Grounds

- code: src/thalamus/eval/cost.py § "cost_report" =sha256:e5ee389bd7cad4ebb86e4ec6f3e4bb4398b1d2df58a6b8bd877e3b7f0e0807f8

## Warrant

cost_report reads the pin ledger and the project's recorded rooms and traces to assemble a CostReport, so the section pulse's numbers come from is this function rather than a static estimate.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-23T21:46:16-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/cost.py § "cost_report" =sha256:e5ee389bd7cad4ebb86e4ec6f3e4bb4398b1d2df58a6b8bd877e3b7f0e0807f8
  artifact: sha256:965a2449d48702c8d6ac6f53c8b27ed5863a78b1f88ee747c9e907fbf9d4c63b
  note: propagated from a moved ground

- 2026-09-23T21:50:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/cost.py § "cost_report" =sha256:965a2449d48702c8d6ac6f53c8b27ed5863a78b1f88ee747c9e907fbf9d4c63b
  note: cost_report now prices a trace's injection through TraceEvent.injected_chars(), which reads the digest length a reflex line records; it still assembles the report from recorded activity, so the assertion is unaffected

## References

- README.md · standing · cites-as-live
