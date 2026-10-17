---
id: A0016-pin-is-checked-per-component-not-as-one-property
kind: claim
stated: 2026-09-13T20:14:38-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: b7dee252a9de18cdf3c30bc4385d739233764a5e5c15829e4932c0c635cbf1dc
---

## Assertion

A pin is not one property every harness carries equally; routing and the write/capability boundary bind on all of them, but the charter and per-scope MCP arming do not.

## Scope

metric: which pin properties each harness actually carries, and which it does not
cohort: the harnesses contract/pinning.py records
condition: the recorded properties only

## Grounds

- code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:201cf8dcec4edeb0fcca06cb9d070ecdd058a54243eb96c8067deb66d6a8d164

## Warrant

PIN_ROWS is the table stating, per component and per harness, which of these properties actually holds, so it is the ground for any claim about which bind everywhere and which do not.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-10-16T17:35:24-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:201cf8dcec4edeb0fcca06cb9d070ecdd058a54243eb96c8067deb66d6a8d164
  artifact: sha256:d4d8b6e66ce326e2acf33a0bf0798dfc19cbbdea2b5b51804df7d4e1e85b56c8
  note: propagated from a moved ground
- 2026-10-16T17:45:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:d4d8b6e66ce326e2acf33a0bf0798dfc19cbbdea2b5b51804df7d4e1e85b56c8
  note: Only a row's evidence text changed, naming `rooms.ensure_room` where it named `pin.ensure_room`. Moved by #342, which takes tmux and room handling out of core into console/; the assertion is unaffected.
- 2026-10-16T17:45:40-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:d4d8b6e66ce326e2acf33a0bf0798dfc19cbbdea2b5b51804df7d4e1e85b56c8
  artifact: sha256:57872046d27a6c309a3d6c3b8b89e251b3b717e274de24af16c8d0c95bae0b48
  note: propagated from a moved ground
- 2026-10-16T17:55:00-07:00 · corroborated · grade: measured · author: architect
  evidence: code: src/thalamus/contract/pinning.py § "PIN_ROWS" =sha256:57872046d27a6c309a3d6c3b8b89e251b3b717e274de24af16c8d0c95bae0b48
  note: Only wording in the section changed: #342 retires "roster" where it meant the set of experts or the console's tmux windows. The assertion is unaffected.

## References

- docs/concepts.md · standing · cites-as-live
