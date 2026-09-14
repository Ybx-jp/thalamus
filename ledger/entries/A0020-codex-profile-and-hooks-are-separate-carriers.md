---
id: A0020-codex-profile-and-hooks-are-separate-carriers
kind: claim
stated: 2026-09-13T20:18:06-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: 386cba3bee6b9cd68ab36a2841910dbe85b63297024aa199f5ba2697a1218f5e
---

## Assertion

codex's `--profile` selects the charter but tells its hooks nothing; the scope still reaches the hooks separately, through the launched argv's `env` prefix.

## Scope

metric: which carrier delivers the scope to the hooks versus to the charter
cohort: every codex session launched pinned
condition: the argv construction only

## Grounds

- code: src/thalamus/harness/pin.py § "_session_argv" =sha256:c87c3b5f0b3c148b6e6cc00a7fdb4a466eafa5358aec8cc106261e5133680d4b

## Warrant

_session_argv is what builds the launched argv, including the env prefix that carries the scope to the hooks independently of the --profile flag, which is what keeps the two carriers separate.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
