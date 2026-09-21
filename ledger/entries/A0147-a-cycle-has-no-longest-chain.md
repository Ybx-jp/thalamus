---
id: A0147-a-cycle-has-no-longest-chain
kind: claim
stated: 2026-09-14T10:14:02-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b464ec0d0e474b9c846d0cca4eaa37278e094595ccdd55e6c2104716bf69bfd6
---

## Assertion

When the reason relation contains a cycle, `eval uses` reports that there is no longest path rather than a depth computed over an arbitrary cut of it.

## Scope

metric: what the depth figure reports when the reason relation is cyclic
cohort: every set of reason edges the report measures depth over
condition: the cyclic case only; the acyclic depth figure is the ordinary path of the same function

## Grounds

- code: src/thalamus/eval/uses.py § "_longest_chain" =sha256:f17a73d540f04cf2861185386d87960d3bd9b81c744067abc60ee786f3e5176e

## Warrant

_longest_chain is a Kahn topological pass that counts the nodes it settles, and it returns the sentinel for no longest path exactly when that count falls short of the node set, which is the condition for a cycle.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/eval/uses.py § "_longest_chain" =sha256:f17a73d540f04cf2861185386d87960d3bd9b81c744067abc60ee786f3e5176e
  artifact: sha256:4dac6633ea8c1a4e92657987a415c1ce5d7362efbf36334da2d9846cf16afb8d
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/eval/uses.py § "_longest_chain" =sha256:4dac6633ea8c1a4e92657987a415c1ce5d7362efbf36334da2d9846cf16afb8d
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the docstring was rewrapped. The assertion is unaffected.

## References

- src/thalamus/eval/uses.py · standing · cites-as-live
