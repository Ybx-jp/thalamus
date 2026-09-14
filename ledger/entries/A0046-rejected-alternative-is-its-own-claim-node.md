---
id: A0046-rejected-alternative-is-its-own-claim-node
kind: claim
stated: 2026-09-13T20:44:08-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 57e839b884bad0491689dbc98e5147076f1d49aab26c1e54724bf42d824f23a3
---

## Assertion

An alternative a session considered and refused is written as its own claim, of kind `<scope>/rejected`, reached from the decision by a `USES` edge whose role is rejected and whose reason says why.

## Scope

metric: whether a rejected alternative is a claim node of its own or only a sentence inside the rationale
cohort: every alternative a decision names
condition: these two functions only

## Grounds

- code: src/thalamus/substrate/schema.py § "rejected_kind" =sha256:cf96c8a66a3c56a4ee513924d167f222d7d0d0cbddaf4ed22ba537f37f9f5e01
- code: src/thalamus/substrate/writer.py § "_write_alternative" =sha256:befe1a70944b87c1986eda1ec6ccbb3f511ce5aff0dd19aaaa2f16c7587b4b65

## Warrant

rejected_kind computes the <scope>/rejected kind string and _write_alternative is what writes the alternative as a claim reached by that USES edge, so together they are the mechanism making a rejected option its own citable node.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
