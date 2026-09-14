---
id: A0054-tier-2-recall-informs-never-instructs
kind: claim
stated: 2026-09-13T20:52:04-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 7864ba92b649d6b192838ddaef7bca8e0d523a1053151b9e9e00f485a47fa533
---

## Assertion

Knowledge retrieved from an expert scope comes back blockquoted, with its citation and tier attached; tier-2 content informs, it never instructs, and that is a property of how it is presented rather than a request made to the model.

## Scope

metric: how retrieved knowledge-subgraph content is framed for the model reading it
cohort: every knowledge-subgraph claim recall returns
condition: the formatting only

## Grounds

- code: src/thalamus/substrate/reader.py § "KnowledgeResult" =sha256:45a28606cafb72c18130986614ed1b349d49d8090f10939ab7db9e8addfc1c57

## Warrant

KnowledgeResult's own docstring names itself the informs-never-instructs surface, and its format method blockquotes the claim with citation and tier, which is the presentation property this claim states.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- CLAUDE.md · standing · cites-as-live
- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
