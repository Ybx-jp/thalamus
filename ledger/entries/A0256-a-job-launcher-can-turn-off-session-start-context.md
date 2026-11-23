---
id: A0256-a-job-launcher-can-turn-off-session-start-context
kind: claim
stated: 2026-11-23T11:31:04-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 6601f7ed28dd110a4ca3bd433ed45ba7080b37b65b22003d26fb2e1e1b262f1a
---

## Assertion

With THALAMUS_SESSION_CONTEXT set to none, the Claude Code session-start hook writes the session's pin-ledger row as for any session and outputs no additionalContext, carrying only the operator notice when there is one. Any other value leaves the priming as it is.

## Scope

metric: what the Claude Code session-start hook outputs and records under THALAMUS_SESSION_CONTEXT
cohort: startup and clear sessions through src/thalamus/harness/hooks/claude-code/session-start.sh
condition: resumed and compacted sessions output nothing either way, earlier in the script

## Grounds

- code: src/thalamus/harness/hooks/claude-code/session-start.sh § "session_context" =sha256:0ff16efc6816514fea7f1d4ebc8f444806125cfa0b5c97e1aa84cc5db33875c3

## Warrant

The section reads THALAMUS_SESSION_CONTEXT and, when it is none, prints an object holding only the systemMessage when operator_notice is set and exits before the output that carries additionalContext. The pin-ledger row is written earlier in the script, unconditionally on the session id, so it is unaffected.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/hooks/claude-code/session-start.sh · standing · cites-as-live
