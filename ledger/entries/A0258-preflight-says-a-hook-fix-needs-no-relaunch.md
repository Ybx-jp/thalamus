---
id: A0258-preflight-says-a-hook-fix-needs-no-relaunch
kind: claim
stated: 2026-11-23T16:04:26-08:00
author: main
grade: argued
supersedes: none
verbatim_sha: 28e34064f5828b421e899c4e44f2d81e13daafc3eec8a6ea6d3eea49711c750e
---

## Assertion

Every preflight report closes on one repair line, which tells the operator and the session that a hook fixed in its settings file takes effect in the same session and that only a missing MCP server or a wrong pin env needs a relaunch.

## Scope

metric: the repair the preflight names beside its findings, on screen and as session context
cohort: every attended Claude Code session whose preflight reports a finding
condition: covers the wording the preflight prints, not whether the operator acts on it

## Grounds

- code: src/thalamus/harness/preflight.py § "_REPAIR" =sha256:52dd1ec6e1f3e7b753fc1a035ca5ab4a7db2632fee09d1b990a0c74a4bf8c655
- entry: A0257-claude-code-applies-hook-edits-to-the-running-session · cites-as-live

## Warrant

_REPAIR is the closing line of both the operator's on-screen message and the session's additionalContext. It sends a hook finding to the settings file and keeps the relaunch for what the process read at startup, which is right because Claude Code reloads its settings files into a running session (A0257).

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- src/thalamus/harness/preflight.py · standing · cites-as-live
