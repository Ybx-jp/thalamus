---
id: A0254-claude-code-starts-mcp-servers-with-the-session-id-and-entrypoint
kind: claim
stated: 2026-11-23T11:02:17-08:00
author: main
grade: measured
supersedes: none
verbatim_sha: 58ebe8d72993a835b98ee82180ca5452bac16b7ae4a7418684d80542e03c21ef
---

## Assertion

Claude Code starts a stdio MCP server with the launching session's id in CLAUDE_CODE_SESSION_ID and its entrypoint in CLAUDE_CODE_ENTRYPOINT, sdk-cli for a headless run and cli for an interactive one, as it does for hooks. pin.process_session_type resolves the session type of the session a process serves from that session's pin-ledger row when the id names one, and otherwise by the launch rule: a declared THALAMUS_SESSION_TYPE, else a headless entrypoint is autonomous, else attended.

## Scope

metric: the environment a Claude Code MCP server process starts with, and the session type a process resolves from it
cohort: stdio MCP servers named by --mcp-config, headless and interactive
condition: measured on Claude Code 2.1.330, 2026-11-23, with an MCP server whose command wrote its CLAUDE and THALAMUS environment to a file and exited. Launched under env -i with only HOME, PATH and a tag set: claude -p --setting-sources project --strict-mcp-config gave CLAUDE_CODE_ENTRYPOINT=sdk-cli and CLAUDE_CODE_SESSION_ID equal to the run's session; the same launched interactively in a tmux pane gave cli and that session's id. A run launched from inside another session also inherited that session's THALAMUS_ variables. The session id is the one the server was launched under; a later /clear in the same process is outside this claim.

## Grounds

- code: src/thalamus/harness/pin.py § "process_session_type" =sha256:186ad117070900f8fca84ecdc5cc677d6516be01f6f700b9a9feab2b3c831c2f

## Warrant

process_session_type reads CLAUDE_CODE_SESSION_ID and asks ledger_session_type of that session's pin-ledger row, returning its answer when there is one; it then applies the declared THALAMUS_SESSION_TYPE, normalised as the bash resolver normalises it, then the sdk entrypoint prefix, then attended. The probe showed both variables present in a server's environment in each mode, so the ledger lookup is reachable from inside the MCP server.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
- src/thalamus/harness/pin.py · standing · cites-as-live
