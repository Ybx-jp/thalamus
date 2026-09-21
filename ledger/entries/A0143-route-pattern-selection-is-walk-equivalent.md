---
id: A0143-route-pattern-selection-is-walk-equivalent
kind: claim
stated: 2026-09-13T23:54:35-07:00
author: architect
grade: argued
supersedes: none
verbatim_sha: ac47d5fca1636f1cfb17610623b77d8ad48451db7ce782e6364a295eaea11d85
---

## Assertion

A declared route pattern that names one file is resolved by a single stat rather than by looking for it in a walk of the repository, and selects the same files it would have selected had it been matched against every walked path.

## Scope

metric: which repo-relative paths a tuple of declared route patterns selects
cohort: the client and server pattern tuples a RoutePolicy declares
condition: not how many times the tree is walked or what the selection costs, only which files come out

## Grounds

- code: src/thalamus/arch/routes.py § "_matching" =sha256:34c33798e9153c5c636219c83434623dfdfc502a624364c35f92dd0909190435
- code: src/thalamus/arch/routes.py § "_nameable" =sha256:117bd7272da4b09c999c8c6e9ec7580d51024526305e10d37020d55e64f5e8a4

## Warrant

`_matching` has two branches and `_nameable` decides between them. The stat branch is entered only for a pattern carrying no glob metacharacter, so the pattern is one path and equality against a walked path is the same test as the stat; and `_nameable` refuses an absolute or upward pattern, which is the only way a stat could answer for a file the walk never yields. A dot-leading segment is deliberately not refused, because `Path.glob` yields entries whose name begins with a dot — the walk reaches them, so the stat must too.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: argued · author: propagation
  evidence: code: src/thalamus/arch/routes.py § "_matching" =sha256:34c33798e9153c5c636219c83434623dfdfc502a624364c35f92dd0909190435
  artifact: sha256:f3345b5f3da64cc18f6b3f1793763a012af0301fbcc141d5615b1d3c04143662
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: argued · author: main
  evidence: code: src/thalamus/arch/routes.py § "_matching" =sha256:f3345b5f3da64cc18f6b3f1793763a012af0301fbcc141d5615b1d3c04143662
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files, and the paragraph holding it was rewrapped. The assertion is unaffected.

## References

- src/thalamus/arch/routes.py · standing · cites-as-live
