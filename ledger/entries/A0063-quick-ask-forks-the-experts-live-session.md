---
id: A0063-quick-ask-forks-the-experts-live-session
kind: claim
stated: 2026-09-13T20:01:07-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: c2122e978e2eeb5f7bf1e5ee686b2fe1f3a49a7b346de6da6946f474b4ef3ef3
---

## Assertion

`thalamus quick ask <scope> <question>` forks that expert's already-live session rather than cold-starting a new one, so the answer comes from a warm process.

## Scope

metric: whether a quick ask starts a fresh process or forks a running one
cohort: every scope with a live pinned session
condition: the fork mechanism only

## Grounds

- code: src/thalamus/harness/quick.py § "run_fork" =sha256:8447adfad1d6931fe06ee13ef86c79fc9b3539310a9a2a77a6946352c87cd556

## Warrant

run_fork is the function thalamus quick ask calls, and forking an existing process is what makes the answer come from one already warm.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- README.md · standing · cites-as-live
- docs/concepts.md · standing · cites-as-live
