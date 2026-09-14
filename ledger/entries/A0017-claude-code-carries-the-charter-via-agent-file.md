---
id: A0017-claude-code-carries-the-charter-via-agent-file
kind: claim
stated: 2026-09-13T20:15:45-07:00
author: main
grade: measured
supersedes: none
verbatim_sha: fa22786e6297e79d17c19b623b9b26b92bc784b22d1fbae5315c1e6aeaf7abdb
---

## Assertion

Claude Code carries a pin's charter and MCP arming through `--agent thalamus-<scope>`, an agent file generated under `.claude/agents/`.

## Scope

metric: how Claude Code receives the charter and its scope's MCP arming
cohort: every Claude Code session launched pinned
condition: the agent-file mechanism only

## Grounds

- code: src/thalamus/harness/pin.py § "write_agent" =sha256:0546100a9f15db84bef0d5150038e237b200448079e07cee192fdf012864c1f5

## Warrant

write_agent is what generates the .claude/agents/thalamus-<scope> file the --agent flag names, so it is the code making this the carrier for Claude Code specifically.

## Backing

none

<!-- APPEND BELOW THIS LINE ONLY -->

## Verdicts

## References

- docs/concepts.md · standing · cites-as-live
