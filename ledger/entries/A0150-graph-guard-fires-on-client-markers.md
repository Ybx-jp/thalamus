---
id: A0150-graph-guard-fires-on-client-markers
kind: claim
stated: 2026-09-14T10:18:18-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 98dc01e4976774fc0eefbe294e38a54d6aa2be0b8635e6b73a3df8e16f74fa96
---

## Assertion

The graph-access guard treats a command as a candidate when a graph-client marker appears on the command line itself, or in a `.py` file the command names that exists on disk when the guard runs; it reads such a file one level deep and follows none of its imports.

## Scope

metric: what makes a Bash command a candidate for the graph-access guard, and how deep the file read goes
cohort: every Bash command the guard inspects
condition: candidacy only; what the guard then does with a candidate under a given scope is a separate rule

## Grounds

- code: src/thalamus/harness/hooks/claude-code/graph-guard.sh § "marked" =sha256:ba301c2e2606f014f2a8a570bbbe92048e961993ea3cc56595dedb23639a1201

## Warrant

the marked block is the whole of candidacy: it greps the command for the marker set, then greps only the .py paths the command names and that pass an existence test, and it exits without a verdict when neither matches — so both the two surfaces it reads and the single level it reads them at are settled by that block.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-20T20:37:07-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/hooks/claude-code/graph-guard.sh § "marked" =sha256:ba301c2e2606f014f2a8a570bbbe92048e961993ea3cc56595dedb23639a1201
  artifact: sha256:28654d05d79b659a9d3cf7ca2d255f5aeb0a61af0e9f274ac6236452748cb1c7
  note: propagated from a moved ground

- 2026-09-20T20:37:29-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/hooks/claude-code/graph-guard.sh § "marked" =sha256:28654d05d79b659a9d3cf7ca2d255f5aeb0a61af0e9f274ac6236452748cb1c7
  note: the citation marker inside this section now names the entry by id alone, under the `citation-slug` rule `claims-ledger.toml` sets for source files. The assertion is unaffected.

## References

- src/thalamus/harness/skills/gremlin-python/SKILL.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/graph-guard.sh · standing · cites-as-live
