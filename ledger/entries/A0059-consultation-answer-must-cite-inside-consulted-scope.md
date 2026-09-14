---
id: A0059-consultation-answer-must-cite-inside-consulted-scope
kind: claim
stated: 2026-09-13T20:57:39-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 136a83928dc25e9f99c34c03fbfd5b7ec663e4387f34ec3eb19330aa9994f711
---

## Assertion

A consultation's answer must cite nodes inside the consulted scope, and those citations are validated before the ticket closes; tickets are single-use.

## Scope

metric: whether an answer's citations are checked before the ticket burns, and whether a burned ticket can be reused
cohort: every consultation ticket answered
condition: this validation and burn logic only

## Grounds

- code: src/thalamus/harness/consultation.py § "consult_answer" =sha256:cbdf5f0ea8341003e30f2439b10cc5c9b06d86b8aa401841cb19d53a03e185c7

## Warrant

consult_answer validates every cited vertex against the consulted scope before accepting the answer, and rejects a call against an already-burned ticket, which is exactly the citation and single-use rules the assertion states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-14T10:30:34-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/consultation.py § "consult_answer" =sha256:cbdf5f0ea8341003e30f2439b10cc5c9b06d86b8aa401841cb19d53a03e185c7
  artifact: sha256:6fcaed8d40fa583d9bffe700bc4849e4b31c5172b6d4db18f433f59cb3eaeb90
  note: propagated from a moved ground
- 2026-09-14T10:30:53-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/consultation.py § "consult_answer" =sha256:6fcaed8d40fa583d9bffe700bc4849e4b31c5172b6d4db18f433f59cb3eaeb90
  note: Read at the current revision. The write-gate change (7de0d95) added gate=refuse_unless_exchange_protocol_holds to the close_exchange call; the citation validation against the consulted scope and the burned-ticket refusal are unchanged.

## References

- docs/concepts.md · standing · cites-as-live
