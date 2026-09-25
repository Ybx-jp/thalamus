---
id: A0165-reflex-runs-on-both-bash-result-events
kind: claim
stated: 2026-09-24T00:18:27-07:00
author: main
grade: measured
supersedes: A0161-reflex-does-not-run-on-a-nonzero-bash-exit
verbatim_change: the predecessor said the reflex runs only on PostToolUse and so never on a non-zero exit; the wiring now names both events, and the hook reads each event's own payload shape
verbatim_sha: 783dd4ac6f155642ac1aec0aa588a37c405108f2017f8058d722d877b8f4ea9c
---

## Assertion

The memory reflex is wired on both Claude Code events a Bash call can end on, PostToolUse for a command that exits 0 and PostToolUseFailure for one that exits non-zero, and applies the same failure test to either: the lexical pattern over the output the model saw, or the payload's interruption flag. A non-zero exit whose output reads clean does not fire it.

## Scope

metric: which Bash calls reach reflex.sh, and which of those it hands to thalamus reflex, in a Claude Code session installed by thalamus init
cohort: every Bash call in such a session that ran and exited
condition: covers the wiring as installed, not a hand-edited settings file; does not cover calls rejected before execution, which reach neither event

## Grounds

- code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:0f2a4371797f96fbb432d5b98a1d58d0f76a8393960bdb6fd17f7bbd219dc4c8
- code: src/thalamus/harness/hooks/claude-code/reflex.sh § "event" =sha256:e231cfa8a86a72cc9313e42e4601bfca8cbcc99345fe471b9a8a9c716d848816
- entry: A0160-claude-code-routes-a-nonzero-bash-exit-to-posttoolusefailure · cites-as-live

## Warrant

HOOK_WIRING, the table thalamus init writes the Claude Code hook block from, names reflex.sh with the Bash matcher under PostToolUse and under PostToolUseFailure. A Bash call that exits non-zero reaches the second event, whose input carries the output in an error string beside is_interrupt rather than a tool_response (A0160). The hook's event section reads the event name from the payload and takes the output and the interruption flag from whichever shape that event delivers, and the failure test that follows reads only those two values, so the event decides where the output is found and nothing about whether the call qualifies.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

- 2026-09-24T22:06:21-07:00 · contested · grade: measured · author: propagation
  evidence: code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:0f2a4371797f96fbb432d5b98a1d58d0f76a8393960bdb6fd17f7bbd219dc4c8
  artifact: sha256:73b3ffc79b79be95f953eff1db9691a4ca6be8fbc98fa746f13983b5e27df4c7
  note: propagated from a moved ground
- 2026-09-24T22:07:00-07:00 · corroborated · grade: measured · author: main
  evidence: code: src/thalamus/harness/install.py § "HOOK_WIRING" =sha256:73b3ffc79b79be95f953eff1db9691a4ca6be8fbc98fa746f13983b5e27df4c7
  note: HOOK_WIRING gained a PostToolUseFailure row for reflex-pointer-tap.sh with no matcher; reflex.sh's rows on PostToolUse and PostToolUseFailure with matcher Bash are unchanged, so the assertion is unaffected

## References

- docs/cli.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/reflex.sh · standing · cites-as-live
- src/thalamus/harness/reflex.py · standing · cites-as-live
